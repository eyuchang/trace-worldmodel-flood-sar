"""Build the deterministic, standalone BYOD student workspace archive.

The archive contains its own public teaching runtime, setup tool, exercise,
and standard-library tests.  Students need only a supported Python install;
the archive never includes the research repository, a model, or hidden truth.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

LAB_ROOT: Final = Path(__file__).resolve().parents[1]
REPO_ROOT: Final = LAB_ROOT.parents[1]
STUDENT_ROOT: Final = LAB_ROOT / "student"
BUNDLE_PREFIX: Final = Path("trace-small-sar-workshop")
ZIP_TIMESTAMP: Final = (2026, 8, 15, 0, 0, 0)
STUDENT_FILES: Final = (
    Path(".gitignore"),
    Path("README.md"),
    Path("setup_workshop.py"),
    Path("workshop.py"),
    Path("exercise/__init__.py"),
    Path("exercise/rescue_controller.py"),
    Path("tests/test_rescue_controller.py"),
    Path("_support/__init__.py"),
    Path("_support/runtime.py"),
    Path("_support/teaching_fixture.json"),
    Path("_support/types.py"),
)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _archive_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.create_system = 3
    return info


def _validated_payloads() -> list[tuple[str, bytes]]:
    payloads: list[tuple[str, bytes]] = []
    root = STUDENT_ROOT.resolve()
    for relative in STUDENT_FILES:
        source = (STUDENT_ROOT / relative).resolve()
        if root not in source.parents:
            raise ValueError(f"bundle source escapes the lab directory: {relative}")
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"bundle source must be a regular file: {relative}")
        archive_name = (BUNDLE_PREFIX / relative).as_posix()
        payloads.append((archive_name, source.read_bytes()))
    return sorted(payloads)


def build_bundle(output: Path) -> dict[str, object]:
    """Create one deterministic, non-overwriting student workspace archive."""

    output = output.expanduser()
    if output.suffix.lower() != ".zip":
        raise ValueError("student bundle output must end in .zip")
    parent = output.parent.resolve()
    if not parent.is_dir():
        raise ValueError("bundle output parent must already exist")
    resolved = parent / output.name
    if resolved.exists():
        raise ValueError("refusing to overwrite an existing student bundle")

    protected = (REPO_ROOT / "data").resolve()
    if resolved == protected or protected in resolved.parents:
        raise ValueError("refusing to write a bundle inside repository data")

    payloads = _validated_payloads()
    manifest: dict[str, object] = {
        "schema_version": "trace-small-sar-student-bundle-v1",
        "base_commit": "3f912bdf3fbacb679063da9ed2ce15a2330b91ab",
        "purpose": "standalone BYOD workspace for the public Small SAR teaching runtime",
        "files": [
            {"path": name, "sha256": _sha256_bytes(payload)} for name, payload in payloads
        ],
        "excludes": [
            "instructor resources and reference solution",
            "release and scientific-boundary tests",
            "video production files",
            "research source, scenario data, and geography data",
        ],
    }
    manifest_payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()

    descriptor, temporary_name = tempfile.mkstemp(
        dir=parent,
        prefix=f".{resolved.name}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, mode="w") as archive:
            for name, payload in payloads:
                archive.writestr(_archive_info(name), payload)
            archive.writestr(
                _archive_info((BUNDLE_PREFIX / ".workshop-manifest.json").as_posix()),
                manifest_payload,
            )
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.link(temporary, resolved)
    except FileExistsError as exc:
        raise ValueError("refusing to overwrite an existing student bundle") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the deterministic standalone Small SAR student workspace.",
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = build_bundle(args.output)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"student bundle ready: {args.output}")
    files = manifest["files"]
    if not isinstance(files, list):
        raise TypeError("student bundle manifest files must be a list")
    print(f"files: {len(files)}; scientific data included: no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
