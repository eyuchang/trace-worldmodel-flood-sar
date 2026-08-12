from __future__ import annotations

import json
from pathlib import Path

import pytest

from trace_reference.provenance import (
    ReferenceScientificInputManifest,
    build_reference_scientific_input_manifest,
    verify_reference_scientific_input_manifest,
)

ROOT = Path(__file__).resolve().parents[3]


def test_reference_scientific_manifest_covers_all_python_and_direct_inputs() -> None:
    manifest = build_reference_scientific_input_manifest(ROOT)
    paths = {item.repository_relative_path for item in manifest.members}
    expected_source = {item.relative_to(ROOT).as_posix() for item in (ROOT / "src").rglob("*.py")}

    assert expected_source <= paths
    assert "pyproject.toml" in paths
    assert "requirements-delta-python311.lock" in paths
    assert (
        "data/scenario/delta/reference/environment/reference_python311_linux_amd64_v1.json" in paths
    )
    assert "docs/delta/reference/WF_DFLD_01_REFERENCE_PROTOCOL_DRAFT.md" in paths
    assert not any(
        part in path
        for path in paths
        for part in ("reference_bundle", "execution_receipt", "validation_report", "figures/")
    )
    verify_reference_scientific_input_manifest(ROOT, manifest)


def test_reference_scientific_manifest_detects_member_and_aggregate_tampering() -> None:
    manifest = build_reference_scientific_input_manifest(ROOT)
    payload = json.loads(manifest.model_dump_json())
    payload["members"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="aggregate digest"):
        ReferenceScientificInputManifest.model_validate(payload)

    payload = json.loads(manifest.model_dump_json())
    payload["members"].pop()
    with pytest.raises(ValueError, match="aggregate digest"):
        ReferenceScientificInputManifest.model_validate(payload)
