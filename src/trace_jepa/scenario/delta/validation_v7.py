from __future__ import annotations

import hashlib
import math
import random
import statistics
import tempfile
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from trace_jepa.predictor import ToyActionPrefixPredictor
from trace_jepa.scenario.delta.acceptance import DeltaSmallAcceptanceConfig
from trace_jepa.scenario.delta.artifacts import canonical_json_bytes, sha256_file
from trace_jepa.scenario.delta.domain import GeneratedScenario
from trace_jepa.scenario.delta.generator import generate_delta_small_from_models
from trace_jepa.scenario.delta.loading import load_geography_catalog, load_scenario_config
from trace_jepa.scenario.delta.pipeline import execute_delta_small, verify_exact_replay
from trace_jepa.scenario.delta.runner import DeltaRunResult, run_delta_small

_BOOTSTRAP_RESAMPLES = 10_000


def _bootstrap_rng(protocol_hash: str, metric_name: str) -> random.Random:
    digest = hashlib.sha256(f"{protocol_hash}|{metric_name}|cluster-bootstrap-v1".encode()).digest()
    return random.Random(int.from_bytes(digest[:16], "big"))


def _percentile_interval(samples: list[float]) -> tuple[float, float]:
    ordered = sorted(samples)
    return ordered[249], ordered[9_749]


def _cluster_mean_interval(
    values: Sequence[float], protocol_hash: str, metric_name: str
) -> dict[str, object]:
    if not values:
        raise ValueError(f"cluster interval requires at least one value: {metric_name}")
    rng = _bootstrap_rng(protocol_hash, metric_name)
    size = len(values)
    samples = [
        statistics.fmean(values[rng.randrange(size)] for _ in range(size))
        for _ in range(_BOOTSTRAP_RESAMPLES)
    ]
    lower, upper = _percentile_interval(samples)
    return {
        "estimate": statistics.fmean(values),
        "lower_95": lower,
        "upper_95": upper,
        "method": "deterministic-seed-cluster-percentile-bootstrap-10000-v1",
        "bootstrap_seed_derivation": (
            f"sha256({protocol_hash}|{metric_name}|cluster-bootstrap-v1)"
        ),
    }


def _cluster_fraction_interval(
    counts: Sequence[tuple[int, int]], protocol_hash: str, metric_name: str
) -> dict[str, object]:
    if not counts or sum(denominator for _numerator, denominator in counts) == 0:
        raise ValueError(f"cluster fraction requires a positive denominator: {metric_name}")
    rng = _bootstrap_rng(protocol_hash, metric_name)
    size = len(counts)
    samples: list[float] = []
    for _ in range(_BOOTSTRAP_RESAMPLES):
        selected = [counts[rng.randrange(size)] for _index in range(size)]
        denominator = sum(item[1] for item in selected)
        samples.append(sum(item[0] for item in selected) / denominator if denominator else 0.0)
    lower, upper = _percentile_interval(samples)
    denominator = sum(item[1] for item in counts)
    return {
        "estimate": sum(item[0] for item in counts) / denominator,
        "lower_95": lower,
        "upper_95": upper,
        "method": "deterministic-seed-cluster-ratio-bootstrap-10000-v1",
        "cluster_count": len(counts),
        "bootstrap_seed_derivation": (
            f"sha256({protocol_hash}|{metric_name}|cluster-bootstrap-v1)"
        ),
    }


def _exact_median_interval(values: Sequence[float]) -> dict[str, object]:
    if not values:
        raise ValueError("median interval requires at least one value")
    ordered = sorted(values)
    size = len(ordered)
    cumulative = 0.0
    tail_index = -1
    for successes in range(size + 1):
        cumulative += math.comb(size, successes) * (0.5**size)
        if cumulative <= 0.025:
            tail_index = successes
        else:
            break
    lower_index = max(0, tail_index)
    upper_index = min(size - 1, size - tail_index - 1)
    return {
        "estimate": statistics.median(ordered),
        "lower_95": ordered[lower_index],
        "upper_95": ordered[upper_index],
        "method": "exact-binomial-order-statistic-median-95-v1",
        "lower_order_statistic_one_based": lower_index + 1,
        "upper_order_statistic_one_based": upper_index + 1,
    }


