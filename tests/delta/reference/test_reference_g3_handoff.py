from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from trace_reference.provenance import build_reference_scientific_input_manifest
from trace_reference.validation import (
    REFERENCE_G3_GATE_IDS,
    ReferenceG3AcceptanceRegistry,
    ReferenceG3CharacterizationIndex,
    ReferenceG3HandoffManifest,
    build_reference_g3_acceptance_receipt,
    build_reference_g3_handoff_manifest,
)

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = Path("data/scenario/delta/reference_protocol/reference_g3_acceptance_registry_v1.json")
CORRECTED_ADR = Path("docs/delta/reference/REFERENCE_G3_TRACE_LEAP_HANDOFF_ADR_V2.md")
MECHANISM_AUDIT = Path(
    "docs/delta/reference/TRACE_LEAP_MECHANISM_IDENTITY_AND_ADAPTATION_AUDIT_V1.md"
)
CHARACTERIZATION_ROOT = Path("data/scenario/delta/reference/g3_handoff_v1")
SCIENTIFIC_INPUT = CHARACTERIZATION_ROOT / "scientific_input_manifest.json"
ACCEPTANCE_RECEIPT = CHARACTERIZATION_ROOT / "g3_acceptance_receipt.json"
HANDOFF_MANIFEST = CHARACTERIZATION_ROOT / "g3_handoff_manifest.json"
CHARACTERIZATION_SHA256 = {
    "acquisition-success": "c797600c2ef36f8c79b59674aeb4aad13f12632eff1686d102cd39967a0da25b",
    "acquisition-timeout": "0473f62c7438953f2a754dd8fe6293a705a083667f6f4edf7f6dcf546676ad08",
    "empty-catalog-fallback": "620a1cb34422871ce85f9f4ca486340266ac2e27f73c19a121a805c97ee91329",
    "faulted-restart": "f6269097f8c6446ec4153031b0945d0687e97c0000ce7e1721d217047e7e4626",
    "nominal": "d03d1882ca4fe6433efdae608f8d690709f479694a58dfb1ca7573b72296aa83",
}
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


def test_g3_committed_characterization_is_complete_and_digest_bound() -> None:
    index = ReferenceG3CharacterizationIndex.model_validate_json(
        (ROOT / CHARACTERIZATION_ROOT / "g3_characterization_index.json").read_text("utf-8")
    )
    assert index.index_digest == (
        "c697192757f6c8d7f5719e01d14f1557ad4184f5a8916508de3068de61ca2846"
    )
    assert tuple(item.fixture_id for item in index.fixtures) == (
        "acquisition-success",
        "acquisition-timeout",
        "empty-catalog-fallback",
        "faulted-restart",
        "nominal",
    )
    for fixture in index.fixtures:
        path = ROOT / CHARACTERIZATION_ROOT / f"{fixture.fixture_id}_fixture_manifest.json"
        assert json.loads(path.read_text("utf-8")) == fixture.model_dump(mode="json")
        assert (
            hashlib.sha256(path.read_bytes()).hexdigest()
            == CHARACTERIZATION_SHA256[fixture.fixture_id]
        )
    assert all(not item.leap_implementation_present for item in index.fixtures)
    assert all(not item.effectiveness_evidence_present for item in index.fixtures)


def test_g3_committed_handoff_manifest_rebuilds_from_every_bound_input() -> None:
    stored = ReferenceG3HandoffManifest.model_validate_json(
        (ROOT / HANDOFF_MANIFEST).read_text("utf-8")
    )
    rebuilt = build_reference_g3_handoff_manifest(
        ROOT,
        scientific_input_relative_path=SCIENTIFIC_INPUT,
        acceptance_receipt_relative_path=ACCEPTANCE_RECEIPT,
        characterization_root_relative_path=CHARACTERIZATION_ROOT,
    )
    assert rebuilt == stored
    assert stored.adr.sha256 == CORRECTED_ADR_SHA256
    assert stored.leap_implementation_present is False
    assert stored.effectiveness_evidence_present is False
    assert stored.g3_ready
