from __future__ import annotations

import pytest

from trace_reference.validation import (
    ReferenceClusterInterval,
    ReferenceSeedMetric,
    cluster_bootstrap_mean_interval,
    exact_median_interval,
)

PROTOCOL_HASH = "a" * 64


def _values() -> tuple[ReferenceSeedMetric, ...]:
    return tuple(
        ReferenceSeedMetric(seed=seed, value_micros=value * 1_000_000)
        for seed, value in zip(range(100, 120), range(20), strict=True)
    )


def test_cluster_bootstrap_is_seed_level_order_invariant_and_reproducible() -> None:
    values = _values()
    first = cluster_bootstrap_mean_interval(
        values,
        protocol_hash=PROTOCOL_HASH,
        metric_name="observed_report_count",
        resample_count=1_000,
    )
    second = cluster_bootstrap_mean_interval(
        tuple(reversed(values)),
        protocol_hash=PROTOCOL_HASH,
        metric_name="observed_report_count",
        resample_count=1_000,
    )

    assert first == second
    assert first.point_micros == 9_500_000
    assert first.lower_micros < first.point_micros < first.upper_micros
    assert first.randomness_sha256 is not None


def test_exact_median_interval_reports_discrete_achieved_coverage() -> None:
    interval = exact_median_interval(_values(), metric_name="strict_load_ratio")

    assert interval.point_micros == 9_500_000
    assert interval.lower_micros <= interval.point_micros <= interval.upper_micros
    assert interval.achieved_coverage_micros is not None
    assert interval.achieved_coverage_micros >= interval.nominal_coverage_micros
    assert interval.randomness_sha256 is None


def test_cluster_statistics_reject_duplicate_seeds_and_invalid_hashes() -> None:
    duplicated = (
        ReferenceSeedMetric(seed=1, value_micros=1),
        ReferenceSeedMetric(seed=1, value_micros=2),
    )
    with pytest.raises(ValueError, match="duplicate"):
        exact_median_interval(duplicated, metric_name="duplicate_seed")
    with pytest.raises(ValueError, match="protocol hash"):
        cluster_bootstrap_mean_interval(
            _values(),
            protocol_hash="not-a-hash",
            metric_name="invalid_hash",
            resample_count=1_000,
        )


def test_interval_model_rejects_inconsistent_method_metadata() -> None:
    with pytest.raises(ValueError, match="randomness provenance"):
        ReferenceClusterInterval(
            schema_version="delta-reference-cluster-interval-v1",
            metric_name="invalid_bootstrap",
            method="deterministic-cluster-bootstrap-percentile-v1",
            cluster_count=10,
            point_micros=2,
            lower_micros=1,
            upper_micros=3,
            nominal_coverage_micros=950_000,
        )
