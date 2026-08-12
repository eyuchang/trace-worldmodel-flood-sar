from __future__ import annotations

import json
from pathlib import Path

import pytest

from trace_reference.calibration.loading import load_reference_observation_coefficients
from trace_reference.calibration.observation_fit import (
    load_reference_observation_fit_benchmark,
    load_reference_observation_fit_protocol,
    reference_observation_target_schedule_micros,
)
from trace_reference.calibration.observation_models import ReferenceObservationFitReport

ROOT = Path(__file__).resolve().parents[3]
FAILED_BENCHMARK = Path(
    "data/scenario/delta/reference/calibration/reference_observation_fit_benchmark_failed_v1.json"
)
PASSING_BENCHMARK = Path(
    "data/scenario/delta/reference/calibration/reference_observation_fit_benchmark_v2.json"
)
COEFFICIENTS = Path(
    "data/scenario/delta/reference/calibration/reference_observation_coefficients_v2.json"
)
FIT_REPORT = Path(
    "data/scenario/delta/reference/calibration/reference_observation_fit_report_v1.json"
)


def test_observation_protocol_binds_frozen_truth_and_exact_schedule() -> None:
    protocol = load_reference_observation_fit_protocol(ROOT)
    schedule = reference_observation_target_schedule_micros()

    assert protocol.seed_namespace.endswith("|development-v1|index")
    assert protocol.seed_count == 100
    assert protocol.truth_coefficient_digest == (
        "63fa9591c17a1208cfa45c46a76997785aa9a9a15e00a074a1e62fe22540b25a"
    )
    assert schedule[52:64] == (95_000_000,) * 12
    assert sum(schedule) == 2_900_000_000


def test_failed_and_passing_observation_benchmarks_are_preserved() -> None:
    failed = load_reference_observation_fit_benchmark(ROOT, FAILED_BENCHMARK)
    passing = load_reference_observation_fit_benchmark(ROOT, PASSING_BENCHMARK)

    assert failed.projected_full_fit_ms == 1_016_180
    assert not failed.within_registered_bounds
    assert passing.projected_full_fit_ms == 482_240
    assert passing.measurement_method.startswith("single-world-pass")
    assert passing.potential_witness_count == failed.potential_witness_count
    assert passing.truth_incident_count == failed.truth_incident_count
    assert passing.within_registered_bounds


def test_observation_benchmark_is_tamper_evident(tmp_path: Path) -> None:
    source = ROOT / PASSING_BENCHMARK
    destination = tmp_path / "receipt.json"
    destination.write_bytes(source.read_bytes())
    payload = json.loads(destination.read_text())
    payload["projected_full_fit_ms"] += 1
    destination.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="invalid"):
        load_reference_observation_fit_benchmark(tmp_path, Path("receipt.json"))


def test_frozen_observation_fit_is_digest_validated_and_reports_adverse_results() -> None:
    coefficients = load_reference_observation_coefficients(ROOT, COEFFICIENTS)
    report = ReferenceObservationFitReport.model_validate_json((ROOT / FIT_REPORT).read_text())

    assert coefficients.coefficient_digest == (
        "02689bac6ae84c3896ec9eb17b23e5e917b99c9f3a8530d3c5c3bf14e2ef1591"
    )
    assert coefficients.initial_report_probability_micros == 160_000
    assert report.realized_mean_evaluation_reports_milli == 2_902_520
    assert min(report.realized_breach_hour_means_milli) == 93_490
    assert max(report.realized_breach_hour_means_milli) == 95_880
    assert len(report.adverse_findings) == 3
    assert any("taxonomy" in finding for finding in report.adverse_findings)
