from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from trace_jepa.util import sha256_file, sha256_value
from trace_jepa.worldmodels.dinowm import (
    DINOWMPredictorConfig,
    build_dinowm_predictor,
    save_dinowm_checkpoint,
    load_dinowm_checkpoint,
)
from trace_jepa.worldmodels.dinowm_io import load_dinowm_transition_dataset
from trace_jepa.worldmodels.training import (
    evaluate_frozen_model_bundle,
    train_development_models,
)


@dataclass(frozen=True)
class DINOWMTrainingConfig:
    predictor_dim: int = 96
    depth: int = 2
    heads: int = 4
    mlp_dim: int = 192
    dropout: float = 0.1
    learning_rate: float = 3e-4
    weight_decay: float = 1e-4
    batch_size: int = 32
    microbatch_size: int = 8
    max_epochs: int = 100
    early_stopping_patience: int = 12
    seed: int = 20260732
    bootstrap_seed: int = 20260733
    bootstrap_replicates: int = 2000


def _mean_losses(prediction: np.ndarray, target: np.ndarray) -> np.ndarray:
    return np.mean((prediction.astype(np.float64) - target.astype(np.float64)) ** 2, axis=(1, 2))


def _cosine_distance(prediction: np.ndarray, target: np.ndarray) -> np.ndarray:
    first = prediction.astype(np.float64).reshape(len(prediction), -1)
    second = target.astype(np.float64).reshape(len(target), -1)
    denominator = np.maximum(
        np.linalg.norm(first, axis=1) * np.linalg.norm(second, axis=1), 1e-12
    )
    return 1.0 - np.sum(first * second, axis=1) / denominator


def paired_episode_interval(
    first_loss: np.ndarray,
    second_loss: np.ndarray,
    episode_ids: np.ndarray,
    *,
    seed: int,
    replicates: int,
) -> dict[str, object]:
    """Cluster bootstrap a paired first-minus-second loss at episode level."""

    unique = np.unique(episode_ids.astype(str))
    difference_by_episode = np.asarray(
        [
            np.mean((first_loss - second_loss)[episode_ids.astype(str) == episode])
            for episode in unique
        ],
        dtype=np.float64,
    )
    result: dict[str, object] = {
        "estimate": float(difference_by_episode.mean()),
        "independent_episode_clusters": int(len(unique)),
    }
    if len(unique) < 20:
        result.update(
            {
                "ci_low": None,
                "ci_high": None,
                "interval_suppressed": True,
                "suppression_reason": "fewer than 20 independent validation episodes",
            }
        )
        return result
    rng = np.random.default_rng(seed)
    draws = rng.choice(len(unique), size=(replicates, len(unique)), replace=True)
    bootstrap = difference_by_episode[draws].mean(axis=1)
    result.update(
        {
            "ci_low": float(np.quantile(bootstrap, 0.025)),
            "ci_high": float(np.quantile(bootstrap, 0.975)),
            "interval_suppressed": False,
        }
    )
    return result


def _predict_in_batches(model, current: np.ndarray, actions: np.ndarray, batch_size: int) -> np.ndarray:
    import torch

    model.eval()
    predictions: list[np.ndarray] = []
    with torch.inference_mode():
        for start in range(0, len(current), batch_size):
            batch = torch.from_numpy(current[start : start + batch_size].astype(np.float32))
            action = torch.from_numpy(actions[start : start + batch_size].astype(np.int64))
            predictions.append(model(batch, action).cpu().numpy().astype(np.float32))
    return np.concatenate(predictions, axis=0)


