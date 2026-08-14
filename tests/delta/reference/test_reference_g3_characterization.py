from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from trace_reference.validation import (
    ReferenceG3CharacterizationBenchmarkReceipt,
    ReferenceG3CharacterizationIndex,
    run_reference_g3_characterization,
)

ROOT = Path(__file__).resolve().parents[3]
RECEIPT = Path(
    "data/scenario/delta/reference_protocol/reference_g3_characterization_benchmark_v2.json"
)
HISTORICAL_RECEIPT_SHA256 = "acfbf7721295c9661b501234ebf6188cc30b626143657ab82b95f24025c2306c"
HISTORICAL_RUNTIME_BASE_COMMIT = "11ab2b62590c6d3106fa6929cd7273729e30a342"
HISTORICAL_IMPLEMENTATION_BINDINGS = {
    "src/trace_reference/runtime/decision_engine.py": (
        "12d51f21658ff7378a631972609f39a34f25e0e32a04fc2bf4c757329f912e32"
    ),
    "src/trace_reference/runtime/mission_runtime.py": (
        "a2c6d4922687dabcdbd8ce985eeff0e35bbc5760fbc1c706e8de2f41e0470aff"
    ),
    "src/trace_reference/validation/g3_characterization.py": (
        "4c311fbd23104c23baee19c3c3966c5b07fcd0284b4a189f5e02bbc0ce407e8f"
    ),
    "src/trace_reference/validation/g3_characterization_models.py": (
        "aa378e161a68acc3428fe769895bf41ae874e7e723cf731052ddb628cc2de53e"
    ),
}


@pytest.fixture(scope="module")
def characterization(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[ReferenceG3CharacterizationIndex, Path]:
    output = tmp_path_factory.mktemp("reference-g3-characterization")
    return run_reference_g3_characterization(ROOT, output, seed=20260812), output


def test_reference_g3_characterization_records_all_feature_off_fixtures(
    characterization: tuple[ReferenceG3CharacterizationIndex, Path],
) -> None:
    index, output = characterization
    stored = ReferenceG3CharacterizationIndex.model_validate_json(
        (output / "g3_characterization_index.json").read_text(encoding="utf-8")
    )

    assert stored == index
    assert tuple(item.fixture_id for item in index.fixtures) == (
        "acquisition-success",
        "acquisition-timeout",
        "empty-catalog-fallback",
        "faulted-restart",
        "nominal",
    )
    assert all(not item.leap_implementation_present for item in index.fixtures)
    assert all(not item.effectiveness_evidence_present for item in index.fixtures)
    assert index.fixtures[0].acquisition_outcome_status == "evidence-accepted"
    assert index.fixtures[0].physical_evidence_count == 1
    assert index.fixtures[1].acquisition_outcome_status == "provider-timeout"
    assert index.fixtures[1].physical_evidence_count == 0
    assert index.fixtures[2].selected_catalog_bundle_count == 0
    assert index.fixtures[2].fallback_disposition == "hold"
    assert index.fixtures[3].restart_public_state_equivalent
    assert index.fixtures[3].restart_durable_state_equivalent
    assert len(tuple(output.glob("*_fixture_manifest.json"))) == 5


def test_reference_g3_characterization_rejects_tampered_fixture_digest(
    characterization: tuple[ReferenceG3CharacterizationIndex, Path],
) -> None:
    index, _ = characterization
    value = index.model_dump(mode="json")
    value["fixtures"][0]["physical_evidence_count"] = 0

    with pytest.raises(ValidationError, match="acquisition-success fixture is incomplete"):
        ReferenceG3CharacterizationIndex.model_validate_json(
            json.dumps(value, sort_keys=True, separators=(",", ":"))
        )


def test_reference_g3_characterization_preserves_historical_benchmark_receipt() -> None:
    payload = (ROOT / RECEIPT).read_bytes()
    receipt = ReferenceG3CharacterizationBenchmarkReceipt.model_validate_json(payload)

    assert hashlib.sha256(payload).hexdigest() == HISTORICAL_RECEIPT_SHA256
    assert receipt.runtime_base_commit == HISTORICAL_RUNTIME_BASE_COMMIT
    assert receipt.pre_completion_products_byte_identical
    assert not receipt.final_products_match_pre_completion
    assert receipt.changed_product_reason == (
        "timeout-fixture-now-binds-required-post-outcome-reassessment"
    )
    assert {
        binding.relative_path: binding.content_sha256 for binding in receipt.implementation_files
    } == HISTORICAL_IMPLEMENTATION_BINDINGS
    assert all(
        binding.semantic_digest == binding.content_sha256
        for binding in receipt.implementation_files
    )
