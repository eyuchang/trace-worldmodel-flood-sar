from __future__ import annotations

import math
import random
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from trace_jepa.predictor import ToyActionPrefixPredictor
from trace_jepa.scenario.delta.artifacts import canonical_json_bytes, sha256_file
from trace_jepa.scenario.delta.generator import generate_delta_small_from_models
from trace_jepa.scenario.delta.loading import (
    load_acceptance_config,
    load_geography_catalog,
    load_scenario_config,
)
from trace_jepa.scenario.delta.models import GeneratedScenario
from trace_jepa.scenario.delta.runner import DeltaRunResult, run_delta_small

LEGACY_V1_DURATIONS_S = {
    "C-STR": 3_600,
    "C-VEH": 2_700,
    "C-LEV": 2_400,
    "C-MED": 2_400,
    "C-WEL": 1_800,
    "C-MIS": 3_000,
}


@dataclass(frozen=True)
class _LineageMetrics:
    relationships: Counter[str]
    nonreported_incidents: int
    incident_count: int
    callback_failures: int
    dropped_calls: int
    location_error_m_sum: float
    location_error_count: int
    repair_correct: int
    repair_scored: int
    false_report_outcomes: Counter[str]


class _StudyRow(TypedDict):
    seed: int
    latent_incidents: int
    observed_calls: int
    hourly_calls: list[int]
    peak_ratio: float
    unserviceable_windows: int
    allocations: int
    refusals: int
    repairs: int
    trace_chain_verified: bool


def _mean_ci(values: list[float]) -> dict[str, float]:
    mean = statistics.fmean(values)
    if len(values) < 2:
        return {"estimate": mean, "lower_95": mean, "upper_95": mean}
    half_width = 1.96 * statistics.stdev(values) / math.sqrt(len(values))
    return {
        "estimate": mean,
        "lower_95": mean - half_width,
        "upper_95": mean + half_width,
    }


def _wilson_ci(successes: int, total: int) -> dict[str, float]:
    if total == 0:
        return {"estimate": 0.0, "lower_95": 0.0, "upper_95": 0.0}
    z = 1.96
    estimate = successes / total
    denominator = 1.0 + z * z / total
    center = (estimate + z * z / (2 * total)) / denominator
    half_width = (
        z
        * math.sqrt(estimate * (1.0 - estimate) / total + z * z / (4 * total * total))
        / denominator
    )
    return {
        "estimate": estimate,
        "lower_95": center - half_width,
        "upper_95": center + half_width,
    }


def _median_ci(values: list[float]) -> dict[str, object]:
    bootstrap = random.Random(20_260_805)
    ordered_medians = sorted(
        statistics.median(bootstrap.choices(values, k=len(values))) for _ in range(10_000)
    )
    return {
        "estimate": statistics.median(values),
        "lower_95": ordered_medians[249],
        "upper_95": ordered_medians[9_749],
        "method": "deterministic-percentile-bootstrap-10000-v1",
    }


def _lineage_metrics(scenario: GeneratedScenario, result: DeltaRunResult) -> _LineageMetrics:
    lineage_by_call = {item.call_id: item for item in scenario.observations.lineage}
    call_by_id = {item.call_id: item for item in scenario.observations.calls}
    structure_by_id = {item.structure_id: item for item in scenario.truth.structures}
    incident_by_id = {item.incident_id: item for item in scenario.truth.incidents}
    reported_incidents = {
        item.truth_incident_id
        for item in scenario.observations.lineage
        if item.truth_incident_id is not None
    }
    relationships = Counter(item.relationship for item in scenario.observations.lineage)
    location_errors_m: list[float] = []
    for lineage in scenario.observations.lineage:
        if lineage.truth_incident_id is None:
            continue
        call = call_by_id[lineage.call_id]
        incident = incident_by_id[lineage.truth_incident_id]
        structure = structure_by_id[incident.structure_id]
        location_errors_m.append(
            math.hypot(
                call.location.easting_mm - structure.easting_mm,
                call.location.northing_mm - structure.northing_mm,
            )
            / 1000.0
        )
    correct_repairs = 0
    scored_repairs = 0
    for event in result.decisions:
        if event.event_type != "repair":
            continue
        current = lineage_by_call[event.call_id].truth_incident_id
        source = lineage_by_call.get(event.belief_cluster_id)
        if current is None or source is None or source.truth_incident_id is None:
            continue
        scored_repairs += 1
        correct_repairs += current == source.truth_incident_id
    false_ids = {
        item.call_id
        for item in scenario.observations.lineage
        if item.relationship == "false_report"
    }
    false_outcomes = Counter(
        event.event_type for event in result.decisions if event.call_id in false_ids
    )
    return _LineageMetrics(
        relationships=relationships,
        nonreported_incidents=len(scenario.truth.incidents) - len(reported_incidents),
        incident_count=len(scenario.truth.incidents),
        callback_failures=sum(item.quality.callback_failed for item in scenario.observations.calls),
        dropped_calls=sum(item.quality.call_dropped for item in scenario.observations.calls),
        location_error_m_sum=sum(location_errors_m),
        location_error_count=len(location_errors_m),
        repair_correct=correct_repairs,
        repair_scored=scored_repairs,
        false_report_outcomes=false_outcomes,
    )


