from __future__ import annotations

import json
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np

from trace_jepa.util import sha256_file, sha256_value
from trace_jepa.worldmodels.adapters import LinearActionHead
from trace_jepa.worldmodels.simulator_observations import validate_test_authorization


FROZEN_SOURCE_FILES = (
    "configs/experiments/dinowm_development_confirmation_v1.yaml",
    "scripts/build_dinowm_transition_dataset.py",
    "scripts/build_dinowm_runtime_cache.py",
    "scripts/encode_dinowm_transitions.py",
    "scripts/freeze_dinowm_test_manifest.py",
    "scripts/run_dinowm_heldout.py",
    "scripts/train_dinowm_confirmation.py",
    "src/trace_jepa/perception/dinov2.py",
    "src/trace_jepa/util.py",
    "src/trace_jepa/worldmodels/__init__.py",
    "src/trace_jepa/worldmodels/adapters.py",
    "src/trace_jepa/worldmodels/calibration.py",
    "src/trace_jepa/worldmodels/dataset.py",
    "src/trace_jepa/worldmodels/dinowm.py",
    "src/trace_jepa/worldmodels/dinowm_dataset.py",
    "src/trace_jepa/worldmodels/dinowm_freeze.py",
    "src/trace_jepa/worldmodels/dinowm_io.py",
    "src/trace_jepa/worldmodels/dinowm_runtime.py",
    "src/trace_jepa/worldmodels/dinowm_training.py",
    "src/trace_jepa/worldmodels/encoding.py",
    "src/trace_jepa/worldmodels/simulator_dataset.py",
    "src/trace_jepa/worldmodels/simulator_observations.py",
    "src/trace_jepa/worldmodels/training.py",
    "src/trace_jepa/worldmodels/factory.py",
    "src/trace_jepa/worldmodels/contracts.py",
    "src/trace_jepa/workbench/cli.py",
)


def _git_head(repository_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def freeze_dinowm_test_manifest(
    repository_root: Path,
    output_path: Path,
    *,
    protocol_path: Path,
    transition_dataset_path: Path,
    development_report_path: Path,
    dynamics_checkpoint_path: Path,
    outcome_checkpoint_path: Path,
    outcome_bundle_path: Path,
    current_control_bundle_path: Path,
    test_data_seed: int,
    test_split_seed: int,
    test_episode_count: int,
) -> dict[str, object]:
    """Freeze exact development evidence and activate the prospectively gated test."""

    repository_root = Path(repository_root).resolve()
    development_report = json.loads(Path(development_report_path).read_text())
    if development_report.get("gate", {}).get("passed") is not True:
        raise ValueError("DINO-WM development gate did not pass")
    if development_report.get("test_rows_accessed") is not False:
        raise ValueError("development report does not prove test isolation")
    if development_report["artifacts"]["dynamics_checkpoint_sha256"] != sha256_file(
        dynamics_checkpoint_path
    ):
        raise ValueError("development dynamics checkpoint hash mismatch")
    if development_report["artifacts"]["outcome_checkpoint_sha256"] != sha256_file(
        outcome_checkpoint_path
    ):
        raise ValueError("development outcome checkpoint hash mismatch")
    if development_report["artifacts"].get(
        "outcome_model_bundle_sha256"
    ) != sha256_file(outcome_bundle_path):
        raise ValueError("development outcome-model bundle hash mismatch")
    if development_report["artifacts"].get(
        "current_control_bundle_sha256"
    ) != sha256_file(current_control_bundle_path):
        raise ValueError("development current-control bundle hash mismatch")
    transition_manifest_path = Path(transition_dataset_path).with_suffix(
        Path(transition_dataset_path).suffix + ".json"
    )
    transition_manifest = json.loads(transition_manifest_path.read_text())
    if transition_manifest.get("test_included") is not False:
        raise ValueError("development transition dataset contains test rows")
    head = LinearActionHead.load(outcome_checkpoint_path)

    source_hashes = {
        relative: sha256_file(repository_root / relative)
        for relative in FROZEN_SOURCE_FILES
    }
    try:
        import torch

        torch_version = torch.__version__
    except ImportError:  # pragma: no cover - freeze requires the ML environment
        torch_version = "unavailable"
    manifest = {
        "manifest_version": "flood-sar-dinowm-test-freeze-v1",
        "protocol_sha256": sha256_file(protocol_path),
        "code_commit": _git_head(repository_root),
        "source_tree_sha256": sha256_value(source_hashes),
        "source_file_sha256": source_hashes,
        "dataset_manifest_sha256": sha256_file(transition_manifest_path),
        "development_dataset_sha256": transition_manifest["dataset_sha256"],
        "predictor_checkpoint_sha256": sha256_file(dynamics_checkpoint_path),
        "calibration_version": str(head.metadata["calibration_version"]),
        "encoder_checkpoint_sha256": str(
            transition_manifest["encoder"]["checkpoint_sha256"]
        ),
        "outcome_checkpoint_sha256": sha256_file(outcome_checkpoint_path),
        "outcome_model_bundle_sha256": sha256_file(outcome_bundle_path),
        "current_control_bundle_sha256": sha256_file(current_control_bundle_path),
        "development_report_sha256": sha256_file(development_report_path),
        "test_data_seed": test_data_seed,
        "test_split_seed": test_split_seed,
        "test_episode_count": test_episode_count,
        "test_shuffle_seed": 20260803,
        "test_bootstrap_seed": 20260804,
        "no_post_open_tuning": True,
        "software_environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "numpy": np.__version__,
            "torch": torch_version,
        },
        "test_authorized": True,
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    validate_test_authorization(output_path)
    return manifest


def verify_dinowm_freeze_manifest(repository_root: Path, manifest_path: Path) -> dict[str, object]:
    manifest = validate_test_authorization(manifest_path)
    repository_root = Path(repository_root).resolve()
    actual_source_hashes = {
        relative: sha256_file(repository_root / relative)
        for relative in manifest["source_file_sha256"]
    }
    if actual_source_hashes != manifest["source_file_sha256"]:
        raise ValueError("source files differ from the frozen DINO-WM test manifest")
    if sha256_value(actual_source_hashes) != manifest["source_tree_sha256"]:
        raise ValueError("frozen DINO-WM source-tree digest mismatch")
    return manifest
