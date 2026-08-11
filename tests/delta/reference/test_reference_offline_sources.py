from __future__ import annotations

import stat
import zipfile
from pathlib import Path

import pytest

from trace_jepa.support import sha256_bytes
from trace_reference.geography import (
    ReferenceArchiveMemberSpec,
    ReferenceSourceArtifactSpec,
    inspect_reference_source,
    write_reference_source_receipt,
)
from trace_reference.geography.offline_sources import ReferenceSourceSecurityError


def _json_spec(payload: bytes) -> ReferenceSourceArtifactSpec:
    return ReferenceSourceArtifactSpec(
        source_id="TEST-SRC-01",
        relative_name="source.json",
        expected_sha256=sha256_bytes(payload),
        maximum_bytes=10_000,
        media_type="application/json",
        approval_status="security-test-fixture",
        runtime_inclusion="none",
    )


def test_reference_source_inspection_is_bounded_and_nonoperative(tmp_path: Path) -> None:
    payload = b'{"agency":"fixture"}\n'
    (tmp_path / "source.json").write_bytes(payload)
    receipt = inspect_reference_source(tmp_path, _json_spec(payload))
    assert receipt.sha256 == sha256_bytes(payload)
    assert receipt.runtime_inclusion == "none"

    output = tmp_path / "output"
    output.mkdir()
    write_reference_source_receipt(output, Path("receipt.json"), receipt)
    assert (output / "receipt.json").read_bytes().endswith(b"\n")


def test_reference_source_rejects_digest_and_symlink_boundaries(tmp_path: Path) -> None:
    payload = b'{"agency":"fixture"}\n'
    (tmp_path / "source.json").write_bytes(payload)
    altered = _json_spec(payload).model_copy(update={"expected_sha256": "0" * 64})
    with pytest.raises(ReferenceSourceSecurityError, match="digest mismatch"):
        inspect_reference_source(tmp_path, altered)

    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "source.json").write_bytes(payload)
    alias = tmp_path / "alias"
    alias.symlink_to(nested, target_is_directory=True)
    unsafe = _json_spec(payload).model_copy(update={"relative_name": "alias/source.json"})
    with pytest.raises(ReferenceSourceSecurityError, match="parent must not be a symlink"):
        inspect_reference_source(tmp_path, unsafe)

    root_alias = tmp_path / "root-alias"
    root_alias.symlink_to(nested, target_is_directory=True)
    root_spec = _json_spec(payload).model_copy(update={"relative_name": "source.json"})
    with pytest.raises(ReferenceSourceSecurityError, match="root must not be a symlink"):
        inspect_reference_source(root_alias, root_spec)


def _zip_spec(archive: bytes, member: bytes) -> ReferenceSourceArtifactSpec:
    return ReferenceSourceArtifactSpec(
        source_id="TEST-SRC-02",
        relative_name="source.zip",
        expected_sha256=sha256_bytes(archive),
        maximum_bytes=100_000,
        media_type="application/zip",
        approval_status="security-test-fixture",
        runtime_inclusion="none",
        archive_member=ReferenceArchiveMemberSpec(
            relative_name="data/member.json",
            sha256=sha256_bytes(member),
            maximum_bytes=10_000,
        ),
        maximum_archive_members=10,
        maximum_total_uncompressed_bytes=20_000,
    )


def test_reference_archive_requires_exact_safe_member(tmp_path: Path) -> None:
    member = b'{"type":"FeatureCollection","features":[]}\n'
    archive_path = tmp_path / "source.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("data/member.json", member)
    receipt = inspect_reference_source(tmp_path, _zip_spec(archive_path.read_bytes(), member))
    assert receipt.archive_member_name == "data/member.json"
    assert receipt.archive_member_sha256 == sha256_bytes(member)


@pytest.mark.parametrize("unsafe_name", ["../escape.json", "/absolute.json", "a\\b.json"])
def test_reference_archive_rejects_unsafe_member_names(tmp_path: Path, unsafe_name: str) -> None:
    member = b"{}\n"
    archive_path = tmp_path / "source.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("data/member.json", member)
        archive.writestr(unsafe_name, b"unsafe")
    with pytest.raises(ReferenceSourceSecurityError, match="unsafe archive member"):
        inspect_reference_source(tmp_path, _zip_spec(archive_path.read_bytes(), member))


def test_reference_archive_rejects_symlink_and_oversized_members(tmp_path: Path) -> None:
    member = b"{}\n"
    archive_path = tmp_path / "source.zip"
    symlink = zipfile.ZipInfo("link")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("data/member.json", member)
        archive.writestr(symlink, "target")
    with pytest.raises(ReferenceSourceSecurityError, match="symlink"):
        inspect_reference_source(tmp_path, _zip_spec(archive_path.read_bytes(), member))

    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("data/member.json", b"x" * 10_001)
    spec = _zip_spec(archive_path.read_bytes(), b"x" * 10_001)
    with pytest.raises(ReferenceSourceSecurityError, match="byte ceiling"):
        inspect_reference_source(tmp_path, spec)


def test_reference_archive_rejects_duplicate_members(tmp_path: Path) -> None:
    member = b"{}\n"
    archive_path = tmp_path / "source.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("data/member.json", member)
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("data/member.json", member)
    with pytest.raises(ReferenceSourceSecurityError, match="duplicate member"):
        inspect_reference_source(tmp_path, _zip_spec(archive_path.read_bytes(), member))


def test_reference_receipt_rejects_symlinked_output_parent(tmp_path: Path) -> None:
    payload = b'{"agency":"fixture"}\n'
    (tmp_path / "source.json").write_bytes(payload)
    receipt = inspect_reference_source(tmp_path, _json_spec(payload))
    output = tmp_path / "output"
    output.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (output / "alias").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ReferenceSourceSecurityError, match="parent must not be a symlink"):
        write_reference_source_receipt(output, Path("alias/receipt.json"), receipt)