def _trace_artifacts_verify(result: DeltaRunResult) -> bool:
    if not result.trace_chain_verified:
        return False
    evidence_ids = {item.evidence_id for item in result.evidence}
    records = {(item.record_id, item.record_version): item for item in result.trace_records}
    if any(not set(record.evidence_refs) <= evidence_ids for record in result.trace_records):
        return False
    for record in result.trace_records:
        if record.record_version == 1:
            if (
                record.supersedes_record_id is not None
                or record.supersedes_record_version is not None
            ):
                return False
        elif (
            record.supersedes_record_id != record.record_id
            or record.supersedes_record_version != record.record_version - 1
            or (record.record_id, record.record_version - 1) not in records
        ):
            return False
    commitment_ids = {item.commitment_id for item in result.commitments}
    if commitment_ids != {item.authorizing_commitment_id for item in result.outcomes}:
        return False
    commitment_by_id = {item.commitment_id: item for item in result.commitments}
    if any(
        (
            outcome.authorizing_trace_record_id,
            outcome.authorizing_trace_record_version,
        )
        != (
            commitment_by_id[outcome.authorizing_commitment_id].authorizing_record_id,
            commitment_by_id[outcome.authorizing_commitment_id].authorizing_record_version,
        )
        for outcome in result.outcomes
    ):
        return False
    for commitment in result.commitments:
        authorizing_record = records.get(
            (commitment.authorizing_record_id, commitment.authorizing_record_version)
        )
        if authorizing_record is None or not authorizing_record.consumer_actions:
            return False
        if authorizing_record.consumer_actions[-1].decision.value != "clear":
            return False
        if not any(
            event.commitment_id == commitment.commitment_id
            and (event.trace_record_id, event.trace_record_version)
            == (commitment.authorizing_record_id, commitment.authorizing_record_version)
            for event in result.decisions
        ):
            return False
    return all(
        (event.trace_record_id, event.trace_record_version) in records for event in result.decisions
    )


