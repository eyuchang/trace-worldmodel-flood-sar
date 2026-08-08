"""Immutable v7 heuristic retained solely for paired protocol comparisons."""

from __future__ import annotations

from trace_jepa.scenario.delta.domain import CallRecord

from .evidence import distance_m


def baseline_v7_visible_relationship(
    call: CallRecord,
    earlier_calls: list[CallRecord],
    cluster_by_call: dict[str, str],
) -> tuple[str, tuple[str, ...]]:
    if call.quality.revision_of_call_id is not None:
        source = call.quality.revision_of_call_id
        return cluster_by_call.get(source, source), ("explicit_report_revision", source)
    for previous in reversed(earlier_calls):
        if call.callback_token == previous.callback_token:
            return cluster_by_call[previous.call_id], (
                "shared_synthetic_callback_token",
                previous.call_id,
            )
    for previous in reversed(earlier_calls):
        if abs(call.received_s - previous.received_s) > 600:
            continue
        if call.reported.call_type != previous.reported.call_type:
            continue
        if distance_m(call, previous) <= (
            call.location.precision_m + previous.location.precision_m
        ):
            return cluster_by_call[previous.call_id], (
                "spatiotemporal_taxonomy_similarity",
                previous.call_id,
            )
    return call.call_id, ()


def baseline_v7_clusters(calls: list[CallRecord]) -> dict[str, str]:
    earlier: list[CallRecord] = []
    clusters: dict[str, str] = {}
    for call in calls:
        cluster, _basis = baseline_v7_visible_relationship(call, earlier, clusters)
        clusters[call.call_id] = cluster
        earlier.append(call)
    return clusters