def _legacy_v1_scenario(scenario: GeneratedScenario) -> GeneratedScenario:
    incidents = [
        incident.model_copy(
            update={"service_duration_s": LEGACY_V1_DURATIONS_S[incident.incident_type]}
        )
        for incident in scenario.truth.incidents
    ]
    return scenario.model_copy(
        update={"truth": scenario.truth.model_copy(update={"incidents": incidents})}
    )


def _study(
    *,
    study_id: str,
    seeds: list[int],
    config_path: Path,
    geography_path: Path,
    policy_path: Path,
    generator_version: str,
    legacy_duration_table: bool,
) -> dict[str, object]:
    config = load_scenario_config(config_path)
    geography = load_geography_catalog(geography_path)
    predictor = ToyActionPrefixPredictor()
    rows: list[_StudyRow] = []
    aggregate_relationships: Counter[str] = Counter()
    aggregate_false_outcomes: Counter[str] = Counter()
    total_calls = 0
    total_incidents = 0
    total_nonreported = 0
    total_callback_failures = 0
    total_dropped = 0
    total_repairs_correct = 0
    total_repairs_scored = 0
    total_location_error = 0.0
    total_location_error_count = 0
    for seed in seeds:
        study_config = config.model_copy(
            update={
                "seed": seed,
                "generator_version": generator_version,
            }
        )
        scenario = generate_delta_small_from_models(
            study_config, geography, config_path.resolve(strict=True)
        )
        if legacy_duration_table:
            scenario = _legacy_v1_scenario(scenario)
        result = run_delta_small(scenario, predictor, policy_path)
        lineage = _lineage_metrics(scenario, result)
        aggregate_relationships.update(lineage.relationships)
        aggregate_false_outcomes.update(lineage.false_report_outcomes)
        calls = len(scenario.observations.calls)
        incidents = len(scenario.truth.incidents)
        total_calls += calls
        total_incidents += incidents
        total_nonreported += lineage.nonreported_incidents
        total_callback_failures += lineage.callback_failures
        total_dropped += lineage.dropped_calls
        total_repairs_correct += lineage.repair_correct
        total_repairs_scored += lineage.repair_scored
        total_location_error += lineage.location_error_m_sum
        total_location_error_count += lineage.location_error_count
        hourly_calls = [
            sum(
                hour * 3600 <= call.received_s < (hour + 1) * 3600
                for call in scenario.observations.calls
            )
            for hour in range(6)
        ]
        rows.append(
            {
                "seed": seed,
                "latent_incidents": incidents,
                "observed_calls": calls,
                "hourly_calls": hourly_calls,
                "peak_ratio": result.peak_demand_capacity_ratio_milli / 1000.0,
                "unserviceable_windows": result.unserviceable_windows,
                "allocations": result.allocated,
                "refusals": result.refused,
                "repairs": result.repaired,
                "trace_chain_verified": result.trace_chain_verified,
            }
        )
    call_counts = [float(row["observed_calls"]) for row in rows]
    ratios = [row["peak_ratio"] for row in rows]
    hourly_means = [
        statistics.fmean(float(row["hourly_calls"][hour]) for row in rows) for hour in range(6)
    ]
    hourly_intervals = [
        _mean_ci([float(row["hourly_calls"][hour]) for row in rows]) for hour in range(6)
    ]
    relationship_intervals = {
        relationship: _wilson_ci(count, total_calls)
        for relationship, count in sorted(aggregate_relationships.items())
    }
    return {
        "study_id": study_id,
        "seed_count": len(seeds),
        "generator_version": (
            f"{generator_version}-reconstructed-duration-table"
            if legacy_duration_table
            else generator_version
        ),
        "seeds": seeds,
        "call_count": {
            **_mean_ci(call_counts),
            "minimum": min(call_counts),
            "maximum": max(call_counts),
            "hourly_means": hourly_means,
            "hourly_mean_95": hourly_intervals,
        },
        "peak_demand_capacity_ratio": {
            **_median_ci(ratios),
            "mean": statistics.fmean(ratios),
            "minimum": min(ratios),
            "maximum": max(ratios),
        },
        "observation_channel": {
            "relationship_fractions": relationship_intervals,
            "nonreporting": _wilson_ci(total_nonreported, total_incidents),
            "callback_failure": _wilson_ci(total_callback_failures, total_calls),
            "dropped_call": _wilson_ci(total_dropped, total_calls),
            "mean_location_error_m": (
                total_location_error / total_location_error_count
                if total_location_error_count
                else 0.0
            ),
            "reconciliation_accuracy": _wilson_ci(total_repairs_correct, total_repairs_scored),
            "false_report_outcomes": dict(sorted(aggregate_false_outcomes.items())),
        },
        "operations": {
            "allocation_mean": statistics.fmean(float(row["allocations"]) for row in rows),
            "refusal_mean": statistics.fmean(float(row["refusals"]) for row in rows),
            "repair_mean": statistics.fmean(float(row["repairs"]) for row in rows),
            "unserviceable_window_mean": statistics.fmean(
                float(row["unserviceable_windows"]) for row in rows
            ),
            "all_trace_chains_verified": all(bool(row["trace_chain_verified"]) for row in rows),
        },
        "per_seed": rows,
    }


