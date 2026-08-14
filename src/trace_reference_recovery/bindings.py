"""Trusted-root artifact bindings used by recovery reports and manifests."""

from __future__ import annotations

from pathlib import Path

from trace_jepa.support import ArtifactLocator, sha256_file
from trace_reference.validation.registration_models import ReferenceValidationBinding

MAX_RECOVERY_ARTIFACT_BYTES = 64 * 1024 * 1024


def bind_artifact(
    repository_root: Path,
    relative_path: Path,
    *,
    maximum_bytes: int = MAX_RECOVERY_ARTIFACT_BYTES,
) -> ReferenceValidationBinding:
    """Resolve within a trusted root before hashing one recovery dependency."""

    path = ArtifactLocator(
        root=repository_root,
        relative_name=relative_path,
        maximum_bytes=maximum_bytes,
        label=f"recovery report binding {relative_path}",
    ).resolve()
    return ReferenceValidationBinding(
        repository_relative_path=relative_path.as_posix(),
        sha256=sha256_file(path),
    )


def read_bound_text(
    repository_root: Path,
    binding: ReferenceValidationBinding,
    *,
    maximum_bytes: int = MAX_RECOVERY_ARTIFACT_BYTES,
) -> str:
    """Read an already-bound artifact only after path and digest verification."""

    path = ArtifactLocator(
        root=repository_root,
        relative_name=Path(binding.repository_relative_path),
        maximum_bytes=maximum_bytes,
        label=f"recovery bound input {binding.repository_relative_path}",
    ).resolve()
    if sha256_file(path) != binding.sha256:
        raise ValueError(f"recovery bound input changed: {binding.repository_relative_path}")
    return path.read_text("utf-8")
