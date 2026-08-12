"""Bounded canonical artifact writing for the Reference development simulator."""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from pathlib import Path

from trace_jepa.support import (
    ArtifactLocator,
    atomic_write_bytes,
    canonical_json_bytes,
    safe_directory,
    safe_output_file,
    sha256_file,
)
from trace_reference.protocol import REFERENCE_PROTOCOL
from trace_reference.runtime import REFERENCE_ENVIRONMENT_VERSION, REFERENCE_POLICY_VERSION
from trace_reference.runtime.mission_state import (
    reference_runtime_profile_digest,
    reference_scenario_input_digest,
)

from .inventory import (
    reference_file_inputs,
    reference_source_tree_sha256,
    reference_value_input,
)
from .models import ReferenceArtifactDescriptor, ReferenceReplayManifest
from .specifications import (
    ReferenceArtifactSpec,
    ReferenceArtifactWriteRequest,
    build_reference_artifact_specs,
)

_MAX_ARTIFACT_BYTES = 128 * 1024 * 1024
_MANIFEST_NAME = "manifest.json"


class ReferenceArtifactMismatchError(RuntimeError):
    """Raised when a Reference artifact bundle fails a replay invariant."""


class ReferenceArtifactWriter:
    """Serialize each artifact independently to bound transient memory."""

    def __init__(self, output_root: Path) -> None:
        self.output_root = safe_directory(
            output_root,
            declared_root=output_root,
            label="Reference artifact output root",
        )

    def write(self, spec: ReferenceArtifactSpec) -> ReferenceArtifactDescriptor:
        path = _safe_artifact_destination(self.output_root, spec.file_name)
        payload = canonical_json_bytes(spec.value)
        if len(payload) > _MAX_ARTIFACT_BYTES:
            raise ReferenceArtifactMismatchError(
                f"Reference artifact exceeds the registered size bound: {spec.file_name}"
            )
        atomic_write_bytes(path, payload, root=self.output_root, label=spec.name)
        return ReferenceArtifactDescriptor(
            name=spec.name,
            file_name=spec.file_name,
            sha256=hashlib.sha256(payload).hexdigest(),
            byte_length=len(payload),
            contains_hidden_truth=spec.contains_hidden_truth,
        )


def _safe_artifact_destination(root: Path, file_name: str) -> Path:
    relative = Path(file_name)
    if relative.is_absolute() or len(relative.parts) != 1 or relative.name != file_name:
        raise ReferenceArtifactMismatchError(f"unsafe Reference artifact name: {file_name!r}")
    try:
        return safe_output_file(
            root / relative,
            declared_root=root,
            label="Reference artifact destination",
        )
    except ValueError as exc:
        raise ReferenceArtifactMismatchError(str(exc)) from exc


def write_reference_artifacts(request: ReferenceArtifactWriteRequest) -> ReferenceReplayManifest:
    """Write a complete deterministic development bundle and its self-checking manifest."""

    writer = ReferenceArtifactWriter(request.output_root)
    artifacts = tuple(writer.write(spec) for spec in build_reference_artifact_specs(request))
    provenance = request.predictor_provenance
    value_inputs = (
        reference_value_input(
            "predictor_provenance", provenance.predictor_version, provenance.model_dump(mode="json")
        ),
        reference_value_input(
            "protocol_registry",
            REFERENCE_PROTOCOL.approved_decision_set,
            asdict(REFERENCE_PROTOCOL),
        ),
        reference_value_input(
            "runtime_profile",
            REFERENCE_POLICY_VERSION,
            {
                "environment_version": REFERENCE_ENVIRONMENT_VERSION,
                "policy_version": REFERENCE_POLICY_VERSION,
            },
        ),
    )
    body = {
        "schema_version": REFERENCE_PROTOCOL.replay_manifest,
        "scientific_status": "development-only-not-validation-evidence",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "generator_version": REFERENCE_PROTOCOL.generator,
        "seed": request.scenario.truth.seed,
        "randomness_namespace": REFERENCE_PROTOCOL.randomness_namespace,
        "generation_order": REFERENCE_PROTOCOL.generation_order,
        "scenario_input_digest": reference_scenario_input_digest(request.scenario),
        "runtime_profile_digest": reference_runtime_profile_digest(None),
        "runtime_event_prefix_digest": request.run.event_prefix_digest,
        "trace_prefix_digest": request.run.trace_prefix_digest,
        "evidence_prefix_digest": request.run.evidence_prefix_digest,
        "commitment_prefix_digest": request.run.commitment_prefix_digest,
        "source_tree_sha256": reference_source_tree_sha256(request.repository_root),
        "file_inputs": [
            item.model_dump(mode="json") for item in reference_file_inputs(request.repository_root)
        ],
        "value_inputs": [item.model_dump(mode="json") for item in value_inputs],
        "artifacts": [item.model_dump(mode="json") for item in artifacts],
    }
    manifest = ReferenceReplayManifest(
        **body,
        manifest_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )
    atomic_write_bytes(
        _safe_artifact_destination(request.output_root, _MANIFEST_NAME),
        canonical_json_bytes(manifest.model_dump(mode="json")),
        root=request.output_root,
        label="Reference replay manifest",
    )
    return manifest


def verify_reference_artifacts(
    *,
    trusted_root: Path,
    bundle_relative_path: Path,
) -> ReferenceReplayManifest:
    """Verify a caller-rooted bundle without following symlink boundaries."""

    bundle_root = safe_directory(
        trusted_root / bundle_relative_path,
        declared_root=trusted_root,
        label="Reference replay bundle",
    )
    manifest_path = ArtifactLocator(
        root=bundle_root,
        relative_name=Path(_MANIFEST_NAME),
        maximum_bytes=4 * 1024 * 1024,
        label="Reference replay manifest",
    ).resolve()
    try:
        manifest = ReferenceReplayManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise ReferenceArtifactMismatchError("Reference replay manifest is invalid") from exc
    for descriptor in manifest.artifacts:
        path = _resolve_artifact(bundle_root, descriptor)
        if path.stat().st_size != descriptor.byte_length:
            raise ReferenceArtifactMismatchError(
                f"Reference artifact length differs: {descriptor.file_name}"
            )
        if sha256_file(path) != descriptor.sha256:
            raise ReferenceArtifactMismatchError(
                f"Reference artifact digest differs: {descriptor.file_name}"
            )
    return manifest


def _resolve_artifact(root: Path, descriptor: ReferenceArtifactDescriptor) -> Path:
    try:
        return ArtifactLocator(
            root=root,
            relative_name=Path(descriptor.file_name),
            maximum_bytes=_MAX_ARTIFACT_BYTES,
            label=f"Reference artifact {descriptor.name}",
        ).resolve()
    except ValueError as exc:
        raise ReferenceArtifactMismatchError(str(exc)) from exc


def verify_reference_input_inventory(
    repository_root: Path,
    manifest: ReferenceReplayManifest,
) -> None:
    """Fail before regeneration when a direct input or source file has changed."""

    if reference_file_inputs(repository_root) != manifest.file_inputs:
        raise ReferenceArtifactMismatchError(
            "current Reference direct inputs differ from the replay manifest"
        )
