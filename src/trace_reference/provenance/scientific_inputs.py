"""Complete non-self-referential scientific-input inventory for Reference."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel
from trace_jepa.support import ArtifactLocator, canonical_json_bytes, safe_directory, sha256_file

from .inventory import reference_direct_input_paths

_MAX_MEMBER_BYTES = 256 * 1024 * 1024


class ReferenceScientificInputMember(DeltaModel):
    """One repository-relative source or input in the scientific freeze boundary."""

    repository_relative_path: str = Field(min_length=1, max_length=300)
    byte_length: int = Field(ge=1, le=_MAX_MEMBER_BYTES)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReferenceScientificInputManifest(DeltaModel):
    """Complete development inventory; generated outputs are intentionally absent."""

    schema_version: Literal["delta-reference-scientific-input-manifest-v1"]
    scientific_status: Literal["development-input-inventory-not-frozen-validation-evidence"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    members: tuple[ReferenceScientificInputMember, ...] = Field(min_length=1)
    aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_inventory(self) -> ReferenceScientificInputManifest:
        paths = tuple(item.repository_relative_path for item in self.members)
        if paths != tuple(sorted(paths)) or len(set(paths)) != len(paths):
            raise ValueError("Reference scientific inputs must be unique and canonically ordered")
        body = self.model_dump(mode="json", exclude={"aggregate_sha256"})
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != self.aggregate_sha256:
            raise ValueError("Reference scientific-input aggregate digest is invalid")
        return self


def _member_paths(repository_root: Path) -> tuple[str, ...]:
    source_root = safe_directory(
        repository_root / "src",
        declared_root=repository_root,
        label="Reference scientific source root",
    )
    source_paths = tuple(
        path.relative_to(repository_root).as_posix() for path in sorted(source_root.rglob("*.py"))
    )
    paths = tuple(sorted({*reference_direct_input_paths(), *source_paths}))
    if len(paths) != len(reference_direct_input_paths()) + len(source_paths):
        raise RuntimeError("Reference scientific input classes unexpectedly overlap")
    return paths


def build_reference_scientific_input_manifest(
    repository_root: Path,
) -> ReferenceScientificInputManifest:
    """Build the complete deterministic source/input inventory without outputs."""

    members = []
    for relative_name in _member_paths(repository_root):
        path = ArtifactLocator(
            root=repository_root,
            relative_name=Path(relative_name),
            maximum_bytes=_MAX_MEMBER_BYTES,
            label=f"Reference scientific input member {relative_name}",
        ).resolve()
        members.append(
            ReferenceScientificInputMember(
                repository_relative_path=relative_name,
                byte_length=path.stat().st_size,
                sha256=sha256_file(path),
            )
        )
    body = {
        "schema_version": "delta-reference-scientific-input-manifest-v1",
        "scientific_status": "development-input-inventory-not-frozen-validation-evidence",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "members": [item.model_dump(mode="json") for item in members],
    }
    return ReferenceScientificInputManifest(
        **body,
        aggregate_sha256=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )


def verify_reference_scientific_input_manifest(
    repository_root: Path,
    expected: ReferenceScientificInputManifest,
) -> None:
    """Reject any member addition, removal, length change, or content substitution."""

    if build_reference_scientific_input_manifest(repository_root) != expected:
        raise ValueError("Reference scientific-input inventory differs from its bound manifest")
