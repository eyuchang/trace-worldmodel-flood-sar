from __future__ import annotations

import hashlib
import json
from pathlib import Path

from trace_reference.runtime import REFERENCE_ENVIRONMENT_VERSION

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = (
    ROOT / "data/scenario/delta/reference/environment/reference_python311_linux_amd64_v1.json"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_reference_environment_binds_exact_lock_without_claiming_local_execution() -> None:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))

    assert value["contract_id"] == REFERENCE_ENVIRONMENT_VERSION
    assert value["exact_python_version"] == "3.11.14"
    assert value["oci_platform_manifest_sha256"] == (
        "88b6d3132a0850db3587a4f4ff28d5568e7d65ff99f0ee34f42be864ddb4ca1d"
    )
    assert value["dependency_lock_sha256"] == _sha256(ROOT / value["dependency_lock_file"])
    assert value["dependency_input_sha256"] == _sha256(ROOT / value["dependency_input_file"])
    claims = " ".join(value["claims"])
    assert "separately verified execution receipt" in claims
    assert "not canonical validation evidence" in claims
