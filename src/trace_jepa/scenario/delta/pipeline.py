from __future__ import annotations

from pathlib import Path

from trace_jepa.predictor import ActionPrefixPredictor
from trace_jepa.scenario.delta.artifacts import (
    ArtifactMismatchError,
    ReplayManifest,
    source_tree_sha256,
    verify_scenario_artifacts,
    write_scenario_artifacts,
)
from trace_jepa.scenario.delta.generator import generate_delta_small
from trace_jepa.scenario.delta.runner import DeltaRunResult, run_delta_small


class DeltaExecution:
    def __init__(self, manifest: ReplayManifest, run_result: DeltaRunResult) -> None:
        self.manifest = manifest
        self.run_result = run_result


def execute_delta_small(
    config_path: Path,
    geography_path: Path,
    policy_path: Path,
    output_root: Path,
    predictor: ActionPrefixPredictor,
    *,
    recorded_git_commit: str | None = None,
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
    )
    verify_scenario_artifacts(output_root)
    return DeltaExecution(manifest, run_result)


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
    replay = execute_delta_small(
        config_path,
        geography_path,
        policy_path,
        replay_root,
        predictor,
        recorded_git_commit=reference_manifest.git_commit,
    )
    if reference_manifest != replay.manifest:
        raise ArtifactMismatchError("replay manifest differs from the reference manifest")
    file_names = [descriptor.file_name for descriptor in reference_manifest.artifacts] + [
        "manifest.json"
    ]
    for file_name in file_names:
        if (reference_root / file_name).read_bytes() != (replay_root / file_name).read_bytes():
            raise ArtifactMismatchError(f"replay is not byte-identical: {file_name}")