def train_dinowm_dynamics(
    dataset_path: Path,
    checkpoint_path: Path,
    *,
    config: DINOWMTrainingConfig,
) -> tuple[np.ndarray, dict[str, object]]:
    """Fit on train, early-stop on tuning, and inspect development validation once."""

    import torch

    arrays, dataset_manifest = load_dinowm_transition_dataset(dataset_path)
    if dataset_manifest.get("study_partition") != "development":
        raise ValueError("dynamics fitting accepts development transitions only")
    splits = arrays["splits"].astype(str)
    train_rows = np.flatnonzero(splits == "train")
    tuning_rows = np.flatnonzero(splits == "tuning")
    validation_rows = np.flatnonzero(splits == "validation")
    if min(len(train_rows), len(tuning_rows), len(validation_rows)) == 0:
        raise ValueError("train, tuning, and validation transition splits are required")

    current = arrays["current_latents"].astype(np.float32)
    future = arrays["next_latents"].astype(np.float32)
    actions = arrays["actions"].astype(np.int64)
    if config.batch_size < 1 or config.microbatch_size < 1:
        raise ValueError("training batch sizes must be positive")
    if config.batch_size % config.microbatch_size:
        raise ValueError("effective batch_size must be divisible by microbatch_size")
    predictor_config = DINOWMPredictorConfig(
        patch_count=current.shape[1],
        feature_dim=current.shape[2],
        action_count=len(arrays["action_names"]),
        predictor_dim=config.predictor_dim,
        depth=config.depth,
        heads=config.heads,
        mlp_dim=config.mlp_dim,
        dropout=config.dropout,
    )
    torch.manual_seed(config.seed)
    np.random.seed(config.seed % (2**32))
    torch.use_deterministic_algorithms(True)
    model = build_dinowm_predictor(predictor_config)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    generator = torch.Generator().manual_seed(config.seed)
    best_tuning = float("inf")
    best_epoch = -1
    best_state = None
    epochs_without_improvement = 0
    history: list[dict[str, float | int]] = []

    for epoch in range(config.max_epochs):
        model.train()
        permutation = torch.randperm(len(train_rows), generator=generator).numpy()
        train_sse = 0.0
        train_elements = 0
        for start in range(0, len(train_rows), config.batch_size):
            group_rows = train_rows[permutation[start : start + config.batch_size]]
            optimizer.zero_grad(set_to_none=True)
            group_elements = len(group_rows) * current.shape[1] * current.shape[2]
            for micro_start in range(0, len(group_rows), config.microbatch_size):
                rows = group_rows[
                    micro_start : micro_start + config.microbatch_size
                ]
                batch_current = torch.from_numpy(current[rows])
                batch_future = torch.from_numpy(future[rows])
                batch_actions = torch.from_numpy(actions[rows])
                prediction = model(batch_current, batch_actions)
                squared_error = torch.sum((prediction - batch_future) ** 2)
                (squared_error / group_elements).backward()
                train_sse += float(squared_error.detach())
                train_elements += prediction.numel()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

        tuning_prediction = _predict_in_batches(
            model,
            current[tuning_rows],
            actions[tuning_rows],
            config.microbatch_size,
        )
        tuning_mse = float(np.mean((tuning_prediction - future[tuning_rows]) ** 2))
        train_mse = train_sse / train_elements
        history.append({"epoch": epoch + 1, "train_mse": train_mse, "tuning_mse": tuning_mse})
        if tuning_mse < best_tuning - 1e-9:
            best_tuning = tuning_mse
            best_epoch = epoch + 1
            best_state = {
                name: value.detach().cpu().clone()
                for name, value in model.state_dict().items()
            }
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
        if epochs_without_improvement >= config.early_stopping_patience:
            break

    if best_state is None:
        raise RuntimeError("DINO-WM training did not produce a finite tuning checkpoint")
    model.load_state_dict(best_state, strict=True)
    model.eval()
    predictions = _predict_in_batches(model, current, actions, config.microbatch_size)
    metadata = {
        "development_only": True,
        "training_dataset_sha256": dataset_manifest["dataset_sha256"],
        "encoder": dataset_manifest["encoder"],
        "best_epoch": best_epoch,
        "best_tuning_mse": best_tuning,
        "test_rows_accessed": False,
        "objective": "next_patch_embedding_mse",
    }
    checkpoint_sha256 = save_dinowm_checkpoint(
        checkpoint_path,
        model,
        predictor_config,
        metadata=metadata,
    )

    shuffled_actions = actions.copy()
    for episode_id in np.unique(arrays["episode_ids"].astype(str)):
        rows = np.flatnonzero(arrays["episode_ids"].astype(str) == episode_id)
        shuffled_actions[rows] = np.roll(actions[rows], 1)
    shuffled_predictions = _predict_in_batches(
        model, current, shuffled_actions, config.microbatch_size
    )
    model_loss = _mean_losses(predictions[validation_rows], future[validation_rows])
    persistence_loss = _mean_losses(current[validation_rows], future[validation_rows])
    shuffled_loss = _mean_losses(
        shuffled_predictions[validation_rows], future[validation_rows]
    )
    validation_episode_ids = arrays["episode_ids"][validation_rows].astype(str)
    report = {
        "report_version": "flood-sar-dinowm-dynamics-development-v1",
        "dataset_sha256": dataset_manifest["dataset_sha256"],
        "checkpoint_sha256": checkpoint_sha256,
        "best_epoch": best_epoch,
        "epochs_completed": len(history),
        "best_tuning_mse": best_tuning,
        "validation_episode_count": int(len(np.unique(validation_episode_ids))),
        "validation_transition_count": int(len(validation_rows)),
        "validation": {
            "predicted_future_mse": float(model_loss.mean()),
            "persistence_mse": float(persistence_loss.mean()),
            "shuffled_action_mse": float(shuffled_loss.mean()),
            "predicted_future_cosine_distance": float(
                _cosine_distance(
                    predictions[validation_rows], future[validation_rows]
                ).mean()
            ),
            "persistence_cosine_distance": float(
                _cosine_distance(current[validation_rows], future[validation_rows]).mean()
            ),
        },
        "paired_episode_bootstrap": {
            "model_minus_persistence_mse": paired_episode_interval(
                model_loss,
                persistence_loss,
                validation_episode_ids,
                seed=config.bootstrap_seed,
                replicates=config.bootstrap_replicates,
            ),
            "model_minus_shuffled_action_mse": paired_episode_interval(
                model_loss,
                shuffled_loss,
                validation_episode_ids,
                seed=config.bootstrap_seed + 1,
                replicates=config.bootstrap_replicates,
            ),
        },
        "training_history": history,
        "test_rows_accessed": False,
    }
    return predictions, report


