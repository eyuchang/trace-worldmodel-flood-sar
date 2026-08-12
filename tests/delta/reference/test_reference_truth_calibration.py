from __future__ import annotations

import json
from pathlib import Path

import pytest

from trace_reference.calibration import (
    benchmark_reference_truth_fit,
    load_reference_truth_fit_protocol,
)
from trace_reference.calibration.truth_fit import (
    load_reference_truth_fit_benchmark,
    write_reference_truth_fit_benchmark,
)
from trace_reference.domain.truth import ReferenceIncidentType

ROOT = Path(__file__).resolve().parents[3]
FAILED_BENCHMARK = Path(
    "data/scenario/delta/reference/calibration/reference_truth_fit_benchmark_failed_v1.json"
)
FAILED_BENCHMARK_V2 = Path(
    "data/scenario/delta/reference/calibration/reference_truth_fit_benchmark_failed_v2.json"
)


def test_truth_fit_protocol_freezes_spent_development_scope() -> None:
    protocol = load_reference_truth_fit_protocol(ROOT)

    assert protocol.seed_count == 100
    assert protocol.seed_namespace.endswith("|development-v1|index")
    assert (
        protocol.target_total_lower,
        protocol.target_total_midpoint,
        protocol.target_total_upper,
    ) == (1_800, 2_000, 2_200)
    assert sum(item.share_micros for item in protocol.target_shares) == 1_000_000
    assert protocol.target_shares[0].incident_type == ReferenceIncidentType.INFORMATION_NEED
    assert protocol.target_shares[-1].incident_type == ReferenceIncidentType.MEDICAL_ACCESS
    assert protocol.solver.per_seed_normalization == "forbidden"


def test_failed_benchmark_is_preserved_as_adverse_evidence() -> None:
    receipt = load_reference_truth_fit_benchmark(ROOT, FAILED_BENCHMARK)

    assert receipt.seed_indices == (0, 1, 2, 3, 4)
    assert receipt.projected_full_fit_ms == 2_884_980
    assert receipt.traced_python_peak_bytes == 78_634_855
    assert not receipt.within_registered_bounds

    optimized_receipt = load_reference_truth_fit_benchmark(ROOT, FAILED_BENCHMARK_V2)
    assert optimized_receipt.kernel_id == "compact-primitive-exact-v2"
    assert optimized_receipt.projected_full_fit_ms == 985_400
    assert optimized_receipt.observed_episode_count == receipt.observed_episode_count
    assert optimized_receipt.observed_interval_count == receipt.observed_interval_count
    assert not optimized_receipt.within_registered_bounds


def test_truth_fit_benchmark_is_digest_bound_and_tamper_evident(tmp_path: Path) -> None:
    receipt = benchmark_reference_truth_fit(ROOT, pilot_seed_count=1)
    output = tmp_path / "benchmark"
    output.mkdir()
    path = write_reference_truth_fit_benchmark(receipt, output)

    assert load_reference_truth_fit_benchmark(output, path.relative_to(output)) == receipt

    payload = json.loads(path.read_text("utf-8"))
    payload["projected_full_fit_ms"] += 1
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid"):
        load_reference_truth_fit_benchmark(output, path.relative_to(output))
