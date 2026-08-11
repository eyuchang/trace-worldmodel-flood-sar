"""Fail-closed inspection of staged Reference sources without network access."""

from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath

from trace_jepa.support import (
    ArtifactLocator,
    atomic_write_bytes,
    canonical_json_bytes,
    sha256_file,
)

from .source_models import (
    ReferenceArchiveMemberSpec,
    ReferenceSourceArtifactSpec,
    ReferenceSourceInspectionReceipt,
)

MAXIMUM_STRUCTURED_DOCUMENT_BYTES = 25_000_000


class ReferenceSourceSecurityError(ValueError):
    """Raised before unsafe or unexpected source bytes can be inspected."""


def _safe_member_name(name: str) -> PurePosixPath:
    member = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or member.is_absolute()
        or ".." in member.parts
        or "." in member.parts
    ):
        raise ReferenceSourceSecurityError(f"unsafe archive member: {name!r}")
    return member


def _validate_json(path: Path, *, geojson: bool) -> None:
    if path.stat().st_size > MAXIMUM_STRUCTURED_DOCUMENT_BYTES:
        raise ReferenceSourceSecurityError("structured source exceeds safe parse ceiling")
    try:
        value = json.loads(path.read_text("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReferenceSourceSecurityError("source is not valid bounded JSON") from exc
    if geojson and (
        not isinstance(value, dict)
        or value.get("type") != "FeatureCollection"
        or not isinstance(value.get("features"), list)
    ):
        raise ReferenceSourceSecurityError("GeoJSON source must be a FeatureCollection")


def _validate_tiff(path: Path) -> None:
    with path.open("rb") as stream:
        header = stream.read(4)
    if header not in {b"II*\x00", b"MM\x00*"}:
        raise ReferenceSourceSecurityError("source does not have a TIFF byte-order marker")


def _validate_html(path: Path) -> None:
    try:
        with path.open("rb") as stream:
            prefix = stream.read(4_096).decode("utf-8").casefold()
    except (OSError, UnicodeError) as exc:
        raise ReferenceSourceSecurityError("HTML source is not valid UTF-8") from exc
    if "<html" not in prefix and "<!doctype html" not in prefix:
        raise ReferenceSourceSecurityError("source does not contain an HTML document marker")


def _compression_ratio(file_size: int, compress_size: int) -> float:
    if file_size == 0:
        return 0.0
    if compress_size == 0:
        return float("inf")
    return file_size / compress_size


def _validated_archive_members(
    archive: zipfile.ZipFile,
    spec: ReferenceSourceArtifactSpec,
) -> dict[str, zipfile.ZipInfo]:
    members = archive.infolist()
    if len(members) > spec.maximum_archive_members:
        raise ReferenceSourceSecurityError("archive contains too many members")
    by_name: dict[str, zipfile.ZipInfo] = {}
    total_uncompressed = 0
    for member in members:
        normalized = str(_safe_member_name(member.filename))
        if normalized in by_name:
            raise ReferenceSourceSecurityError("archive contains duplicate member names")
        if member.is_dir() or stat.S_ISLNK(member.external_attr >> 16):
            raise ReferenceSourceSecurityError("archive directory or symlink rejected")
        if member.flag_bits & 0x1:
            raise ReferenceSourceSecurityError("encrypted archive member rejected")
        total_uncompressed += member.file_size
        if total_uncompressed > spec.maximum_total_uncompressed_bytes:
            raise ReferenceSourceSecurityError("archive exceeds uncompressed byte ceiling")
        ratio = _compression_ratio(member.file_size, member.compress_size)
        if ratio > spec.maximum_compression_ratio:
            raise ReferenceSourceSecurityError("archive compression ratio is unsafe")
        by_name[normalized] = member
    return by_name


def _digest_archive_member(
    archive: zipfile.ZipFile,
    member: zipfile.ZipInfo,
    maximum_bytes: int,
) -> tuple[int, str]:
    if member.file_size > maximum_bytes:
        raise ReferenceSourceSecurityError("declared archive member exceeds byte ceiling")
    digest = hashlib.sha256()
    observed_bytes = 0
    with archive.open(member) as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            observed_bytes += len(chunk)
            if observed_bytes > maximum_bytes:
                raise ReferenceSourceSecurityError(
                    "declared archive member exceeds byte ceiling while reading"
                )
            digest.update(chunk)
    return observed_bytes, digest.hexdigest()


def _inspect_archive(
    path: Path,
    *,
    spec: ReferenceSourceArtifactSpec,
    expected: ReferenceArchiveMemberSpec,
) -> tuple[int, str]:
    expected_name = str(_safe_member_name(expected.relative_name))
    try:
        with zipfile.ZipFile(path) as archive:
            members = _validated_archive_members(archive, spec)
            if expected_name not in members:
                raise ReferenceSourceSecurityError("declared archive member is absent")
            observed_bytes, observed_digest = _digest_archive_member(
                archive, members[expected_name], expected.maximum_bytes
            )
    except (OSError, zipfile.BadZipFile) as exc:
        raise ReferenceSourceSecurityError("source is not a valid ZIP archive") from exc
    if observed_digest != expected.sha256:
        raise ReferenceSourceSecurityError("declared archive member digest mismatch")
    return observed_bytes, observed_digest


def inspect_reference_source(
    source_root: Path,
    spec: ReferenceSourceArtifactSpec,
) -> ReferenceSourceInspectionReceipt:
    """Inspect one staged source by exact bytes, schema, and archive member."""

    try:
        path = ArtifactLocator(
            root=source_root,
            relative_name=Path(spec.relative_name),
            maximum_bytes=spec.maximum_bytes,
            label=f"Reference source {spec.source_id}",
        ).resolve()
    except ValueError as exc:
        raise ReferenceSourceSecurityError(str(exc)) from exc
    observed_digest = sha256_file(path)
    if observed_digest != spec.expected_sha256:
        raise ReferenceSourceSecurityError("source digest mismatch")

    member_bytes: int | None = None
    member_digest: str | None = None
    member_name: str | None = None
    if spec.media_type == "application/json":
        _validate_json(path, geojson=False)
    elif spec.media_type == "application/geo+json":
        _validate_json(path, geojson=True)
    elif spec.media_type == "image/tiff":
        _validate_tiff(path)
    elif spec.media_type == "text/html":
        _validate_html(path)
    else:
        expected = spec.archive_member
        if expected is None:  # guarded by model validation; retained for type narrowing
            raise ReferenceSourceSecurityError("zip source is missing a member contract")
        member_name = expected.relative_name
        member_bytes, member_digest = _inspect_archive(path, spec=spec, expected=expected)

    return ReferenceSourceInspectionReceipt(
        receipt_schema="delta-reference-source-inspection-receipt-v1",
        source_id=spec.source_id,
        relative_name=spec.relative_name,
        media_type=spec.media_type,
        byte_length=path.stat().st_size,
        sha256=observed_digest,
        archive_member_name=member_name,
        archive_member_byte_length=member_bytes,
        archive_member_sha256=member_digest,
        approval_status=spec.approval_status,
        runtime_inclusion="none",
    )


def write_reference_source_receipt(
    output_root: Path,
    relative_name: Path,
    receipt: ReferenceSourceInspectionReceipt,
) -> None:
    """Write a deterministic receipt beneath an existing caller-trusted root."""

    try:
        atomic_write_bytes(
            output_root / relative_name,
            canonical_json_bytes(receipt.model_dump(mode="json")),
            root=output_root,
            label="Reference source inspection receipt",
        )
    except ValueError as exc:
        raise ReferenceSourceSecurityError(str(exc)) from exc
