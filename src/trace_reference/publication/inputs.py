"""Safe typed loading of the minimal verified Reference publication surface."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from trace_jepa.support import ArtifactLocator, sha256_file
from trace_reference.decision import ReferenceServiceOutcome
from trace_reference.domain import (
    ReferenceMissionDecision,
    ReferencePhysicalScenario,
    ReferencePublicResourceCatalog,
    ReferenceRawObservationScenario,
    ReferenceResourceActivationSchedule,
)
from trace_reference.geography import ReferenceGeographyCatalog
from trace_reference.provenance import (
    ReferenceReplayManifest,
    ReferenceResultSummary,
    verify_reference_artifacts,
)
from trace_reference.reconciliation import ReferenceReconciliationArtifact
from trace_reference.validation import ReferenceCapacityEvaluation

_MAX_ARTIFACT_BYTES = 128 * 1024 * 1024


@dataclass(frozen=True)
class ReferencePublicationInputs:
    replay_manifest: ReferenceReplayManifest
    replay_manifest_sha256: str
    geography: ReferenceGeographyCatalog
    physical: ReferencePhysicalScenario
    reports: ReferenceRawObservationScenario
    resources: ReferencePublicResourceCatalog
    activations: ReferenceResourceActivationSchedule
    decisions: tuple[ReferenceMissionDecision, ...]
    outcomes: tuple[ReferenceServiceOutcome, ...]
    reconciliations: tuple[ReferenceReconciliationArtifact, ...]
    capacity: ReferenceCapacityEvaluation
    source_summary: ReferenceResultSummary


def _artifact_path(
    bundle_root: Path,
    manifest: ReferenceReplayManifest,
    name: str,
) -> Path:
    descriptor = next((item for item in manifest.artifacts if item.name == name), None)
    if descriptor is None:
        raise ValueError(f"Reference publication source artifact is absent: {name}")
    return ArtifactLocator(
        root=bundle_root,
        relative_name=Path(descriptor.file_name),
        maximum_bytes=_MAX_ARTIFACT_BYTES,
        label=f"Reference publication source {name}",
    ).resolve()


def load_reference_publication_inputs(
    *,
    trusted_reference_root: Path,
    reference_relative_path: Path,
) -> ReferencePublicationInputs:
    """Verify the complete replay bundle before opening publication projections."""

    manifest = verify_reference_artifacts(
        trusted_root=trusted_reference_root,
        bundle_relative_path=reference_relative_path,
    )
    bundle_root = (trusted_reference_root / reference_relative_path).resolve(strict=True)
    manifest_path = ArtifactLocator(
        root=bundle_root,
        relative_name=Path("manifest.json"),
        maximum_bytes=4 * 1024 * 1024,
        label="Reference replay manifest",
    ).resolve()
    return ReferencePublicationInputs(
        replay_manifest=manifest,
        replay_manifest_sha256=sha256_file(manifest_path),
        geography=ReferenceGeographyCatalog.model_validate_json(
            _artifact_path(bundle_root, manifest, "geography").read_text(encoding="utf-8")
        ),
        physical=ReferencePhysicalScenario.model_validate_json(
            _artifact_path(bundle_root, manifest, "physical_truth").read_text(encoding="utf-8")
        ),
        reports=ReferenceRawObservationScenario.model_validate_json(
            _artifact_path(bundle_root, manifest, "raw_reports").read_text(encoding="utf-8")
        ),
        resources=ReferencePublicResourceCatalog.model_validate_json(
            _artifact_path(bundle_root, manifest, "resource_catalog").read_text(encoding="utf-8")
        ),
        activations=ReferenceResourceActivationSchedule.model_validate_json(
            _artifact_path(bundle_root, manifest, "coordination_activations").read_text(
                encoding="utf-8"
            )
        ),
        decisions=TypeAdapter(tuple[ReferenceMissionDecision, ...]).validate_json(
            _artifact_path(bundle_root, manifest, "decisions").read_text(encoding="utf-8")
        ),
        outcomes=TypeAdapter(tuple[ReferenceServiceOutcome, ...]).validate_json(
            _artifact_path(bundle_root, manifest, "outcomes").read_text(encoding="utf-8")
        ),
        reconciliations=TypeAdapter(tuple[ReferenceReconciliationArtifact, ...]).validate_json(
            _artifact_path(bundle_root, manifest, "reconciliations").read_text(encoding="utf-8")
        ),
        capacity=ReferenceCapacityEvaluation.model_validate_json(
            _artifact_path(bundle_root, manifest, "capacity_evaluation").read_text(encoding="utf-8")
        ),
        source_summary=ReferenceResultSummary.model_validate_json(
            _artifact_path(bundle_root, manifest, "result_summary").read_text(encoding="utf-8")
        ),
    )
