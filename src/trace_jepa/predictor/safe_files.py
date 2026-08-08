from __future__ import annotations

import stat
import zipfile
from pathlib import Path


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
