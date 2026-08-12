"""Deterministic publication bundle construction from verified replay artifacts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from trace_jepa.support import (
    ArtifactLocator,
    atomic_write_bytes,
    canonical_json_bytes,
    safe_directory,
    safe_output_file,
    sha256_file,
)

from .figures import capacity_figure, timeline_figure, topology_figure, trace_flow_figure
from .inputs import ReferencePublicationInputs, load_reference_publication_inputs
from .models import (
    ReferencePublicationArtifact,
    ReferencePublicationManifest,
    ReferencePublicationResultTable,
)

_MAX_PUBLICATION_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class _PublicationSpec:
    name: str
    file_name: str
    media_type: str
    payload: bytes


def _destination(root: Path, file_name: str) -> Path:
    relative = Path(file_name)
    if relative.is_absolute() or len(relative.parts) != 1 or relative.name != file_name:
        raise ValueError(f"unsafe Reference publication file name: {file_name!r}")
    return safe_output_file(
        root / relative,
        declared_root=root,
        label="Reference publication artifact",
    )


def _result_table(values: ReferencePublicationInputs) -> ReferencePublicationResultTable:
    summary = values.source_summary
    capacity = values.capacity
    confirmed = sum(
        item.status == "confirmed" for artifact in values.reconciliations for item in artifact.links
    )
    suspected = sum(
        item.status == "suspected" for artifact in values.reconciliations for item in artifact.links
    )
    body = {
        "schema_version": "delta-reference-publication-result-table-v1",
        "scientific_status": "development-descriptive-not-validation-evidence",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "seed": summary.seed,
        "report_count": summary.report_count,
        "evaluation_report_count": summary.evaluation_report_count,
        "truth_incident_count": summary.truth_incident_count,
        "evaluation_truth_incident_count": summary.evaluation_truth_incident_count,
        "decision_count": len(values.decisions),
        "allocation_count": sum(item.disposition == "allocated" for item in values.decisions),
        "refusal_count": sum(item.disposition == "refused" for item in values.decisions),
        "acquisition_request_count": sum(
            item.disposition == "acquisition-requested" for item in values.decisions
        ),
        "completed_within_window_count": sum(
            item.status == "completed_within_window" for item in values.outcomes
        ),
        "active_at_censoring_count": sum(
            item.status == "active_at_scenario_censoring" for item in values.outcomes
        ),
        "confirmed_visible_link_count": confirmed,
        "suspected_visible_link_count": suspected,
        "peak_finite_strict_concurrent_load_ratio_milli": (
            capacity.peak_finite_strict_concurrent_load_ratio_milli
        ),
        "strict_unserviceable_window_count": capacity.strict_unserviceable_window_count,
        "peak_finite_uncapped_compatible_load_ratio_milli": (
            capacity.peak_finite_uncapped_compatible_load_ratio_milli
        ),
        "peak_finite_historical_normalized_coverable_load_index_milli": (
            capacity.peak_finite_historical_normalized_coverable_load_index_milli
        ),
        "peak_finite_residual_strict_pressure_ratio_milli": (
            capacity.peak_finite_residual_strict_pressure_ratio_milli
        ),
        "residual_unserviceable_window_count": capacity.residual_unserviceable_window_count,
    }
    return ReferencePublicationResultTable(
        **body,
        table_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )


def _specifications(values: ReferencePublicationInputs) -> tuple[_PublicationSpec, ...]:
    table = _result_table(values)
    return (
        _PublicationSpec(
            "capacity_sensitivity_figure",
            "capacity_sensitivity.svg",
            "image/svg+xml",
            capacity_figure(values),
        ),
        _PublicationSpec(
            "result_table",
            "result_table.json",
            "application/json",
            canonical_json_bytes(table.model_dump(mode="json")),
        ),
        _PublicationSpec(
            "timeline_figure",
            "timeline.svg",
            "image/svg+xml",
            timeline_figure(values),
        ),
        _PublicationSpec(
            "topology_figure",
            "topology.svg",
            "image/svg+xml",
            topology_figure(values),
        ),
        _PublicationSpec(
            "trace_flow_figure",
            "trace_flow.svg",
            "image/svg+xml",
            trace_flow_figure(values),
        ),
    )


def publish_reference_bundle(
    *,
    trusted_reference_root: Path,
    reference_relative_path: Path,
    output_root: Path,
) -> ReferencePublicationManifest:
    """Verify a replay bundle and regenerate all development publication artifacts."""

    output = safe_directory(
        output_root,
        declared_root=output_root,
        label="Reference publication output root",
    )
    if any(output.iterdir()):
        raise ValueError("Reference publication output root must be empty")
    values = load_reference_publication_inputs(
        trusted_reference_root=trusted_reference_root,
        reference_relative_path=reference_relative_path,
    )
    artifacts = []
    for spec in _specifications(values):
        if len(spec.payload) > _MAX_PUBLICATION_BYTES:
            raise ValueError(f"Reference publication artifact is oversized: {spec.file_name}")
        atomic_write_bytes(
            _destination(output, spec.file_name),
            spec.payload,
            root=output,
            label=spec.name,
        )
        artifacts.append(
            ReferencePublicationArtifact(
                name=spec.name,
                file_name=spec.file_name,
                media_type=spec.media_type,
                sha256=hashlib.sha256(spec.payload).hexdigest(),
                byte_length=len(spec.payload),
            )
        )
    body = {
        "schema_version": "delta-reference-publication-manifest-v1",
        "scientific_status": "development-descriptive-not-validation-evidence",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "source_replay_manifest_sha256": values.replay_manifest_sha256,
        "source_replay_manifest_digest": values.replay_manifest.manifest_digest,
        "artifacts": [item.model_dump(mode="json") for item in artifacts],
    }
    manifest = ReferencePublicationManifest(
        **body,
        manifest_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )
    atomic_write_bytes(
        _destination(output, "publication_manifest.json"),
        canonical_json_bytes(manifest.model_dump(mode="json")),
        root=output,
        label="Reference publication manifest",
    )
    return manifest


def verify_reference_publication(
    *,
    trusted_root: Path,
    publication_relative_path: Path,
) -> ReferencePublicationManifest:
    """Verify every artifact in one caller-rooted publication bundle."""

    root = safe_directory(
        trusted_root / publication_relative_path,
        declared_root=trusted_root,
        label="Reference publication bundle",
    )
    manifest_path = ArtifactLocator(
        root=root,
        relative_name=Path("publication_manifest.json"),
        maximum_bytes=4 * 1024 * 1024,
        label="Reference publication manifest",
    ).resolve()
    manifest = ReferencePublicationManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    for descriptor in manifest.artifacts:
        path = ArtifactLocator(
            root=root,
            relative_name=Path(descriptor.file_name),
            maximum_bytes=_MAX_PUBLICATION_BYTES,
            label=f"Reference publication artifact {descriptor.name}",
        ).resolve()
        if path.stat().st_size != descriptor.byte_length or sha256_file(path) != descriptor.sha256:
            raise ValueError(f"Reference publication artifact differs: {descriptor.file_name}")
    return manifest
