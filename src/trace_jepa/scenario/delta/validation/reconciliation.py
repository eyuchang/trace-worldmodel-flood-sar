"""Paired reconciliation evaluation for registered Delta studies."""

from __future__ import annotations

from pathlib import Path

from trace_jepa.scenario.delta.evaluation import evaluate_partitions
from trace_jepa.scenario.delta.generator import generate_delta_small_from_models
from trace_jepa.scenario.delta.loading import load_geography_catalog, load_scenario_config
from trace_jepa.scenario.delta.reconciliation import (
    baseline_v7_clusters,
    evidence_graph_clusters,
)
from trace_jepa.scenario.delta.reconciliation_selection import (
    CANONICAL_RECONCILIATION_ALGORITHM,
)
from trace_jepa.scenario.delta.validation.statistics import cluster_mean_interval

_METRIC_NAMES = (
    "false_merge_rate",
    "pairwise_precision",
    "pairwise_recall",
    "pairwise_f1",
    "adjusted_rand_index",
    "missed_link_rate",
    "false_report_merge_rate",
)


def _reference_partition(scenario: object) -> tuple[dict[str, str], set[str]]:
    observations = scenario.observations  # type: ignore[attr-defined]
    reference = {
        item.call_id: (
            item.truth_incident_id
            if item.truth_incident_id is not None
            else f"false-singleton:{item.call_id}"
        )
        for item in observations.lineage
    }
    false_ids = {
        item.call_id for item in observations.lineage if item.truth_incident_id is None
    }
    return reference, false_ids


def _seed_row(seed: int, config_path: Path, geography_path: Path) -> dict[str, float | int]:
    config = load_scenario_config(config_path)
    geography = load_geography_catalog(geography_path)
    scenario = generate_delta_small_from_models(
        config.model_copy(update={"seed": seed}),
        geography,
        config_path.resolve(strict=True),
    )
    calls = sorted(
        scenario.observations.calls,
        key=lambda item: (item.received_s, item.call_id),
    )
    reference, false_ids = _reference_partition(scenario)
    baseline = evaluate_partitions(reference, baseline_v7_clusters(calls), false_ids)
    selected = evaluate_partitions(
        reference,
        evidence_graph_clusters(calls, CANONICAL_RECONCILIATION_ALGORITHM).cluster_by_call,
        false_ids,
    )
    row: dict[str, float | int] = {"seed": seed}
    for metric in _METRIC_NAMES:
        baseline_value = float(getattr(baseline, metric))
        selected_value = float(getattr(selected, metric))
        row[f"baseline_{metric}"] = baseline_value
        row[f"selected_{metric}"] = selected_value
        row[f"difference_{metric}"] = selected_value - baseline_value
    return row


def _metric_summary(
    metric: str,
    rows: list[dict[str, float | int]],
    protocol_hash: str,
    study_id: str,
) -> dict[str, object]:
    baseline = [float(row[f"baseline_{metric}"]) for row in rows]
    selected = [float(row[f"selected_{metric}"]) for row in rows]
    differences = [float(row[f"difference_{metric}"]) for row in rows]
    return {
        "baseline": cluster_mean_interval(
            baseline, protocol_hash, f"{study_id}:baseline:{metric}"
        ),
        "selected": cluster_mean_interval(
            selected, protocol_hash, f"{study_id}:selected:{metric}"
        ),
        "paired_difference_selected_minus_baseline": cluster_mean_interval(
            differences,
            protocol_hash,
            f"{study_id}:paired-difference:{metric}",
        ),
    }


def paired_reconciliation_report(
    *,
    seeds: list[int],
    config_path: Path,
    geography_path: Path,
    protocol_hash: str,
    study_id: str,
) -> dict[str, object]:
    """Evaluate selected and immutable baseline clustering on identical seeds."""

    rows = [_seed_row(seed, config_path, geography_path) for seed in seeds]
    return {
        "baseline_algorithm_id": "baseline-v7-heuristic",
        "selected_algorithm_id": CANONICAL_RECONCILIATION_ALGORITHM,
        "cluster_unit": "one-complete-seed-run",
        "metrics": {
            metric: _metric_summary(metric, rows, protocol_hash, study_id)
            for metric in _METRIC_NAMES
        },
        "per_seed": rows,
    }
