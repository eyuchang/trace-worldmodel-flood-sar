"""Registered acceptance-gate evaluation without study execution side effects."""

from __future__ import annotations

from typing import Any, cast

from trace_jepa.scenario.delta.domain import GeneratedScenario
from trace_jepa.scenario.delta.domain.acceptance import DeltaSmallAcceptanceConfig
from trace_jepa.scenario.delta.runtime import DeltaRunResult
from trace_jepa.scenario.delta.validation.verification import trace_artifacts_verify


def reconciliation_claims(paired: dict[str, object]) -> dict[str, bool]:
    metrics = cast(dict[str, Any], paired["metrics"])
    false_merge = metrics["false_merge_rate"]["paired_difference_selected_minus_baseline"]
    recall = metrics["pairwise_recall"]["paired_difference_selected_minus_baseline"]
    return {
        "false_merge_improvement": float(false_merge["upper_95"]) < 0.0,
        "recall_noninferiority": float(recall["lower_95"]) > -0.05,
    }


def confirmatory_gates(
    study: dict[str, object],
    protocol: DeltaSmallAcceptanceConfig,
    elapsed_seconds: float,
) -> tuple[dict[str, bool], dict[str, bool]]:
    call_count = cast(dict[str, Any], study["call_count"])
    peak_hour = cast(list[dict[str, Any]], call_count["hourly_mean_95"])[3]
    channel = cast(dict[str, Any], study["observation_channel"])
    operations = cast(dict[str, Any], study["operations"])
    channel_gates = {
        name: abs(float(channel[name]["estimate"]) - expected)
        <= protocol.observation_channel.point_absolute_tolerances[name]
        for name, expected in protocol.observation_channel.expected_point_estimates.items()
    }
    gates = {
        "observed_call_mean_within_absolute_tolerance": (
            abs(float(call_count["estimate"]) - protocol.call_process.expected_total_mean)
            <= protocol.call_process.total_mean_absolute_tolerance
        ),
        "configured_peak_inside_hour_four_mean_95_interval": (
            float(peak_hour["lower_95"])
            <= protocol.call_process.configured_peak_intensity_per_hour
            <= float(peak_hour["upper_95"])
        ),
        "observation_channel_points_within_frozen_tolerances": all(channel_gates.values()),
        "nonzero_operational_means": all(
            float(operations[name]["estimate"]) > 0
            for name in ("allocations", "refusals", "repairs")
        ),
        "all_trace_and_outcome_links_verified": bool(operations["all_trace_artifacts_verified"]),
        "no_overlapping_incident_episode_violations": bool(operations["all_episode_keys_unique"]),
        "runtime_below_55_seconds": (
            elapsed_seconds <= protocol.performance.maximum_generate_run_replay_s
        ),
    }
    return gates, channel_gates


def book_gates(
    scenario: GeneratedScenario,
    result: DeltaRunResult,
    protocol: DeltaSmallAcceptanceConfig,
) -> tuple[dict[str, bool], float]:
    del scenario
    outcome_total = result.allocated + result.refused
    allocation_share = result.allocated / outcome_total if outcome_total else 0.0
    gates = {
        "allocation_share_within_registered_band": (
            protocol.demand_capacity.book_allocation_share_minimum
            <= allocation_share
            <= protocol.demand_capacity.book_allocation_share_maximum
        ),
        "has_allocation_refusal_and_visible_evidence_repair": (
            result.allocated > 0 and result.refused > 0 and result.repaired > 0
        ),
        "trace_and_outcome_links_verified": trace_artifacts_verify(result),
    }
    return gates, allocation_share