def run_registered_validation(
    config_path: Path,
    geography_path: Path,
    policy_path: Path,
    acceptance_path: Path,
    output_path: Path,
) -> dict[str, object]:
    protocol = load_acceptance_config(acceptance_path)
    development_seeds = list(
        range(
            protocol.development_ensemble.first_seed,
            protocol.development_ensemble.first_seed + protocol.development_ensemble.seed_count,
        )
    )
    report: dict[str, object] = {
        "schema_version": "delta-small-statistical-validation-v2",
        "protocol_sha256": sha256_file(acceptance_path),
        "scenario_configuration_sha256": sha256_file(config_path),
        "geography_sha256": sha256_file(geography_path),
        "policy_sha256": sha256_file(policy_path),
        "book_seed_role": protocol.book_seed_role,
        "claims_limit": [
            "generator-process-validation-not-field-effectiveness",
            "confidence-intervals-describe-synthetic-seed-variation",
            "confirmatory-v1-adverse-result-retained",
            "confirmatory-v2-preaudit-result-retained",
            "numeric-gates-reported-even-when-failed",
        ],
        "studies": [
            _study(
                study_id="development-v5",
                seeds=development_seeds,
                config_path=config_path,
                geography_path=geography_path,
                policy_path=policy_path,
                generator_version="delta-small-generator-v5",
                legacy_duration_table=False,
            ),
            _study(
                study_id="confirmatory-v1-adverse",
                seeds=protocol.confirmatory_ensemble.seeds,
                config_path=config_path,
                geography_path=geography_path,
                policy_path=policy_path,
                generator_version="delta-small-generator-v2",
                legacy_duration_table=True,
            ),
            _study(
                study_id="confirmatory-v2-preaudit",
                seeds=protocol.amended_confirmatory_ensemble.seeds,
                config_path=config_path,
                geography_path=geography_path,
                policy_path=policy_path,
                generator_version="delta-small-generator-v3",
                legacy_duration_table=False,
            ),
            _study(
                study_id="confirmatory-v3-spatial-preaudit",
                seeds=protocol.final_confirmatory_ensemble.seeds,
                config_path=config_path,
                geography_path=geography_path,
                policy_path=policy_path,
                generator_version="delta-small-generator-v4",
                legacy_duration_table=False,
            ),
            _study(
                study_id="confirmatory-v4-primary",
                seeds=protocol.spatial_confirmatory_ensemble.seeds,
                config_path=config_path,
                geography_path=geography_path,
                policy_path=policy_path,
                generator_version="delta-small-generator-v5",
                legacy_duration_table=False,
            ),
        ],
    }
    studies = report["studies"]
    assert isinstance(studies, list)
    for study in studies:
        assert isinstance(study, dict)
        call_count = study["call_count"]
        ratio = study["peak_demand_capacity_ratio"]
        assert isinstance(call_count, dict)
        assert isinstance(ratio, dict)
        hourly_intervals = call_count["hourly_mean_95"]
        assert isinstance(hourly_intervals, list)
        peak_hour_interval = hourly_intervals[3]
        assert isinstance(peak_hour_interval, dict)
        total_call_gate = (
            abs(float(call_count["estimate"]) - protocol.call_process.expected_total_mean)
            <= protocol.call_process.total_mean_absolute_tolerance
        )
        peak_intensity_gate = (
            float(peak_hour_interval["lower_95"])
            <= protocol.call_process.configured_peak_intensity_per_hour
            <= float(peak_hour_interval["upper_95"])
        )
        ratio_gate = (
            protocol.demand_capacity.confirmatory_median_minimum
            <= float(ratio["estimate"])
            <= protocol.demand_capacity.confirmatory_median_maximum
        )
        study["registered_gate_evaluation"] = {
            "total_call_mean_within_absolute_tolerance": total_call_gate,
            "configured_peak_intensity_within_hour_4_mean_95_ci": peak_intensity_gate,
            "median_peak_ratio_within_registered_band": ratio_gate,
            "all_registered_numeric_gates_met": (
                total_call_gate and peak_intensity_gate and ratio_gate
            ),
        }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(canonical_json_bytes(report))
    return report
