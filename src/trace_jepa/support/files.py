"""Security-conscious deterministic file primitives shared across TRACE."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


def canonical_json_bytes(value: object) -> bytes:
    """Encode canonical, finite JSON with one trailing newline."""

    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Hash a file without loading it wholly into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    """Return a lowercase SHA-256 digest for an in-memory payload."""

    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class ArtifactLocator:
    """A bounded relative artifact name beneath a caller-trusted root."""

    root: Path
    relative_name: Path
    maximum_bytes: int
    label: str

    @classmethod
    def from_path(
        cls,
        *,
        root: Path,
        path: Path,
        maximum_bytes: int,
        label: str,
    ) -> ArtifactLocator:
        try:
            relative = Path(path).absolute().relative_to(Path(root).absolute())
        except ValueError as exc:
            raise ValueError(f"{label} is outside its caller-trusted root") from exc
        return cls(Path(root), relative, maximum_bytes, label)

    def resolve(self) -> Path:
        relative = Path(self.relative_name)
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise ValueError(f"{self.label} has an unsafe relative name")
        return safe_regular_file(
            Path(self.root) / relative,
            declared_root=self.root,
            maximum_bytes=self.maximum_bytes,
            label=self.label,
        )


def _safe_root(root: Path, label: str) -> Path:
    if root.is_symlink():
        raise ValueError(f"{label} root must not be a symlink")
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"{label} root is absent") from exc
    if not resolved.is_dir():
        raise ValueError(f"{label} root must be a directory")
    return resolved


def _relative_candidate(path: Path, root: Path, label: str) -> Path:
    try:
        relative = path.absolute().relative_to(root.absolute())
    except ValueError as exc:
        raise ValueError(f"{label} is outside its caller-trusted root") from exc
    if not relative.parts or ".." in relative.parts:
        raise ValueError(f"{label} has an unsafe relative name")
    return relative


def _reject_intermediate_symlinks(root: Path, relative: Path, label: str) -> None:
    cursor = root
    for component in relative.parts[:-1]:
        cursor = cursor / component
        if cursor.is_symlink():
            raise ValueError(f"{label} parent must not be a symlink")


def safe_regular_file(
    path: Path,
    *,
    declared_root: Path,
    maximum_bytes: int,
    label: str,
) -> Path:
    """Resolve a bounded regular file without accepting symlink boundaries."""

    candidate = Path(path)
    root = Path(declared_root)
    resolved_root = _safe_root(root, label)
    relative = _relative_candidate(candidate, root, label)
    _reject_intermediate_symlinks(root, relative, label)
    if candidate.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise ValueError(f"{label} escapes or is absent from its declared root") from exc
    metadata = resolved.stat(follow_symlinks=False)
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{label} must be a regular file")
    if metadata.st_size > maximum_bytes:
        raise ValueError(f"{label} exceeds the maximum expected size")
    return resolved


def safe_directory(path: Path, *, declared_root: Path, label: str) -> Path:
    """Resolve a directory beneath a caller-trusted root without symlinks."""

    candidate = Path(path)
    root = Path(declared_root)
    resolved_root = _safe_root(root, label)
    if candidate.absolute() == root.absolute():
        relative = Path()
    else:
        relative = _relative_candidate(candidate, root, label)
        _reject_intermediate_symlinks(root, relative, label)
    if candidate.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise ValueError(f"{label} escapes or is absent from its declared root") from exc
    if not resolved.is_dir():
        raise ValueError(f"{label} must be a directory")
    return resolved


def safe_output_file(path: Path, *, declared_root: Path, label: str) -> Path:
    """Validate a caller-named output without following symlink boundaries."""

    root = Path(declared_root)
    resolved_root = _safe_root(root, label)
    relative = _relative_candidate(Path(path), root, label)
    _reject_intermediate_symlinks(root, relative, label)
    parent = (root / relative).parent.resolve(strict=True)
    if not parent.is_relative_to(resolved_root):
        raise ValueError(f"{label} escapes its caller-trusted root")
    destination = root / relative
    if destination.is_symlink() or (destination.exists() and not destination.is_file()):
        raise ValueError(f"{label} must be a safe regular-file destination")
    return destination


def atomic_write_bytes(path: Path, payload: bytes, *, root: Path, label: str) -> None:
    """Atomically replace one validated file within an existing trusted root."""

    destination = safe_output_file(path, declared_root=root, label=label)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.name}.",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, destination)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def validate_npz_container(
    path: Path,
    *,
    expected_arrays: set[str],
    maximum_uncompressed_bytes: int,
    label: str,
) -> None:
    """Reject malformed, oversized, or schema-expanding NPZ archives."""

    expected_members = {f"{name}.npy" for name in expected_arrays}
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            names = {member.filename for member in members}
            if names != expected_members or len(names) != len(members):
                raise ValueError(f"{label} does not satisfy the exact array schema")
            if any(
                Path(member.filename).is_absolute()
                or Path(member.filename).name != member.filename
                or member.is_dir()
                for member in members
            ):
                raise ValueError(f"{label} contains an unsafe archive member")
            if sum(member.file_size for member in members) > maximum_uncompressed_bytes:
                raise ValueError(f"{label} exceeds the maximum uncompressed size")
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"{label} is not a valid NPZ container") from exc