def _seed_row(scenario: GeneratedScenario, result: DeltaRunResult) -> dict[str, Any]:
    calls = scenario.observations.calls
    lineage = scenario.observations.lineage
    relationship_counts = Counter(item.relationship for item in lineage)
    method_counts = Counter(item.location.method for item in calls)
    incident_by_id = {item.incident_id: item for item in scenario.truth.incidents}
    structure_by_id = {item.structure_id: item for item in scenario.truth.structures}
    call_by_id = {item.call_id: item for item in calls}
    reported_incidents = {
        item.truth_incident_id for item in lineage if item.truth_incident_id is not None
    }
    location_errors: list[float] = []
    for link in lineage:
        if link.truth_incident_id is None:
            continue
        call = call_by_id[link.call_id]
        incident = incident_by_id[link.truth_incident_id]
        structure = structure_by_id[incident.structure_id]
        location_errors.append(
            math.hypot(
                call.location.easting_mm - structure.easting_mm,
                call.location.northing_mm - structure.northing_mm,
            )
            / 1000.0
        )
    channel_counts = {
        relationship: (relationship_counts[relationship], len(calls))
        for relationship in (
            "duplicate",
            "multi_channel",
            "revision",
            "conflicting_report",
            "false_report",
        )
    }
    channel_counts.update(
        {
            "callback_failure": (
                sum(call.quality.callback_failed for call in calls),
                len(calls),
            ),
            "dropped_call": (sum(call.quality.call_dropped for call in calls), len(calls)),
            "nonreporting": (
                len(scenario.truth.incidents) - len(reported_incidents),
                len(scenario.truth.incidents),
            ),
            "location_gps_or_address_intersection": (
                method_counts["gps-or-address-intersection"],
                len(calls),
            ),
            "location_landmark": (method_counts["landmark"], len(calls)),
            "location_cell_sector": (method_counts["cell-sector"], len(calls)),
        }
    )
    reconciliation = result.reconciliation_evaluation
    accepted_episode_keys = [
        item.episode_key
        for item in getattr(scenario.truth, "candidate_audit", [])
        if item.disposition == "accepted_as_truth_incident"
    ]
    return {
        "seed": scenario.config.seed,
        "latent_incidents": len(scenario.truth.incidents),
        "observed_calls": len(calls),
        "hourly_calls": [
            sum(hour * 3_600 <= call.received_s < (hour + 1) * 3_600 for call in calls)
            for hour in range(6)
        ],
        "channel_counts": channel_counts,
        "location_error_mean_m": statistics.fmean(location_errors) if location_errors else 0.0,
        "peak_strict_concurrent_load_ratio": (
            result.peak_strict_concurrent_load_ratio_milli / 1000.0
        ),
        "strict_unserviceable_windows": result.strict_unserviceable_windows,
        "peak_uncapped_compatible_load_ratio": (
            result.peak_uncapped_compatible_load_ratio_milli / 1000.0
        ),
        "uncapped_unserviceable_windows": result.uncapped_unserviceable_windows,
        "peak_registered_normalized_coverable_load_index": (
            result.peak_registered_normalized_coverable_load_index_milli / 1000.0
        ),
        "historical_capped_unserviceable_windows": (result.historical_capped_unserviceable_windows),
        "peak_finite_residual_strict_pressure_ratio": (
            result.peak_finite_residual_strict_pressure_ratio_milli / 1000.0
        ),
        "residual_strict_unserviceable_windows": (result.residual_strict_unserviceable_windows),
        "allocations": result.allocated,
        "refusals": result.refused,
        "repairs": result.repaired,
        "trace_artifacts_verified": _trace_artifacts_verify(result),
        "episode_overlap_violations": len(accepted_episode_keys) - len(set(accepted_episode_keys)),
        "reconciliation": {
            "pairwise_precision": reconciliation.pairwise_precision,
            "pairwise_recall": reconciliation.pairwise_recall,
            "pairwise_f1": reconciliation.pairwise_f1,
            "false_merge_rate": reconciliation.false_merge_rate,
            "missed_link_rate": reconciliation.missed_link_rate,
            "false_report_merge_rate": reconciliation.false_report_merge_rate,
            "revision_link_precision": reconciliation.revision_link_precision,
            "revision_link_recall": reconciliation.revision_link_recall,
            "reported_occupant_revision_truth_accuracy": (
                reconciliation.reported_occupant_revision_truth_accuracy
            ),
            "adjusted_rand_index": reconciliation.adjusted_rand_index,
        },
    }


def _metric_summary(
    rows: Sequence[dict[str, Any]],
    key: str,
    protocol_hash: str,
    *,
    median: bool = False,
) -> dict[str, object]:
    values = [float(row[key]) for row in rows]
    interval = (
        _exact_median_interval(values)
        if median
        else _cluster_mean_interval(values, protocol_hash, key)
    )
    return {
        **interval,
        "mean": statistics.fmean(values),
        "minimum": min(values),
        "maximum": max(values),
    }


