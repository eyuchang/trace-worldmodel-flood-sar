import json

import numpy as np
import pytest

from trace_jepa.util import sha256_file
from trace_jepa.worldmodels.dinowm_training import (
    DINOWMTrainingConfig,
    paired_episode_interval,
    run_dinowm_development_confirmation,
    run_dinowm_heldout_evaluation,
)
from trace_jepa.worldmodels.dataset import load_feature_dataset
from trace_jepa.worldmodels.training import evaluate_frozen_model_bundle


pytest.importorskip("torch")


def _write_synthetic_transition_dataset(path):
    rng = np.random.default_rng(9)
    episode_count = 100
    episode_signal = rng.normal(size=episode_count)
    current = np.repeat(rng.normal(size=(episode_count, 4, 6)), 2, axis=0).astype(np.float32)
    actions = np.tile(np.asarray([0, 1], dtype=np.int64), episode_count)
    action_delta = np.zeros_like(current)
    action_delta[:, :, 0] = np.where(actions[:, None] == 0, 0.25, -0.25)
    future = current + action_delta
    structured = rng.normal(size=(episode_count * 2, 5)).astype(np.float32)
    risk = np.repeat(episode_signal, 2) + 0.35 * actions
    outcomes = (risk < 0.0).astype(np.int64)
    targets = np.column_stack(
        [outcomes, 0.3 + 0.1 * actions, 1.0 / (1.0 + np.exp(-risk)), 0.5 - 0.1 * actions]
    ).astype(np.float32)
    episode_ids = np.repeat(
        np.asarray([f"episode-{index:03d}" for index in range(episode_count)]), 2
    )
    split_by_episode = np.asarray(
        ["train"] * 50 + ["tuning"] * 15 + ["calibration"] * 15 + ["validation"] * 20
    )
    splits = np.repeat(split_by_episode, 2)
    np.savez_compressed(
        path,
        current_latents=current.astype(np.float16),
        next_latents=future.astype(np.float16),
        structured=structured,
        actions=actions,
        targets=targets,
        outcomes=outcomes,
        episode_ids=episode_ids.astype("U64"),
        splits=splits.astype("U16"),
        current_observation_hashes=np.asarray(["a" * 64] * len(actions)),
        next_observation_hashes=np.asarray(["b" * 64] * len(actions)),
        action_names=np.asarray(["dispatch_rescue_boat", "evacuate_to_safety"]),
        target_names=np.asarray(["success", "arrival", "hazard", "resource"]),
    )
    manifest = {
        "dataset_sha256": sha256_file(path),
        "study_partition": "development",
        "episode_count": episode_count,
        "transition_count": len(actions),
        "split_episode_counts": {
            split: int(np.sum(split_by_episode == split))
            for split in ("train", "tuning", "calibration", "validation")
        },
        "test_included": False,
        "encoder": {"version": "synthetic", "checkpoint_sha256": "none"},
    }
    path.with_suffix(".npz.json").write_text(json.dumps(manifest))


