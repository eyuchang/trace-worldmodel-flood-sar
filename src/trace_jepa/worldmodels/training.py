from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from trace_jepa.util import sha256_file, sha256_value
from trace_jepa.worldmodels.calibration import IsotonicCalibrator, expected_calibration_error
from trace_jepa.worldmodels.dataset import load_feature_dataset


RIDGE_ALPHAS = (1e-4, 1e-3, 1e-2, 1e-1, 1.0, 10.0)
MODEL_MODES = ("constant", "structured", "visual", "fused", "fused_shuffled_visual")


@dataclass(frozen=True)
class Normalization:
    structured_mean: np.ndarray
    structured_std: np.ndarray
    visual_mean: np.ndarray
    visual_std: np.ndarray


def _safe_stats(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mean = values.mean(axis=0)
    std = values.std(axis=0)
    return mean, np.maximum(std, 1e-6)


def _normalization(arrays: dict[str, np.ndarray], train: np.ndarray) -> Normalization:
    structured_mean, structured_std = _safe_stats(arrays["structured"][train])
    visual_mean, visual_std = _safe_stats(arrays["visual"][train])
    return Normalization(structured_mean, structured_std, visual_mean, visual_std)


def _design(
    arrays: dict[str, np.ndarray],
    rows: np.ndarray,
    normalization: Normalization,
    mode: str,
    *,
    shuffled_visual: np.ndarray | None = None,
) -> np.ndarray:
    structured = (
        arrays["structured"][rows] - normalization.structured_mean
    ) / normalization.structured_std
    visual_source = arrays["visual"][rows] if shuffled_visual is None else shuffled_visual
    visual = (visual_source - normalization.visual_mean) / normalization.visual_std
    actions = np.eye(len(arrays["action_names"]), dtype=np.float64)[arrays["actions"][rows]]
    if mode == "structured":
        return np.concatenate([structured, actions], axis=1)
    if mode == "visual":
        return np.concatenate([visual, actions], axis=1)
    if mode in {"fused", "fused_shuffled_visual"}:
        return np.concatenate([structured, visual, actions], axis=1)
    if mode == "constant":
        return np.zeros((len(rows), 0), dtype=np.float64)
    raise ValueError(f"unknown model mode: {mode}")


def _shuffle_visual_by_episode(
    arrays: dict[str, np.ndarray],
    rows: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    """Permute the visual channel at the independent-episode unit.

    Every counterfactual action row from one target episode receives the same
    source episode's feature. This destroys visual/label alignment without
    creating an impossible within-episode mixture of observations.
    """

    episode_ids = arrays["episode_ids"][rows].astype(str)
    unique_episodes = np.unique(episode_ids)
    permuted = rng.permutation(unique_episodes)
    source_by_target = dict(zip(unique_episodes, permuted, strict=True))
    first_row_by_episode = {
        episode_id: rows[np.flatnonzero(episode_ids == episode_id)[0]]
        for episode_id in unique_episodes
    }
    return np.asarray(
        [
            arrays["visual"][first_row_by_episode[source_by_target[episode_id]]]
            for episode_id in episode_ids
        ]
    )


def _fit_ridge(design: np.ndarray, targets: np.ndarray, alpha: float) -> np.ndarray:
    feature_mean = design.mean(axis=0)
    target_mean = targets.mean(axis=0)
    centered_design = design - feature_mean
    centered_targets = targets - target_mean
    if design.shape[1] == 0:
        coefficients = np.empty((0, targets.shape[1]), dtype=np.float64)
    elif design.shape[1] <= len(design):
        coefficients = np.linalg.solve(
            centered_design.T @ centered_design + alpha * np.eye(design.shape[1], dtype=np.float64),
            centered_design.T @ centered_targets,
        )
    else:
        # The frozen encoder is high-dimensional relative to a development
        # sample. The algebraically equivalent dual system is both faster and
        # better conditioned than inverting a mostly empty feature covariance.
        coefficients = centered_design.T @ np.linalg.solve(
            centered_design @ centered_design.T + alpha * np.eye(len(design), dtype=np.float64),
            centered_targets,
        )
    intercept = target_mean - feature_mean @ coefficients
    return np.vstack([coefficients, intercept])


def _predict(design: np.ndarray, weights: np.ndarray) -> np.ndarray:
    return np.concatenate([design, np.ones((len(design), 1))], axis=1) @ weights


def _binary_metrics(probability: np.ndarray, outcomes: np.ndarray) -> dict[str, float | None]:
    probability = np.clip(np.asarray(probability), 1e-6, 1.0 - 1e-6)
    outcomes = np.asarray(outcomes)
    positive = outcomes == 1
    negative = outcomes == 0
    auroc = None
    average_precision = None
    if positive.any() and negative.any():
        order = np.argsort(probability, kind="stable")
        sorted_probability = probability[order]
        ranks = np.arange(1, len(probability) + 1, dtype=np.float64)
        for value in np.unique(sorted_probability):
            tied = sorted_probability == value
            ranks[tied] = ranks[tied].mean()
        rank_by_original = np.empty_like(ranks)
        rank_by_original[order] = ranks
        auroc = float(
            (rank_by_original[positive].sum() - positive.sum() * (positive.sum() + 1) / 2)
            / (positive.sum() * negative.sum())
        )
        descending = np.argsort(-probability, kind="stable")
        sorted_positive = positive[descending]
        precision = np.cumsum(sorted_positive) / np.arange(1, len(probability) + 1)
        average_precision = float(precision[sorted_positive].mean())
    return {
        "brier": float(np.mean((probability - outcomes) ** 2)),
        "nll": float(
            -np.mean(outcomes * np.log(probability) + (1 - outcomes) * np.log(1 - probability))
        ),
        "ece_10": expected_calibration_error(probability, outcomes, bins=10),
        "auroc": auroc,
        "average_precision": average_precision,
    }


def _regression_metrics(prediction: np.ndarray, targets: np.ndarray) -> dict[str, object]:
    residual = prediction - targets
    return {
        "mse_all_targets": float(np.mean(residual**2)),
        "mae_by_target": [float(value) for value in np.mean(np.abs(residual), axis=0)],
        "rmse_by_target": [float(value) for value in np.sqrt(np.mean(residual**2, axis=0))],
    }


def _cluster_bootstrap_difference(
    first_loss: np.ndarray,
    second_loss: np.ndarray,
    episode_ids: np.ndarray,
    *,
    seed: int,
    replicates: int = 2000,
) -> dict[str, object]:
    unique = np.unique(episode_ids)
    if len(unique) < 20:
        return {
            "estimate": float(np.mean(first_loss - second_loss)),
            "ci_low": None,
            "ci_high": None,
            "independent_episode_clusters": int(len(unique)),
            "interval_suppressed": True,
            "suppression_reason": "fewer than 20 independent validation episodes",
        }
    difference_by_episode = np.asarray(
        [np.mean((first_loss - second_loss)[episode_ids == episode]) for episode in unique]
    )
    rng = np.random.default_rng(seed)
    draws = rng.choice(len(unique), size=(replicates, len(unique)), replace=True)
    bootstrap = difference_by_episode[draws].mean(axis=1)
    return {
        "estimate": float(difference_by_episode.mean()),
        "ci_low": float(np.quantile(bootstrap, 0.025)),
        "ci_high": float(np.quantile(bootstrap, 0.975)),
        "independent_episode_clusters": int(len(unique)),
        "interval_suppressed": False,
    }


def train_development_models(
    dataset_path: Path,
    checkpoint_path: Path,
    report_path: Path,
    *,
    seed: int = 23,
    model_bundle_path: Path | None = None,
) -> dict[str, object]:
    """Tune, calibrate, then evaluate once on disjoint development episodes.

    Test rows, when present in a separately authorized dataset, are never read by
    this function. The fused checkpoint remains a development artifact until an
    independently frozen test manifest is executed.
    """

    arrays, dataset_manifest = load_feature_dataset(dataset_path)
    splits = arrays["splits"].astype(str)
    masks = {
        split: np.flatnonzero(splits == split)
        for split in ("train", "tuning", "calibration", "validation")
    }
    if any(len(rows) == 0 for rows in masks.values()):
        raise ValueError(
            "train, tuning, calibration, and validation must each contain complete episodes"
        )
    normalization = _normalization(arrays, masks["train"])
    rng = np.random.default_rng(seed)
    results: dict[str, dict[str, object]] = {}
    predictions: dict[str, np.ndarray] = {}
    fitted: dict[str, tuple[np.ndarray, IsotonicCalibrator, np.ndarray, np.ndarray]] = {}

    for mode in MODEL_MODES:
        shuffled: dict[str, np.ndarray] = {}
        if mode == "fused_shuffled_visual":
            for split, rows in masks.items():
                shuffled[split] = _shuffle_visual_by_episode(arrays, rows, rng)
        designs = {
            split: _design(
                arrays,
                rows,
                normalization,
                mode,
                shuffled_visual=shuffled.get(split),
            )
            for split, rows in masks.items()
        }
        best: tuple[float, float, np.ndarray] | None = None
        for alpha in RIDGE_ALPHAS:
            weights = _fit_ridge(designs["train"], arrays["targets"][masks["train"]], alpha)
            tuning_prediction = _predict(designs["tuning"], weights)
            score = float(
                np.mean((tuning_prediction - arrays["targets"][masks["tuning"]]) ** 2)
            )
            if best is None or score < best[0]:
                best = (score, alpha, weights)
        assert best is not None
        calibration_prediction = _predict(designs["calibration"], best[2])
        calibrator = IsotonicCalibrator.fit(
            np.clip(calibration_prediction[:, 0], 0.0, 1.0),
            arrays["outcomes"][masks["calibration"]],
        )
        validation_prediction = _predict(designs["validation"], best[2])
        validation_prediction[:, 0] = calibrator.transform(
            np.clip(validation_prediction[:, 0], 0.0, 1.0)
        )
        validation_prediction[:, 2] = np.clip(validation_prediction[:, 2], 0.0, 1.0)
        predictions[mode] = validation_prediction
        binary = _binary_metrics(
            validation_prediction[:, 0], arrays["outcomes"][masks["validation"]]
        )
        regression = _regression_metrics(
            validation_prediction, arrays["targets"][masks["validation"]]
        )
        results[mode] = {
            "selected_ridge_alpha": best[1],
            "tuning_selection_mse": best[0],
            **binary,
            **regression,
        }
        residual_rmse = np.sqrt(
            np.mean(
                (calibration_prediction - arrays["targets"][masks["calibration"]]) ** 2,
                axis=0,
            )
        )
        fitted[mode] = (best[2], calibrator, residual_rmse, designs["train"])

    validation_rows = masks["validation"]
    episode_ids = arrays["episode_ids"][validation_rows].astype(str)
    fused_brier = (predictions["fused"][:, 0] - arrays["outcomes"][validation_rows]) ** 2
    structured_brier = (predictions["structured"][:, 0] - arrays["outcomes"][validation_rows]) ** 2
    fused_mse = np.mean((predictions["fused"] - arrays["targets"][validation_rows]) ** 2, axis=1)
    structured_mse = np.mean(
        (predictions["structured"] - arrays["targets"][validation_rows]) ** 2, axis=1
    )
    paired = {
        "fused_minus_structured_brier": _cluster_bootstrap_difference(
            fused_brier, structured_brier, episode_ids, seed=seed + 1
        ),
        "fused_minus_structured_target_mse": _cluster_bootstrap_difference(
            fused_mse, structured_mse, episode_ids, seed=seed + 2
        ),
    }
    shuffled_brier = (
        predictions["fused_shuffled_visual"][:, 0]
        - arrays["outcomes"][validation_rows]
    ) ** 2
    shuffled_mse = np.mean(
        (
            predictions["fused_shuffled_visual"]
            - arrays["targets"][validation_rows]
        )
        ** 2,
        axis=1,
    )
    paired.update(
        {
            "fused_minus_shuffled_visual_brier": _cluster_bootstrap_difference(
                fused_brier, shuffled_brier, episode_ids, seed=seed + 3
            ),
            "fused_minus_shuffled_visual_target_mse": (
                _cluster_bootstrap_difference(
                    fused_mse, shuffled_mse, episode_ids, seed=seed + 4
                )
            ),
        }
    )

    weights, calibrator, residual_rmse, fused_train_design = fitted["fused"]
    encoder = dict(dataset_manifest["encoder"])
    calibration_version = f"route-isotonic-v1-{sha256_value([calibrator.thresholds.tolist(), calibrator.values.tolist()])[:12]}"
    predictor_version = f"flood-route-linear-v1-{sha256_value(weights.tolist())[:12]}"
    is_dinowm = str(encoder.get("family", "")).lower() == "dino-wm"
    metadata = {
        "checkpoint_schema_version": "flood-route-linear-head-v1",
        "encoder_version": encoder["version"],
        "encoder_checkpoint_sha256": encoder["checkpoint_sha256"],
        "predictor_version": predictor_version,
        "calibration_version": calibration_version,
        "training_snapshot": dataset_manifest["dataset_sha256"],
        "semantic_probe_versions": ["route-success-hazard-probes-v1"],
        "visual_freshness_s": 180.0,
        "development_only": True,
        "test_rows_accessed": False,
        "feature_schema_version": (
            "route-dinowm-future-fusion-v1" if is_dinowm else "route-jepa-fusion-v1"
        ),
        "prediction_assumptions": (
            [
                "model_conditional_prediction",
                "frozen_visual_encoder",
                "action_conditioned_future_representation",
                "controller_visible_inputs_only",
                "calibrated_on_declared_development_distribution",
                "visual_freshness_is_gated",
            ]
            if is_dinowm
            else [
                "model_conditional_prediction",
                "frozen_visual_encoder",
                "controller_visible_inputs_only",
                "calibrated_on_declared_development_distribution",
                "visual_freshness_is_gated",
            ]
        ),
    }
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        checkpoint_path,
        weights=weights,
        structured_mean=normalization.structured_mean,
        structured_std=normalization.structured_std,
        visual_mean=normalization.visual_mean,
        visual_std=normalization.visual_std,
        training_min=fused_train_design.min(axis=0),
        training_max=fused_train_design.max(axis=0),
        support_center=fused_train_design.mean(axis=0),
        support_scale=np.maximum(fused_train_design.std(axis=0), 0.25),
        residual_rmse=residual_rmse,
        action_names=arrays["action_names"],
        calibration_thresholds=calibrator.thresholds,
        calibration_values=calibrator.values,
        metadata_json=np.asarray(json.dumps(metadata, sort_keys=True)),
    )
    if model_bundle_path is not None:
        bundle_payload: dict[str, np.ndarray] = {
            "structured_mean": normalization.structured_mean,
            "structured_std": normalization.structured_std,
            "visual_mean": normalization.visual_mean,
            "visual_std": normalization.visual_std,
            "action_names": arrays["action_names"],
            "metadata_json": np.asarray(
                json.dumps(
                    {
                        "bundle_schema": "frozen-development-outcome-models-v1",
                        "dataset_sha256": dataset_manifest["dataset_sha256"],
                        "training_seed": seed,
                        "model_modes": list(MODEL_MODES),
                        "test_rows_accessed": False,
                    },
                    sort_keys=True,
                )
            ),
        }
        for mode, (mode_weights, mode_calibrator, _, _) in fitted.items():
            bundle_payload[f"{mode}_weights"] = mode_weights
            bundle_payload[f"{mode}_calibration_thresholds"] = mode_calibrator.thresholds
            bundle_payload[f"{mode}_calibration_values"] = mode_calibrator.values
        model_bundle_path = Path(model_bundle_path)
        model_bundle_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(model_bundle_path, **bundle_payload)
    report = {
        "report_version": "jepa-route-development-benchmark-v1",
        "dataset": str(Path(dataset_path).name),
        "dataset_sha256": dataset_manifest["dataset_sha256"],
        "checkpoint": str(checkpoint_path.name),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "selection_split": "tuning",
        "calibration_split": "calibration",
        "evaluation_split": "validation",
        "split_unit": "complete_episode",
        "seed": seed,
        "test_rows_accessed": False,
        "validation_episode_count": int(len(np.unique(episode_ids))),
        "validation_outcome_counts": {
            "positive": int(arrays["outcomes"][validation_rows].sum()),
            "negative": int(len(validation_rows) - arrays["outcomes"][validation_rows].sum()),
        },
        "precision_adequate_for_claims": bool(len(np.unique(episode_ids)) >= 20),
        "models": results,
        "paired_episode_bootstrap": paired,
        "interpretation_boundary": (
            "development evidence on controlled synthetic clips; it establishes integration and "
            "channel sensitivity, not cross-domain or operational effectiveness"
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8"
    )
    return report


def evaluate_frozen_model_bundle(
    arrays: dict[str, np.ndarray],
    model_bundle_path: Path,
    *,
    shuffle_seed: int,
    bootstrap_seed: int,
) -> dict[str, object]:
    """Evaluate frozen development models on one externally authorized row set."""

    with np.load(model_bundle_path, allow_pickle=False) as payload:
        metadata = json.loads(str(payload["metadata_json"].item()))
        if metadata.get("bundle_schema") != "frozen-development-outcome-models-v1":
            raise ValueError("unsupported frozen outcome-model bundle")
        bundle = {name: payload[name].copy() for name in payload.files}
    if tuple(arrays["action_names"].astype(str)) != tuple(
        bundle["action_names"].astype(str)
    ):
        raise ValueError("held-out action schema does not match the frozen bundle")
    normalization = Normalization(
        structured_mean=bundle["structured_mean"],
        structured_std=bundle["structured_std"],
        visual_mean=bundle["visual_mean"],
        visual_std=bundle["visual_std"],
    )
    rows = np.arange(len(arrays["actions"]), dtype=np.int64)
    rng = np.random.default_rng(shuffle_seed)
    predictions: dict[str, np.ndarray] = {}
    results: dict[str, dict[str, object]] = {}
    for mode in MODEL_MODES:
        shuffled = (
            _shuffle_visual_by_episode(arrays, rows, rng)
            if mode == "fused_shuffled_visual"
            else None
        )
        design = _design(
            arrays,
            rows,
            normalization,
            mode,
            shuffled_visual=shuffled,
        )
        weights = bundle[f"{mode}_weights"]
        calibrator = IsotonicCalibrator(
            thresholds=bundle[f"{mode}_calibration_thresholds"],
            values=bundle[f"{mode}_calibration_values"],
        )
        prediction = _predict(design, weights)
        prediction[:, 0] = calibrator.transform(np.clip(prediction[:, 0], 0.0, 1.0))
        prediction[:, 2] = np.clip(prediction[:, 2], 0.0, 1.0)
        predictions[mode] = prediction
        results[mode] = {
            **_binary_metrics(prediction[:, 0], arrays["outcomes"]),
            **_regression_metrics(prediction, arrays["targets"]),
        }

    episode_ids = arrays["episode_ids"].astype(str)
    fused_brier = (predictions["fused"][:, 0] - arrays["outcomes"]) ** 2
    structured_brier = (
        predictions["structured"][:, 0] - arrays["outcomes"]
    ) ** 2
    shuffled_brier = (
        predictions["fused_shuffled_visual"][:, 0] - arrays["outcomes"]
    ) ** 2
    fused_mse = np.mean((predictions["fused"] - arrays["targets"]) ** 2, axis=1)
    structured_mse = np.mean(
        (predictions["structured"] - arrays["targets"]) ** 2, axis=1
    )
    shuffled_mse = np.mean(
        (predictions["fused_shuffled_visual"] - arrays["targets"]) ** 2,
        axis=1,
    )
    paired = {
        "fused_minus_structured_brier": _cluster_bootstrap_difference(
            fused_brier, structured_brier, episode_ids, seed=bootstrap_seed
        ),
        "fused_minus_structured_target_mse": _cluster_bootstrap_difference(
            fused_mse, structured_mse, episode_ids, seed=bootstrap_seed + 1
        ),
        "fused_minus_shuffled_visual_brier": _cluster_bootstrap_difference(
            fused_brier, shuffled_brier, episode_ids, seed=bootstrap_seed + 2
        ),
        "fused_minus_shuffled_visual_target_mse": _cluster_bootstrap_difference(
            fused_mse, shuffled_mse, episode_ids, seed=bootstrap_seed + 3
        ),
    }
    return {
        "models": results,
        "paired_episode_bootstrap": paired,
        "episode_count": int(len(np.unique(episode_ids))),
        "row_count": int(len(rows)),
        "model_bundle_sha256": sha256_file(model_bundle_path),
    }