def write_dinowm_outcome_dataset(
    path: Path,
    transition_dataset_path: Path,
    visual_features: np.ndarray,
    *,
    feature_version: str,
    feature_checkpoint_sha256: str,
) -> Path:
    arrays, source_manifest = load_dinowm_transition_dataset(transition_dataset_path)
    visual = np.asarray(visual_features, dtype=np.float32)
    if visual.ndim != 2 or len(visual) != len(arrays["actions"]):
        raise ValueError("outcome visual features must contain one vector per transition")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        structured=arrays["structured"].astype(np.float32),
        visual=visual,
        actions=arrays["actions"].astype(np.int64),
        targets=arrays["targets"].astype(np.float32),
        outcomes=arrays["outcomes"].astype(np.int64),
        episode_ids=arrays["episode_ids"],
        splits=arrays["splits"],
        observation_hashes=arrays["next_observation_hashes"],
        action_names=arrays["action_names"],
        target_names=arrays["target_names"],
    )
    manifest = {
        "dataset_version": "flood-sar-dinowm-outcome-features-v1",
        "dataset_sha256": sha256_file(path),
        "source_transition_dataset_sha256": source_manifest["dataset_sha256"],
        "episode_count": source_manifest["episode_count"],
        "row_count": source_manifest["transition_count"],
        "split_unit": "complete_episode",
        "split_episode_counts": source_manifest["split_episode_counts"],
        "test_included": False,
        "encoder": {
            "family": "DINO-WM",
            "version": feature_version,
            "checkpoint_sha256": feature_checkpoint_sha256,
            "role": "action_conditioned_predicted_future_spatial_features",
        },
        "visual_feature_count": int(visual.shape[1]),
        "feature_inventory_sha256": sha256_value(visual.tolist()),
    }
    manifest_path = path.with_suffix(path.suffix + ".json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    return manifest_path


def _gate_from_reports(
    dynamics: dict[str, object], outcome: dict[str, object]
) -> dict[str, object]:
    transition = dynamics["validation"]
    transition_intervals = dynamics["paired_episode_bootstrap"]
    models = outcome["models"]
    paired = outcome["paired_episode_bootstrap"]
    dynamics_persistence = bool(
        transition["predicted_future_mse"] < transition["persistence_mse"]
        and transition_intervals["model_minus_persistence_mse"]["ci_high"] is not None
        and transition_intervals["model_minus_persistence_mse"]["ci_high"] < 0.0
    )
    dynamics_action = bool(
        transition["predicted_future_mse"] < transition["shuffled_action_mse"]
    )
    outcome_points = bool(
        models["fused"]["brier"] < models["structured"]["brier"]
        and models["fused"]["mse_all_targets"]
        < models["structured"]["mse_all_targets"]
    )
    brier_supported = bool(
        paired["fused_minus_structured_brier"]["ci_high"] is not None
        and paired["fused_minus_structured_brier"]["ci_high"] < 0.0
        and models["fused"]["brier"]
        < models["fused_shuffled_visual"]["brier"]
    )
    mse_supported = bool(
        paired["fused_minus_structured_target_mse"]["ci_high"] is not None
        and paired["fused_minus_structured_target_mse"]["ci_high"] < 0.0
        and models["fused"]["mse_all_targets"]
        < models["fused_shuffled_visual"]["mse_all_targets"]
    )
    conditions = {
        "dynamics_beats_persistence_with_supported_interval": dynamics_persistence,
        "dynamics_beats_shuffled_action_point_estimate": dynamics_action,
        "fused_beats_structured_on_both_primary_point_estimates": outcome_points,
        "at_least_one_outcome_metric_supported_and_beats_shuffle": (
            brier_supported or mse_supported
        ),
    }
    return {
        "passed": all(conditions.values()),
        "conditions": conditions,
        "heldout_action": (
            "freeze_manifest_then_evaluate_once"
            if all(conditions.values())
            else "keep_heldout_closed"
        ),
    }


def run_dinowm_development_confirmation(
    transition_dataset_path: Path,
    output_dir: Path,
    *,
    config: DINOWMTrainingConfig,
) -> dict[str, object]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dynamics_checkpoint = output_dir / "dinowm_dynamics_development_v1.pt"
    predictions, dynamics_report = train_dinowm_dynamics(
        transition_dataset_path,
        dynamics_checkpoint,
        config=config,
    )
    dynamics_checkpoint_sha256 = sha256_file(dynamics_checkpoint)
    arrays, transition_manifest = load_dinowm_transition_dataset(
        transition_dataset_path
    )
    predicted_dataset = output_dir / "dinowm_predicted_future_outcomes_v1.npz"
    write_dinowm_outcome_dataset(
        predicted_dataset,
        transition_dataset_path,
        predictions.mean(axis=1),
        feature_version=f"flood-sar-dinowm-v1-{dynamics_checkpoint_sha256[:12]}",
        feature_checkpoint_sha256=dynamics_checkpoint_sha256,
    )
    outcome_checkpoint = output_dir / "dinowm_route_head_development_v1.npz"
    outcome_report_path = output_dir / "dinowm_outcome_development_report.json"
    outcome_report = train_development_models(
        predicted_dataset,
        outcome_checkpoint,
        outcome_report_path,
        seed=config.seed + 2,
        model_bundle_path=output_dir / "dinowm_outcome_models_development_v1.npz",
    )

    current_dataset = output_dir / "dinov2_current_outcomes_control_v1.npz"
    encoder = dict(transition_manifest["encoder"])
    write_dinowm_outcome_dataset(
        current_dataset,
        transition_dataset_path,
        arrays["current_latents"].astype(np.float32).mean(axis=1),
        feature_version=str(encoder["version"]),
        feature_checkpoint_sha256=str(encoder["checkpoint_sha256"]),
    )
    current_report = train_development_models(
        current_dataset,
        output_dir / "dinov2_current_route_head_control_v1.npz",
        output_dir / "dinov2_current_outcome_control_report.json",
        seed=config.seed + 2,
        model_bundle_path=output_dir / "dinov2_current_outcome_models_control_v1.npz",
    )
    gate = _gate_from_reports(dynamics_report, outcome_report)
    report = {
        "report_version": "flood-sar-dinowm-development-confirmation-v1",
        "transition_dataset_sha256": transition_manifest["dataset_sha256"],
        "dynamics": dynamics_report,
        "predicted_future_outcomes": outcome_report,
        "current_visual_control": current_report,
        "gate": gate,
        "artifacts": {
            "dynamics_checkpoint_sha256": dynamics_checkpoint_sha256,
            "outcome_checkpoint_sha256": sha256_file(outcome_checkpoint),
            "predicted_outcome_dataset_sha256": sha256_file(predicted_dataset),
        },
        "test_generated": False,
        "test_rows_accessed": False,
    }
    report_path = output_dir / "dinowm_development_confirmation_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    return report


def run_dinowm_heldout_evaluation(
    transition_dataset_path: Path,
    output_path: Path,
    *,
    freeze_manifest: dict[str, object],
    freeze_manifest_path: Path,
    dynamics_checkpoint_path: Path,
    outcome_bundle_path: Path,
    current_control_bundle_path: Path,
) -> dict[str, object]:
    """Evaluate frozen dynamics and outcome models once without fitting or tuning."""

    output_path = Path(output_path)
    if output_path.exists():
        raise ValueError("held-out DINO-WM evaluation report already exists")
    if freeze_manifest.get("test_authorized") is not True:
        raise ValueError("held-out DINO-WM evaluation is not authorized")
    if freeze_manifest.get("no_post_open_tuning") is not True:
        raise ValueError("freeze manifest does not prohibit post-open tuning")
    if sha256_file(dynamics_checkpoint_path) != freeze_manifest[
        "predictor_checkpoint_sha256"
    ]:
        raise ValueError("frozen dynamics checkpoint hash mismatch")
    if sha256_file(outcome_bundle_path) != freeze_manifest[
        "outcome_model_bundle_sha256"
    ]:
        raise ValueError("frozen outcome bundle hash mismatch")
    if sha256_file(current_control_bundle_path) != freeze_manifest[
        "current_control_bundle_sha256"
    ]:
        raise ValueError("frozen current-control bundle hash mismatch")

    arrays, dataset_manifest = load_dinowm_transition_dataset(
        transition_dataset_path,
        allow_test=True,
        test_authorization_manifest=freeze_manifest_path,
    )
    if dataset_manifest.get("study_partition") != "test" or set(
        arrays["splits"].astype(str)
    ) != {"test"}:
        raise ValueError("held-out evaluation requires test-only transitions")
    if dataset_manifest["data_seed"] != freeze_manifest["test_data_seed"]:
        raise ValueError("held-out data seed differs from the freeze manifest")
    if dataset_manifest["split_seed"] != freeze_manifest["test_split_seed"]:
        raise ValueError("held-out split seed differs from the freeze manifest")
    if dataset_manifest["episode_count"] != freeze_manifest["test_episode_count"]:
        raise ValueError("held-out episode count differs from the freeze manifest")

    model, _, checkpoint_metadata = load_dinowm_checkpoint(
        dynamics_checkpoint_path
    )
    current = arrays["current_latents"].astype(np.float32)
    future = arrays["next_latents"].astype(np.float32)
    actions = arrays["actions"].astype(np.int64)
    prediction = _predict_in_batches(model, current, actions, batch_size=8)
    shuffled_actions = actions.copy()
    episode_ids = arrays["episode_ids"].astype(str)
    for episode_id in np.unique(episode_ids):
        rows = np.flatnonzero(episode_ids == episode_id)
        shuffled_actions[rows] = np.roll(actions[rows], 1)
    shuffled_prediction = _predict_in_batches(
        model, current, shuffled_actions, batch_size=8
    )
    model_loss = _mean_losses(prediction, future)
    persistence_loss = _mean_losses(current, future)
    shuffled_loss = _mean_losses(shuffled_prediction, future)
    bootstrap_seed = int(freeze_manifest["test_bootstrap_seed"])
    dynamics = {
        "predicted_future_mse": float(model_loss.mean()),
        "persistence_mse": float(persistence_loss.mean()),
        "shuffled_action_mse": float(shuffled_loss.mean()),
        "predicted_future_cosine_distance": float(
            _cosine_distance(prediction, future).mean()
        ),
        "persistence_cosine_distance": float(
            _cosine_distance(current, future).mean()
        ),
        "paired_episode_bootstrap": {
            "model_minus_persistence_mse": paired_episode_interval(
                model_loss,
                persistence_loss,
                episode_ids,
                seed=bootstrap_seed,
                replicates=2000,
            ),
            "model_minus_shuffled_action_mse": paired_episode_interval(
                model_loss,
                shuffled_loss,
                episode_ids,
                seed=bootstrap_seed + 1,
                replicates=2000,
            ),
        },
    }

    common = {
        "structured": arrays["structured"].astype(np.float32),
        "actions": actions,
        "targets": arrays["targets"].astype(np.float32),
        "outcomes": arrays["outcomes"].astype(np.int64),
        "episode_ids": arrays["episode_ids"],
        "action_names": arrays["action_names"],
        "target_names": arrays["target_names"],
    }
    predicted_outcome_arrays = {
        **common,
        "visual": prediction.mean(axis=1).astype(np.float32),
    }
    current_outcome_arrays = {
        **common,
        "visual": current.mean(axis=1).astype(np.float32),
    }
    predicted_outcomes = evaluate_frozen_model_bundle(
        predicted_outcome_arrays,
        outcome_bundle_path,
        shuffle_seed=int(freeze_manifest["test_shuffle_seed"]),
        bootstrap_seed=bootstrap_seed + 10,
    )
    current_control = evaluate_frozen_model_bundle(
        current_outcome_arrays,
        current_control_bundle_path,
        shuffle_seed=int(freeze_manifest["test_shuffle_seed"]),
        bootstrap_seed=bootstrap_seed + 20,
    )
    report = {
        "report_version": "flood-sar-dinowm-heldout-v1",
        "freeze_manifest_sha256": sha256_file(freeze_manifest_path),
        "test_dataset_sha256": dataset_manifest["dataset_sha256"],
        "test_episode_count": dataset_manifest["episode_count"],
        "test_transition_count": dataset_manifest["transition_count"],
        "dynamics": dynamics,
        "predicted_future_outcomes": predicted_outcomes,
        "current_visual_control": current_control,
        "frozen_development_checkpoint_metadata": checkpoint_metadata,
        "fitting_performed": False,
        "tuning_performed": False,
        "calibration_performed": False,
        "test_rows_accessed": True,
        "claim_boundary": (
            "one held-out controlled simulator evaluation; no field-video, "
            "operational-safety, or cross-domain conclusion"
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    return report
