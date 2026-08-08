from __future__ import annotations

import json
import os
from pathlib import Path

from trace_jepa.predictor import ActionPrefixPredictor
from trace_jepa.scenario.delta.artifacts import (
    ArtifactMismatchError,
    ReplayManifest,
    canonical_json_bytes,
    current_git_commit,
    source_tree_sha256,
    verify_scenario_artifacts,
    write_scenario_artifacts,
)
from trace_jepa.scenario.delta.environment import execution_receipt
from trace_jepa.scenario.delta.generator import generate_delta_small
from trace_jepa.scenario.delta.runner import DeltaRunResult, run_delta_small


class DeltaExecution:
    def __init__(
        self,
        manifest: ReplayManifest,
        run_result: DeltaRunResult,
        receipt: dict[str, object] | None,
    ) -> None:
        self.manifest = manifest
        self.run_result = run_result
        self.execution_receipt = receipt


def execute_delta_small(
    config_path: Path,
    geography_path: Path,
    policy_path: Path,
    output_root: Path,
    predictor: ActionPrefixPredictor,
    *,
    recorded_git_commit: str | None = None,
    validation_report_path: Path | None = None,
    ci_run_id: str | None = None,
) -> DeltaExecution:
    scenario = generate_delta_small(config_path, geography_path)
    run_result = run_delta_small(scenario, predictor, policy_path)
    package_root = Path(__file__).resolve().parents[2]
    manifest = write_scenario_artifacts(
        scenario,
        run_result,
        policy_path,
        predictor.provenance(),
        geography_path,
        output_root,
        package_root,
        recorded_git_commit=recorded_git_commit,
        validation_report_path=validation_report_path,
    )
    verify_scenario_artifacts(output_root)
    receipt: dict[str, object] | None = None
    if manifest.generator_version in {
        "delta-small-generator-v7",
        "delta-small-generator-v8",
    }:
        repository_root = package_root.parents[1]
        receipt = execution_receipt(
            repository_root / "data/scenario/delta/environment/python311_linux_amd64_v1.json",
            repository_root / "requirements-delta-python311.lock",
            source_commit=recorded_git_commit or current_git_commit(repository_root),
            ci_run_id=ci_run_id or os.environ.get("GITHUB_RUN_ID"),
            execution_role=os.environ.get("TRACE_DELTA_EXECUTION_ROLE"),
        )
        receipt_path = output_root / "execution_receipt.json"
        if receipt_path.is_symlink():
            raise ArtifactMismatchError(
                f"execution receipt path must not be a symlink: {receipt_path}"
            )
        if receipt_path.parent.resolve(strict=True) != output_root.resolve(strict=True):
            raise ArtifactMismatchError("execution receipt path escapes output root")
        receipt_path.write_bytes(canonical_json_bytes(receipt))
    return DeltaExecution(manifest, run_result, receipt)


def verify_exact_replay(
    config_path: Path,
    geography_path: Path,
    policy_path: Path,
    reference_root: Path,
    replay_root: Path,
    predictor: ActionPrefixPredictor,
) -> None:
    reference_manifest = verify_scenario_artifacts(reference_root)
    package_root = Path(__file__).resolve().parents[2]
    current_source_tree = source_tree_sha256(package_root)
    if current_source_tree != reference_manifest.source_tree_sha256:
        raise ArtifactMismatchError(
            "current source tree differs from the source bound by the reference manifest"
        )
    recorded_commit = reference_manifest.git_commit
    if reference_manifest.schema_version in {
        "delta-replay-manifest-v4",
        "delta-replay-manifest-v5",
        "delta-replay-manifest-v6",
    }:
        receipt_path = reference_root / "execution_receipt.json"
        if receipt_path.is_symlink() or not receipt_path.is_file():
            raise ArtifactMismatchError("modern reference is missing a safe execution receipt")
        try:
            receipt_payload = json.loads(receipt_path.read_text("utf-8"))
            recorded_commit = str(receipt_payload["source_commit"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ArtifactMismatchError("modern reference execution receipt is invalid") from exc
    replay = execute_delta_small(
        config_path,
        geography_path,
        policy_path,
        replay_root,
        predictor,
        recorded_git_commit=recorded_commit,
    )
    if reference_manifest != replay.manifest:
        raise ArtifactMismatchError("replay manifest differs from the reference manifest")
    file_names = [descriptor.file_name for descriptor in reference_manifest.artifacts] + [
        "manifest.json"
    ]
    for file_name in file_names:
        if (reference_root / file_name).read_bytes() != (replay_root / file_name).read_bytes():
            raise ArtifactMismatchError(f"replay is not byte-identical: {file_name}")
