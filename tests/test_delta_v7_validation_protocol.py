from __future__ import annotations

from pathlib import Path

from trace_jepa.scenario.delta.artifacts import sha256_file
from trace_jepa.scenario.delta.loading import load_acceptance_config
from trace_jepa.scenario.delta.validation_v7 import (
    _cluster_fraction_interval,
    _cluster_mean_interval,
    _exact_median_interval,
    run_v7_study,
)

ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE = ROOT / "configs/scenarios/wf_dfld_01_small_acceptance_v3.yaml"
CONFIG = ROOT / "configs/scenarios/wf_dfld_01_small_v3.yaml"
GEOGRAPHY = ROOT / "data/scenario/delta/geography/delta_small_geography_v3.yaml"
POLICY = ROOT / "configs/policies/trace_delta_small_v1.yaml"


def test_confirmatory_v6_protocol_binds_exact_seeds_inputs_and_no_strict_gate() -> None:
    protocol = load_acceptance_config(ACCEPTANCE)
    assert protocol.schema_version == "delta-small-acceptance-v7"
    assert protocol.v7_confirmatory_ensemble is not None
    assert len(protocol.v7_confirmatory_ensemble.seeds) == 100
    assert len(set(protocol.v7_confirmatory_ensemble.seeds)) == 100
    assert protocol.v7_confirmatory_ensemble.seeds[:3] == [
        610419135,
        1553948431,
        1191027615,
    ]
    assert protocol.demand_capacity.primary_metric == "strict_concurrent_load_ratio"
    assert protocol.demand_capacity.strict_numerical_gate is None
    assert "administrative placeholder" in (protocol.registration_erratum or "")
    assert sha256_file(CONFIG) == protocol.frozen_input_sha256["scenario_configuration"]


def test_cluster_intervals_are_metric_keyed_and_deterministic() -> None:
    protocol_hash = sha256_file(ACCEPTANCE)
    values = [1.0, 2.0, 4.0, 8.0]
    first = _cluster_mean_interval(values, protocol_hash, "metric-a")
    second = _cluster_mean_interval(values, protocol_hash, "metric-a")
    other = _cluster_mean_interval(values, protocol_hash, "metric-b")
    assert first == second
    assert first["bootstrap_seed_derivation"] != other["bootstrap_seed_derivation"]
    counts = [(1, 2), (3, 4), (0, 1), (4, 5)]
    fraction = _cluster_fraction_interval(counts, protocol_hash, "fraction-a")
    assert fraction["estimate"] == 8 / 12
    assert fraction["cluster_count"] == 4


def test_exact_median_interval_uses_binomial_order_statistics() -> None:
    interval = _exact_median_interval([float(index) for index in range(1, 101)])
    assert interval["estimate"] == 50.5
    assert interval["lower_order_statistic_one_based"] == 40
    assert interval["upper_order_statistic_one_based"] == 61
    assert interval["lower_95"] == 40.0
    assert interval["upper_95"] == 61.0


def test_development_study_smoke_reports_all_v7_metrics_without_holdout() -> None:
    study = run_v7_study(
        study_id="development-test-only",
        seeds=[20260803, 20260804, 20260805],
        config_path=CONFIG,
        geography_path=GEOGRAPHY,
        policy_path=POLICY,
        protocol_hash=sha256_file(ACCEPTANCE),
    )
    assert study["seed_count"] == 3
    assert study["generator_version"] == "delta-small-generator-v7"
    assert "peak_strict_concurrent_load_ratio" in study
    assert "peak_uncapped_compatible_load_ratio" in study
    assert "peak_registered_normalized_coverable_load_index" in study
    assert "adjusted_rand_index" in study["reconciliation"]
    assert study["operations"]["all_trace_artifacts_verified"] is True
