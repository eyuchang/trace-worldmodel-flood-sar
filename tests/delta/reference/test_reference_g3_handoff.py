from __future__ import annotations

import json
from pathlib import Path

import pytest

from trace_reference.provenance import build_reference_scientific_input_manifest
from trace_reference.validation import (
    REFERENCE_G3_GATE_IDS,
    ReferenceG3AcceptanceRegistry,
    build_reference_g3_acceptance_receipt,
)

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = Path("data/scenario/delta/reference_protocol/reference_g3_acceptance_registry_v1.json")
CORRECTED_ADR = Path("docs/delta/reference/REFERENCE_G3_TRACE_LEAP_HANDOFF_ADR_V2.md")
MECHANISM_AUDIT = Path(
    "docs/delta/reference/TRACE_LEAP_MECHANISM_IDENTITY_AND_ADAPTATION_AUDIT_V1.md"
)
CORRECTED_ADR_SHA256 = "2af2b3b9e24040cb7fa0efa146b6e5cc9a3ad0805e53050494888a095b54403d"


def _registry() -> ReferenceG3AcceptanceRegistry:
    return ReferenceG3AcceptanceRegistry.model_validate_json((ROOT / REGISTRY).read_text("utf-8"))


def test_g3_registry_exactly_binds_corrected_adr_and_all_41_gates() -> None:
    registry = _registry()
    assert registry.adr_sha256 == CORRECTED_ADR_SHA256
    assert tuple(item.gate_id for item in registry.gates) == REFERENCE_G3_GATE_IDS
    assert len(registry.gates) == 41
    assert "faca92aae1d88e0ea1598020691ef69c8c78157b34964a25e10f1cc95ab6b270" not in (
        (ROOT / CORRECTED_ADR).read_text("utf-8")
        + (ROOT / MECHANISM_AUDIT).read_text("utf-8")
        + (ROOT / REGISTRY).read_text("utf-8")
    )


def test_g3_acceptance_receipt_fails_closed_on_incomplete_gate_results() -> None:
    with pytest.raises(ValueError, match="every corrected-ADR gate"):
        build_reference_g3_acceptance_receipt(
            ROOT,
            passed_gate_ids=REFERENCE_G3_GATE_IDS[:-1],
        )


def test_g3_acceptance_receipt_binds_every_registered_test_source() -> None:
    receipt = build_reference_g3_acceptance_receipt(
        ROOT,
        passed_gate_ids=REFERENCE_G3_GATE_IDS,
    )
    registry = _registry()
    registered_sources = {
        node_id.split("::", maxsplit=1)[0]
        for gate in registry.gates
        for node_id in gate.test_node_ids
    }
    assert {item.relative_path for item in receipt.test_sources} == registered_sources
    assert tuple(item.gate_id for item in receipt.gate_results) == REFERENCE_G3_GATE_IDS
    assert receipt.all_gates_pass


def test_g3_scientific_manifest_contains_adr_audit_registry_and_test_sources() -> None:
    manifest = build_reference_scientific_input_manifest(ROOT)
    paths = {item.repository_relative_path for item in manifest.members}
    registry = _registry()
    expected = {
        CORRECTED_ADR.as_posix(),
        MECHANISM_AUDIT.as_posix(),
        REGISTRY.as_posix(),
        *(
            node_id.split("::", maxsplit=1)[0]
            for gate in registry.gates
            for node_id in gate.test_node_ids
        ),
    }
    assert expected <= paths
    serialized = json.dumps(manifest.model_dump(mode="json"), sort_keys=True)
    assert "g3_handoff.py" in serialized
    assert "g3_handoff_models.py" in serialized
