"""One-run execution and exact byte replay for Reference development artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trace_jepa.predictor import ActionPrefixPredictor, ToyActionPrefixPredictor
from trace_jepa.support import ArtifactLocator, safe_directory
from trace_reference.generation import generate_reference_scenario
from trace_reference.runtime import ReferenceMissionRun, build_reference_runtime
from trace_reference.validation import ReferenceCapacityEvaluation, evaluate_reference_capacity

from .artifacts import (
    ReferenceArtifactMismatchError,
    verify_reference_artifacts,
    verify_reference_input_inventory,
    write_reference_artifacts,
)
from .inventory import reference_source_tree_sha256
from .limits import REFERENCE_ARTIFACT_MAX_BYTES
from .models import ReferenceReplayManifest
from .specifications import ReferenceArtifactWriteRequest

_COMPARE_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ReferenceExecution:
    manifest: ReferenceReplayManifest
    run: ReferenceMissionRun
    capacity: ReferenceCapacityEvaluation


def _empty_output_root(output_root: Path) -> Path:
    root = safe_directory(
        output_root,
        declared_root=output_root,
        label="Reference execution output root",
    )
    if any(root.iterdir()):
        raise ReferenceArtifactMismatchError("Reference execution output root must be empty")
    return root


def _files_equal(first: Path, second: Path) -> bool:
    if first.stat().st_size != second.stat().st_size:
        return False
    with first.open("rb") as left, second.open("rb") as right:
        while True:
            first_chunk = left.read(_COMPARE_CHUNK_BYTES)
            second_chunk = right.read(_COMPARE_CHUNK_BYTES)
            if first_chunk != second_chunk:
                return False
            if not first_chunk:
                return True


def execute_reference_scenario(
    repository_root: Path,
    output_root: Path,
    *,
    seed: int,
    predictor: ActionPrefixPredictor | None = None,
) -> ReferenceExecution:
    """Generate, execute, evaluate, and materialize one nominal development scenario."""

    root = _empty_output_root(output_root)
    runtime_root = root / "runtime_store"
    runtime_root.mkdir()
    scenario = generate_reference_scenario(repository_root, seed=seed)
    selected_predictor = predictor or ToyActionPrefixPredictor()
    runtime_bundle = build_reference_runtime(
        scenario,
        runtime_root,
        predictor=selected_predictor,
    )
    run = runtime_bundle.runtime.run()
    capacity = evaluate_reference_capacity(scenario, run)
    manifest = write_reference_artifacts(
        ReferenceArtifactWriteRequest(
            repository_root=repository_root,
            output_root=root,
            scenario=scenario,
            run=run,
            runtime_bundle=runtime_bundle,
            capacity=capacity,
            predictor_provenance=selected_predictor.provenance(),
        )
    )
    return ReferenceExecution(manifest=manifest, run=run, capacity=capacity)


def verify_exact_reference_replay(
    repository_root: Path,
    *,
    trusted_reference_root: Path,
    reference_relative_path: Path,
    replay_output_root: Path,
    predictor: ActionPrefixPredictor | None = None,
) -> None:
    """Regenerate one verified bundle and compare every registered byte."""

    reference = verify_reference_artifacts(
        trusted_root=trusted_reference_root,
        bundle_relative_path=reference_relative_path,
    )
    if reference.source_tree_sha256 != reference_source_tree_sha256(repository_root):
        raise ReferenceArtifactMismatchError(
            "current source tree differs from the Reference replay manifest"
        )
    verify_reference_input_inventory(repository_root, reference)
    replay = execute_reference_scenario(
        repository_root,
        replay_output_root,
        seed=reference.seed,
        predictor=predictor,
    )
    if replay.manifest != reference:
        raise ReferenceArtifactMismatchError("Reference replay manifest differs")
    reference_bundle = safe_directory(
        trusted_reference_root / reference_relative_path,
        declared_root=trusted_reference_root,
        label="Reference replay bundle",
    )
    for descriptor in reference.artifacts:
        reference_path = ArtifactLocator(
            root=reference_bundle,
            relative_name=Path(descriptor.file_name),
            maximum_bytes=REFERENCE_ARTIFACT_MAX_BYTES,
            label=f"Reference replay source {descriptor.name}",
        ).resolve()
        replay_path = ArtifactLocator(
            root=replay_output_root,
            relative_name=Path(descriptor.file_name),
            maximum_bytes=REFERENCE_ARTIFACT_MAX_BYTES,
            label=f"Reference replay result {descriptor.name}",
        ).resolve()
        if not _files_equal(reference_path, replay_path):
            raise ReferenceArtifactMismatchError(
                f"Reference replay is not byte-identical: {descriptor.file_name}"
            )
    reference_manifest_path = ArtifactLocator(
        root=reference_bundle,
        relative_name=Path("manifest.json"),
        maximum_bytes=4 * 1024 * 1024,
        label="Reference source replay manifest",
    ).resolve()
    replay_manifest_path = ArtifactLocator(
        root=replay_output_root,
        relative_name=Path("manifest.json"),
        maximum_bytes=4 * 1024 * 1024,
        label="Reference result replay manifest",
    ).resolve()
    if not _files_equal(reference_manifest_path, replay_manifest_path):
        raise ReferenceArtifactMismatchError("Reference replay manifest bytes differ")
