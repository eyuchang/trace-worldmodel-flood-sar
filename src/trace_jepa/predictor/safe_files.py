from __future__ import annotations

import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArtifactLocator:
    """A bounded artifact name interpreted only beneath a caller-trusted root."""

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


def safe_regular_file(
    path: Path,
    *,
    declared_root: Path,
    maximum_bytes: int,
    label: str,
) -> Path:
    """Resolve a bounded regular file without accepting a symlink boundary."""

    candidate = Path(path)
    root = Path(declared_root)
    if root.is_symlink():
        raise ValueError(f"{label} root must not be a symlink")
    try:
        resolved_root = root.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"{label} root is absent") from exc
    if not resolved_root.is_dir():
        raise ValueError(f"{label} root must be a directory")
    if candidate.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise ValueError(f"{label} escapes or is absent from its declared root") from exc

    relative = resolved.relative_to(resolved_root)
    cursor = root
    for component in relative.parts[:-1]:
        cursor = cursor / component
        if cursor.is_symlink():
            raise ValueError(f"{label} parent must not be a symlink")
    metadata = resolved.stat(follow_symlinks=False)
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{label} must be a regular file")
    if metadata.st_size > maximum_bytes:
        raise ValueError(f"{label} exceeds the maximum expected size")
    return resolved


def safe_output_file(
    path: Path,
    *,
    declared_root: Path,
    label: str,
) -> Path:
    """Validate a caller-named output without following any symlink boundary."""

    root = Path(declared_root)
    if root.is_symlink():
        raise ValueError(f"{label} root must not be a symlink")
    try:
        resolved_root = root.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"{label} root is absent") from exc
    if not resolved_root.is_dir():
        raise ValueError(f"{label} root must be a directory")
    try:
        relative = Path(path).absolute().relative_to(root.absolute())
    except ValueError as exc:
        raise ValueError(f"{label} is outside its caller-trusted root") from exc
    if not relative.parts or ".." in relative.parts:
        raise ValueError(f"{label} has an unsafe relative name")
    cursor = root
    for component in relative.parts[:-1]:
        cursor = cursor / component
        if cursor.is_symlink():
            raise ValueError(f"{label} parent must not be a symlink")
    parent = (root / relative).parent.resolve(strict=True)
    if not parent.is_relative_to(resolved_root):
        raise ValueError(f"{label} escapes its caller-trusted root")
    destination = root / relative
    if destination.is_symlink() or (destination.exists() and not destination.is_file()):
        raise ValueError(f"{label} must be a safe regular-file destination")
    return destination


def validate_npz_container(
    path: Path,
    *,
    expected_arrays: set[str],
    maximum_uncompressed_bytes: int,
    label: str,
) -> None:
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