def run_v7_study(
    *,
    study_id: str,
    seeds: Sequence[int],
    config_path: Path,
    geography_path: Path,
    policy_path: Path,
    protocol_hash: str,
) -> dict[str, object]:
    config = load_scenario_config(config_path)
    geography = load_geography_catalog(geography_path)
    predictor = ToyActionPrefixPredictor()
    rows: list[dict[str, Any]] = []
    for seed in seeds:
        scenario = generate_delta_small_from_models(
            config.model_copy(update={"seed": seed}),
            geography,
            config_path.resolve(strict=True),
        )
        rows.append(_seed_row(scenario, run_delta_small(scenario, predictor, policy_path)))
    call_values = [float(row["observed_calls"]) for row in rows]
    hourly = [
        _cluster_mean_interval(
            [float(row["hourly_calls"][hour]) for row in rows],
            protocol_hash,
            f"{study_id}:hour-{hour + 1}-calls",
        )
        for hour in range(6)
    ]
    channel_names = sorted(rows[0]["channel_counts"])
    channel = {
        name: _cluster_fraction_interval(
            [tuple(row["channel_counts"][name]) for row in rows],
            protocol_hash,
            f"{study_id}:observation:{name}",
        )
        for name in channel_names
    }
    location_error = _cluster_mean_interval(
        [float(row["location_error_mean_m"]) for row in rows],
        protocol_hash,
        f"{study_id}:per-seed-mean-location-error-m",
    )
    reconciliation_names = sorted(rows[0]["reconciliation"])
    reconciliation = {
        name: _cluster_mean_interval(
            [float(row["reconciliation"][name]) for row in rows],
            protocol_hash,
            f"{study_id}:reconciliation:{name}",
        )
        for name in reconciliation_names
    }
    operations: dict[str, object] = {
        name: _cluster_mean_interval(
            [float(row[name]) for row in rows], protocol_hash, f"{study_id}:operation:{name}"
        )
        for name in ("allocations", "refusals", "repairs")
    }
    operations.update(
        {
            "strict_unserviceable_windows": _cluster_mean_interval(
                [float(row["strict_unserviceable_windows"]) for row in rows],
                protocol_hash,
                f"{study_id}:strict-unserviceable-windows",
            ),
            "residual_strict_unserviceable_windows": _cluster_mean_interval(
                [float(row["residual_strict_unserviceable_windows"]) for row in rows],
                protocol_hash,
                f"{study_id}:residual-strict-unserviceable-windows",
            ),
            "all_trace_artifacts_verified": all(
                bool(row["trace_artifacts_verified"]) for row in rows
            ),
            "all_episode_keys_unique": all(
                int(row["episode_overlap_violations"]) == 0 for row in rows
            ),
        }
    )
    return {
        "study_id": study_id,
        "seed_count": len(seeds),
        "generator_version": config.generator_version,
        "seeds": list(seeds),
        "call_count": {
            **_cluster_mean_interval(call_values, protocol_hash, f"{study_id}:observed-calls"),
            "minimum": min(call_values),
            "maximum": max(call_values),
            "hourly_mean_95": hourly,
        },
        "peak_strict_concurrent_load_ratio": _metric_summary(
            rows, "peak_strict_concurrent_load_ratio", protocol_hash, median=True
        ),
        "peak_uncapped_compatible_load_ratio": _metric_summary(
            rows, "peak_uncapped_compatible_load_ratio", protocol_hash, median=True
        ),
        "peak_registered_normalized_coverable_load_index": _metric_summary(
            rows,
            "peak_registered_normalized_coverable_load_index",
            protocol_hash,
            median=True,
        ),
        "peak_finite_residual_strict_pressure_ratio": _metric_summary(
            rows, "peak_finite_residual_strict_pressure_ratio", protocol_hash, median=True
        ),
        "observation_channel": channel,
        "per_seed_mean_location_error_m": location_error,
        "reconciliation": reconciliation,
        "operations": operations,
        "per_seed": rows,
    }


def _verify_frozen_inputs(
    protocol: DeltaSmallAcceptanceConfig,
    repository_root: Path,
) -> None:
    paths = {
        "scenario_configuration": repository_root / "configs/scenarios/wf_dfld_01_small.yaml",
        "process_calibration": (
            repository_root / "data/scenario/delta/calibration/v7_process_coefficients_v1.json"
        ),
        "truth_implementation": repository_root / "src/trace_jepa/scenario/delta/truth_v7.py",
        "observation_implementation": repository_root
        / "src/trace_jepa/scenario/delta/observations_v7.py",
        "coordination_implementation": repository_root
        / "src/trace_jepa/scenario/delta/coordination.py",
        "runtime_and_capacity_implementation": repository_root
        / "src/trace_jepa/scenario/delta/runner.py",
        "reconciliation_implementation": repository_root
        / "src/trace_jepa/scenario/delta/evaluation.py",
        "geography_catalog": repository_root
        / "data/scenario/delta/geography/delta_small_geography_v3.yaml",
        "geography_build_manifest": repository_root
        / "data/scenario/delta/geography/build_manifest_v3.json",
        "environment_contract": repository_root
        / "data/scenario/delta/environment/python311_linux_amd64_v1.json",
        "dependency_lock": repository_root / "requirements-delta-python311.lock",
        "trace_policy": repository_root / "configs/policies/trace_delta_small_v1.yaml",
    }
    if set(paths) != set(protocol.frozen_input_sha256):
        raise ValueError("registered frozen-input keys disagree with validator requirements")
    mismatches = [
        name
        for name, path in paths.items()
        if sha256_file(path) != protocol.frozen_input_sha256[name]
    ]
    if mismatches:
        raise ValueError(f"frozen inputs changed after preregistration: {sorted(mismatches)}")


