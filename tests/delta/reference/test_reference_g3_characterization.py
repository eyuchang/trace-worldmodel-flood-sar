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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def test_reference_g3_characterization_preserves_historical_fixture_products(
    characterization: tuple[ReferenceG3CharacterizationIndex, Path],
) -> None:
    _, output = characterization
    receipt = ReferenceG3CharacterizationBenchmarkReceipt.model_validate_json(
        (ROOT / RECEIPT).read_text(encoding="utf-8")
    )

    for binding in receipt.implementation_files:
        assert _sha256(ROOT / binding.relative_path) == binding.content_sha256
    for binding in receipt.products:
        # The index binds the complete scientific-input aggregate, so unrelated
        # source changes intentionally replace its digest. The five fixture
        # products remain the behavior-preserving benchmark comparison.
        if binding.relative_path == "g3_characterization_index.json":
            continue
        assert _sha256(output / binding.relative_path) == binding.content_sha256