def test_dinowm_confirmation_trains_without_opening_test(tmp_path):
    dataset = tmp_path / "transitions.npz"
    _write_synthetic_transition_dataset(dataset)
    report = run_dinowm_development_confirmation(
        dataset,
        tmp_path / "output",
        config=DINOWMTrainingConfig(
            predictor_dim=8,
            depth=1,
            heads=2,
            mlp_dim=16,
            dropout=0.0,
            learning_rate=0.01,
            batch_size=32,
            microbatch_size=8,
            max_epochs=30,
            early_stopping_patience=5,
            seed=17,
            bootstrap_seed=18,
            bootstrap_replicates=100,
        ),
    )
    assert report["test_rows_accessed"] is False
    assert report["dynamics"]["validation"]["predicted_future_mse"] < report[
        "dynamics"
    ]["validation"]["persistence_mse"]
    assert (tmp_path / "output" / "dinowm_development_confirmation_report.json").is_file()
    outcome_arrays, _ = load_feature_dataset(
        tmp_path / "output" / "dinowm_predicted_future_outcomes_v1.npz"
    )
    validation = outcome_arrays["splits"].astype(str) == "validation"
    heldout_like = {
        name: values[validation]
        for name, values in outcome_arrays.items()
        if name not in {"action_names", "target_names"}
    }
    heldout_like["action_names"] = outcome_arrays["action_names"]
    heldout_like["target_names"] = outcome_arrays["target_names"]
    frozen = evaluate_frozen_model_bundle(
        heldout_like,
        tmp_path / "output" / "dinowm_outcome_models_development_v1.npz",
        shuffle_seed=19,
        bootstrap_seed=20,
    )
    assert frozen["models"]["fused"]["brier"] == pytest.approx(
        report["predicted_future_outcomes"]["models"]["fused"]["brier"]
    )

    transition_arrays = dict(np.load(dataset, allow_pickle=False))
    transition_arrays["splits"] = np.asarray(
        ["test"] * len(transition_arrays["actions"]), dtype="U16"
    )
    test_dataset = tmp_path / "test_transitions.npz"
    np.savez_compressed(test_dataset, **transition_arrays)
    test_manifest = {
        "dataset_sha256": sha256_file(test_dataset),
        "study_partition": "test",
        "episode_count": 100,
        "transition_count": 200,
        "data_seed": 101,
        "split_seed": 102,
        "test_included": True,
        "encoder": {"version": "synthetic", "checkpoint_sha256": "none"},
    }
    test_dataset.with_suffix(".npz.json").write_text(json.dumps(test_manifest))
    result_dir = tmp_path / "output"
    freeze = {
        "manifest_version": "flood-sar-dinowm-test-freeze-v1",
        "protocol_sha256": "protocol",
        "code_commit": "commit",
        "dataset_manifest_sha256": "development-manifest",
        "predictor_checkpoint_sha256": sha256_file(
            result_dir / "dinowm_dynamics_development_v1.pt"
        ),
        "calibration_version": "calibration",
        "outcome_model_bundle_sha256": sha256_file(
            result_dir / "dinowm_outcome_models_development_v1.npz"
        ),
        "current_control_bundle_sha256": sha256_file(
            result_dir / "dinov2_current_outcome_models_control_v1.npz"
        ),
        "test_data_seed": 101,
        "test_split_seed": 102,
        "test_episode_count": 100,
        "test_shuffle_seed": 103,
        "test_bootstrap_seed": 104,
        "no_post_open_tuning": True,
        "test_authorized": True,
    }
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(json.dumps(freeze))
    heldout_path = tmp_path / "heldout.json"
    heldout = run_dinowm_heldout_evaluation(
        test_dataset,
        heldout_path,
        freeze_manifest=freeze,
        freeze_manifest_path=freeze_path,
        dynamics_checkpoint_path=result_dir / "dinowm_dynamics_development_v1.pt",
        outcome_bundle_path=result_dir / "dinowm_outcome_models_development_v1.npz",
        current_control_bundle_path=result_dir
        / "dinov2_current_outcome_models_control_v1.npz",
    )
    assert heldout["fitting_performed"] is False
    assert heldout["test_rows_accessed"] is True
    with pytest.raises(ValueError, match="already exists"):
        run_dinowm_heldout_evaluation(
            test_dataset,
            heldout_path,
            freeze_manifest=freeze,
            freeze_manifest_path=freeze_path,
            dynamics_checkpoint_path=result_dir
            / "dinowm_dynamics_development_v1.pt",
            outcome_bundle_path=result_dir
            / "dinowm_outcome_models_development_v1.npz",
            current_control_bundle_path=result_dir
            / "dinov2_current_outcome_models_control_v1.npz",
        )


def test_paired_episode_interval_resamples_independent_units():
    episode_ids = np.repeat(np.asarray([f"e{i}" for i in range(20)]), 2)
    first = np.zeros(40)
    second = np.ones(40)
    interval = paired_episode_interval(
        first,
        second,
        episode_ids,
        seed=1,
        replicates=100,
    )
    assert interval["estimate"] == -1.0
    assert interval["ci_high"] == -1.0
    assert interval["independent_episode_clusters"] == 20