def _book_and_performance(
    config_path: Path,
    geography_path: Path,
    policy_path: Path,
) -> tuple[GeneratedScenario, DeltaRunResult, float]:
    config = load_scenario_config(config_path)
    geography = load_geography_catalog(geography_path)
    scenario = generate_delta_small_from_models(config, geography, config_path.resolve(strict=True))
    result = run_delta_small(scenario, ToyActionPrefixPredictor(), policy_path)
    with tempfile.TemporaryDirectory(prefix="delta-v7-performance-") as temporary:
        root = Path(temporary)
        started = time.perf_counter()
        execute_delta_small(
            config_path,
            geography_path,
            policy_path,
            root / "reference",
            ToyActionPrefixPredictor(),
        )
        verify_exact_replay(
            config_path,
            geography_path,
            policy_path,
            root / "reference",
            root / "replay",
            ToyActionPrefixPredictor(),
        )
        elapsed = time.perf_counter() - started
    return scenario, result, elapsed


def run_v7_registered_validation(
    *,
    protocol: DeltaSmallAcceptanceConfig,
    config_path: Path,
    geography_path: Path,
    policy_path: Path,
    acceptance_path: Path,
    output_path: Path,
) -> dict[str, object]:
    if output_path.exists():
        raise FileExistsError(
            f"registered validation output already exists and will not be overwritten: {output_path}"
        )
    repository_root = Path(__file__).resolve().parents[4]
    _verify_frozen_inputs(protocol, repository_root)
    confirmatory = protocol.v7_confirmatory_ensemble
    if confirmatory is None or len(confirmatory.seeds) != 100:
        raise ValueError("acceptance v7 requires exactly 100 confirmatory-v6 seeds")
    protocol_hash = sha256_file(acceptance_path)
    development_seeds = list(
        range(
            protocol.development_ensemble.first_seed,
            protocol.development_ensemble.first_seed + protocol.development_ensemble.seed_count,
        )
    )
    studies = [
        run_v7_study(
            study_id="development-v7",
            seeds=development_seeds,
            config_path=config_path,
            geography_path=geography_path,
            policy_path=policy_path,
            protocol_hash=protocol_hash,
        ),
        run_v7_study(
            study_id="confirmatory-v6-primary",
            seeds=confirmatory.seeds,
            config_path=config_path,
            geography_path=geography_path,
            policy_path=policy_path,
            protocol_hash=protocol_hash,
        ),
    ]
    primary = studies[1]
    call_count = primary["call_count"]
    assert isinstance(call_count, dict)
    hourly = call_count["hourly_mean_95"]
    assert isinstance(hourly, list)
    peak_hour = hourly[3]
    assert isinstance(peak_hour, dict)
    channel = primary["observation_channel"]
    operations = primary["operations"]
    assert isinstance(channel, dict) and isinstance(operations, dict)
    channel_gates = {
        name: abs(float(channel[name]["estimate"]) - expected)
        <= protocol.observation_channel.point_absolute_tolerances[name]
        for name, expected in protocol.observation_channel.expected_point_estimates.items()
    }
    book_scenario, book_result, elapsed = _book_and_performance(
        config_path, geography_path, policy_path
    )
    allocation_denominator = book_result.allocated + book_result.refused
    allocation_share = (
        book_result.allocated / allocation_denominator if allocation_denominator else 0.0
    )
    book_gates = {
        "allocation_share_within_registered_band": (
            protocol.demand_capacity.book_allocation_share_minimum
            <= allocation_share
            <= protocol.demand_capacity.book_allocation_share_maximum
        ),
        "has_allocation_refusal_and_visible_evidence_repair": (
            book_result.allocated > 0 and book_result.refused > 0 and book_result.repaired > 0
        ),
        "trace_artifacts_verified": _trace_artifacts_verify(book_result),
    }
    confirmatory_gates = {
        "observed_call_mean_within_absolute_tolerance": (
            abs(float(call_count["estimate"]) - protocol.call_process.expected_total_mean)
            <= protocol.call_process.total_mean_absolute_tolerance
        ),
        "configured_peak_inside_peak_hour_mean_95_interval": (
            float(peak_hour["lower_95"])
            <= protocol.call_process.configured_peak_intensity_per_hour
            <= float(peak_hour["upper_95"])
        ),
        "observation_channel_points_within_frozen_tolerances": all(channel_gates.values()),
        "nonzero_allocation_refusal_and_repair_means": all(
            float(operations[name]["estimate"]) > 0
            for name in ("allocations", "refusals", "repairs")
        ),
        "all_trace_artifacts_verified": bool(operations["all_trace_artifacts_verified"]),
        "generate_run_and_replay_below_55_seconds": (
            elapsed <= protocol.performance.maximum_generate_run_replay_s
        ),
    }
    report: dict[str, object] = {
        "schema_version": "delta-statistical-validation-v3",
        "execution_policy": "write-once-no-overwrite-confirmatory-v6",
        "protocol_sha256": protocol_hash,
        "registration_erratum": protocol.registration_erratum,
        "scenario_configuration_sha256": sha256_file(config_path),
        "geography_sha256": sha256_file(geography_path),
        "policy_sha256": sha256_file(policy_path),
        "book_seed_role": protocol.book_seed_role,
        "book_walkthrough": {
            "seed": protocol.book_seed,
            "observed_calls": len(book_scenario.observations.calls),
            "latent_incidents": len(book_scenario.truth.incidents),
            "peak_strict_concurrent_load_ratio": (
                book_result.peak_strict_concurrent_load_ratio_milli / 1000.0
            ),
            "strict_unserviceable_windows": book_result.strict_unserviceable_windows,
            "peak_uncapped_compatible_load_ratio": (
                book_result.peak_uncapped_compatible_load_ratio_milli / 1000.0
            ),
            "peak_registered_normalized_coverable_load_index": (
                book_result.peak_registered_normalized_coverable_load_index_milli / 1000.0
            ),
            "peak_finite_residual_strict_pressure_ratio": (
                book_result.peak_finite_residual_strict_pressure_ratio_milli / 1000.0
            ),
            "residual_strict_unserviceable_windows": (
                book_result.residual_strict_unserviceable_windows
            ),
            "allocations": book_result.allocated,
            "refusals": book_result.refused,
            "visible_evidence_repairs": book_result.repaired,
            "allocation_share_among_allocation_refusal": allocation_share,
            "reconciliation": book_result.reconciliation_evaluation.model_dump(mode="json"),
            "registered_gate_evaluation": book_gates,
        },
        "confirmatory_gate_evaluation": {
            **confirmatory_gates,
            "observation_channel_metric_gates": channel_gates,
            "all_registered_gates_met": (
                all(book_gates.values()) and all(confirmatory_gates.values())
            ),
            "strict_load_numeric_gate": None,
        },
        "performance": {
            "generate_run_and_exact_replay_seconds": elapsed,
            "maximum_seconds": protocol.performance.maximum_generate_run_replay_s,
        },
        "inference": protocol.inference.model_dump(mode="json") if protocol.inference else None,
        "claims_limit": [
            "synthetic-generator-process-validation-not-field-effectiveness",
            "seed-cluster-intervals-describe-registered-synthetic-seed-variation",
            "strict-load-has-no-post-hoc-numerical-acceptance-band",
            "automatic-aid-schedule-is-a-frozen-teaching-assumption",
            "no-operational-readiness-or-field-generalization-claim",
        ],
        "preserved_protocol_history": {
            "v5_validation_sha256": (
                "d51e17364c254032a8118a9de633425c82f9689c7a523582a5706e40238b817b"
            ),
            "v6_validation_sha256": (
                "2754b9d92c2df4e0c20026a388e092ec1039b315d38617c76ac8b3be8d44a24c"
            ),
            "interpretation": "retained_history_not_recomputed_as_v7",
        },
        "studies": studies,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.is_symlink():
        raise ValueError("validation output must not be a symlink")
    output_path.write_bytes(canonical_json_bytes(report))
    return report
