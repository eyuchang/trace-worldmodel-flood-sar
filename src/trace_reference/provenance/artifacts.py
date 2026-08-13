"""Bounded canonical artifact writing for the Reference development simulator."""

from __future__ import annotations

import gzip
import hashlib
import os
import tempfile
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path

from pydantic import BaseModel

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
from .limits import REFERENCE_ARTIFACT_MAX_BYTES
from .models import ReferenceArtifactDescriptor, ReferenceReplayManifest
from .specifications import (
    ReferenceArtifactSpec,
    ReferenceArtifactWriteRequest,
    build_reference_artifact_specs,
)

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
        if spec.content_encoding == "canonical-json-gzip-v1":
            sha256, byte_length = _write_canonical_model_sequence_gzip(
                path,
                spec.value,
                root=self.output_root,
                label=spec.name,
            )
            return ReferenceArtifactDescriptor(
                name=spec.name,
                file_name=spec.file_name,
                sha256=sha256,
                byte_length=byte_length,
                contains_hidden_truth=spec.contains_hidden_truth,
                content_encoding=spec.content_encoding,
            )
        payload = canonical_json_bytes(spec.value)
        if len(payload) > REFERENCE_ARTIFACT_MAX_BYTES:
            raise ReferenceArtifactMismatchError(
                "Reference artifact exceeds the registered size bound: "
                f"{spec.file_name} ({len(payload)} > {REFERENCE_ARTIFACT_MAX_BYTES} bytes)"
            )
        atomic_write_bytes(path, payload, root=self.output_root, label=spec.name)
        return ReferenceArtifactDescriptor(
            name=spec.name,
            file_name=spec.file_name,
            sha256=hashlib.sha256(payload).hexdigest(),
            byte_length=len(payload),
            contains_hidden_truth=spec.contains_hidden_truth,
            content_encoding=spec.content_encoding,
        )


def _write_canonical_model_sequence_gzip(
    path: Path,
    value: object,
    *,
    root: Path,
    label: str,
) -> tuple[str, int]:
    """Atomically stream one canonical model array through deterministic gzip."""

    if not isinstance(value, Iterable) or isinstance(value, (bytes, str)):
        raise TypeError("compressed Reference artifact must be an iterable of models")
    destination = safe_output_file(path, declared_root=root, label=label)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w+b",
            prefix=f".{destination.name}.",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            with gzip.GzipFile(
                filename="",
                mode="wb",
                compresslevel=9,
                fileobj=temporary,
                mtime=0,
            ) as compressed:
                compressed.write(b"[")
                for index, item in enumerate(value):
                    if not isinstance(item, BaseModel):
                        raise TypeError("compressed Reference sequence contains a non-model value")
                    if index:
                        compressed.write(b",")
                    compressed.write(
                        canonical_json_bytes(item.model_dump(mode="json")).rstrip(b"\n")
                    )
                compressed.write(b"]\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path = Path(temporary_name)
        byte_length = temporary_path.stat().st_size
        if byte_length > REFERENCE_ARTIFACT_MAX_BYTES:
            raise ReferenceArtifactMismatchError(
                "compressed Reference artifact exceeds the registered size bound: "
                f"{path.name} ({byte_length} > {REFERENCE_ARTIFACT_MAX_BYTES} bytes)"
            )
        sha256 = sha256_file(temporary_path)
        os.replace(temporary_path, destination)
        temporary_name = None
        return sha256, byte_length
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


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
            maximum_bytes=REFERENCE_ARTIFACT_MAX_BYTES,
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
