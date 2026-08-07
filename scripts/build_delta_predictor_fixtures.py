from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from trace_jepa.predictor import write_deterministic_feature_cache, write_deterministic_npz
from trace_jepa.scenario.delta.artifacts import canonical_json_bytes, sha256_file

ACTION_NAMES = np.asarray(
    [
        "dispatch_rescue_boat",
        "deploy_ground_team",
        "perform_welfare_check",
        "inspect_levee",
    ]
)
ENCODER_VERSION = "ci-vjepa-feature-encoder-v1"
ENCODER_HASH = "a" * 64
OBSERVATION_HASH = "c" * 64


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "tests/fixtures/predictor"
    root.mkdir(parents=True, exist_ok=True)
    feature_path = root / "vjepa_ci_feature.npz"
    write_deterministic_feature_cache(
        feature_path,
        feature=np.asarray([0.1, 0.2, 0.3], dtype=np.float32),
        observation_sha256=OBSERVATION_HASH,
        encoder_version=ENCODER_VERSION,
        encoder_checkpoint_hash=ENCODER_HASH,
    )
    structured_dimension = 11 + len(ACTION_NAMES)
    input_dimension = structured_dimension + 3
    metadata = {
        "predictor_version": "vjepa-ci-flood-head-v1",
        "calibration_version": "vjepa-ci-calibration-v1",
        "calibration_hash": "b" * 64,
        "training_snapshot": "ci-project-owned-synthetic-no-effectiveness-claim",
        "encoder_version": ENCODER_VERSION,
        "encoder_checkpoint_hash": ENCODER_HASH,
        "feature_schema_version": "action-prefix-features-v2",
        "action_schema_version": "delta-response-actions-v2",
    }
    head_path = root / "vjepa_ci_head.npz"
    write_deterministic_npz(
        head_path,
        {
            "weights": np.zeros((input_dimension, 7), dtype=np.float64),
            "bias": np.asarray([1.5, 6.8, -1.5, 0.2, 2.0, -2.0, -2.0]),
            "feature_mean": np.zeros(input_dimension, dtype=np.float64),
            "feature_std": np.ones(input_dimension, dtype=np.float64),
            "action_names": ACTION_NAMES,
            "metadata_json": np.asarray(json.dumps(metadata, sort_keys=True)),
        },
    )
    manifest = {
        "schema_version": "delta-predictor-ci-fixtures-v1",
        "qualification_status": "unqualified-test-fixture",
        "claims_limit": "loader-and-governance-tests-only",
        "encoder_version": ENCODER_VERSION,
        "encoder_checkpoint_hash": ENCODER_HASH,
        "feature_schema_version": "vjepa-frozen-feature-v1",
        "observation_sha256": OBSERVATION_HASH,
        "artifacts": {
            feature_path.name: sha256_file(feature_path),
            head_path.name: sha256_file(head_path),
        },
    }
    (root / "manifest.json").write_bytes(canonical_json_bytes(manifest))


if __name__ == "__main__":
    main()
