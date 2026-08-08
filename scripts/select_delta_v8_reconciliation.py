from __future__ import annotations

import argparse
import statistics
from pathlib import Path
from typing import Any

from trace_jepa.scenario.delta.artifacts import canonical_json_bytes, sha256_file
from trace_jepa.scenario.delta.evaluation import ReconciliationEvaluation, evaluate_partitions
from trace_jepa.scenario.delta.generator import generate_delta_small_from_models
from trace_jepa.scenario.delta.loading import (
    load_acceptance_config,
    load_geography_catalog,
    load_scenario_config,
)
from trace_jepa.scenario.delta.reconciliation_v8 import (
    EVIDENCE_GRAPH_CANDIDATES,
    baseline_v7_clusters,
    evidence_graph_clusters,
)


def _evaluation(
    scenario: Any,
    predicted: dict[str, str],
) -> ReconciliationEvaluation:
    reference = {
        link.call_id: (
            link.truth_incident_id
            if link.truth_incident_id is not None
            else f"false-singleton:{link.call_id}"
        )
        for link in scenario.observations.lineage
    }
    false_ids = {
        link.call_id for link in scenario.observations.lineage if link.truth_incident_id is None
    }
    return evaluate_partitions(reference, predicted, false_ids)


def _mean(values: list[float]) -> float:
    return statistics.fmean(values)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select the v8 visible-evidence graph using only development seeds."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--geography", type=Path, required=True)
    parser.add_argument("--acceptance", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.output.exists() or arguments.output.is_symlink():
        raise FileExistsError(f"selection output already exists: {arguments.output}")

    config = load_scenario_config(arguments.config)
    geography = load_geography_catalog(arguments.geography)
    acceptance = load_acceptance_config(arguments.acceptance)
    seeds = list(
        range(
            acceptance.development_ensemble.first_seed,
            acceptance.development_ensemble.first_seed + acceptance.development_ensemble.seed_count,
        )
    )
    metrics = (
        "false_merge_rate",
        "pairwise_precision",
        "pairwise_recall",
        "pairwise_f1",
        "adjusted_rand_index",
        "missed_link_rate",
        "false_report_merge_rate",
    )
    per_seed: dict[str, list[dict[str, float | int]]] = {"baseline-v7-heuristic": []}
    per_seed.update({algorithm_id: [] for algorithm_id in EVIDENCE_GRAPH_CANDIDATES})
    for seed_index, seed in enumerate(seeds):
        scenario = generate_delta_small_from_models(
            config.model_copy(update={"seed": seed}),
            geography,
            arguments.config.resolve(strict=True),
        )
        calls = sorted(
            scenario.observations.calls,
            key=lambda call: (call.received_s, call.call_id),
        )
        predicted_by_algorithm = {
            "baseline-v7-heuristic": baseline_v7_clusters(calls),
            **{
                algorithm_id: evidence_graph_clusters(calls, algorithm_id).cluster_by_call
                for algorithm_id in EVIDENCE_GRAPH_CANDIDATES
            },
        }
        for algorithm_id, predicted in predicted_by_algorithm.items():
            result = _evaluation(scenario, predicted)
            per_seed[algorithm_id].append(
                {
                    "seed_index": seed_index,
                    "seed": seed,
                    **{metric: float(getattr(result, metric)) for metric in metrics},
                }
            )

    baseline_rows = per_seed["baseline-v7-heuristic"]
    candidate_reports: dict[str, dict[str, object]] = {}
    eligible: list[str] = []
    recall_floor_candidates: list[str] = []
    for algorithm_id in EVIDENCE_GRAPH_CANDIDATES:
        rows = per_seed[algorithm_id]
        folds: list[dict[str, object]] = []
        every_fold_eligible = True
        for fold in range(5):
            indexes = [index for index in range(len(seeds)) if index % 5 == fold]
            baseline_false_merge = _mean(
                [float(baseline_rows[index]["false_merge_rate"]) for index in indexes]
            )
            candidate_false_merge = _mean(
                [float(rows[index]["false_merge_rate"]) for index in indexes]
            )
            baseline_recall = _mean(
                [float(baseline_rows[index]["pairwise_recall"]) for index in indexes]
            )
            candidate_recall = _mean([float(rows[index]["pairwise_recall"]) for index in indexes])
            fold_eligible = (
                candidate_false_merge < baseline_false_merge
                and candidate_recall - baseline_recall >= -0.05
            )
            every_fold_eligible = every_fold_eligible and fold_eligible
            folds.append(
                {
                    "fold": fold,
                    "seed_count": len(indexes),
                    "baseline_false_merge_rate": baseline_false_merge,
                    "candidate_false_merge_rate": candidate_false_merge,
                    "false_merge_difference": candidate_false_merge - baseline_false_merge,
                    "baseline_pairwise_recall": baseline_recall,
                    "candidate_pairwise_recall": candidate_recall,
                    "recall_difference": candidate_recall - baseline_recall,
                    "eligible": fold_eligible,
                }
            )
        aggregate = {metric: _mean([float(row[metric]) for row in rows]) for metric in metrics}
        if every_fold_eligible:
            eligible.append(algorithm_id)
        if aggregate["pairwise_recall"] >= 0.80:
            recall_floor_candidates.append(algorithm_id)
        candidate_reports[algorithm_id] = {
            "spatial_multiplier": EVIDENCE_GRAPH_CANDIDATES[algorithm_id],
            "every_fold_eligible": every_fold_eligible,
            "folds": folds,
            "aggregate": aggregate,
            "per_seed": rows,
        }

    selection_guardrail_failure = False
    if eligible:
        selected = min(
            eligible,
            key=lambda algorithm_id: (
                float(candidate_reports[algorithm_id]["aggregate"]["false_merge_rate"]),  # type: ignore[index]
                -float(candidate_reports[algorithm_id]["aggregate"]["pairwise_f1"]),  # type: ignore[index]
                EVIDENCE_GRAPH_CANDIDATES[algorithm_id],
            ),
        )
        selection_rule = "every-fold-eligible-then-false-merge-f1-smallest-q"
    elif recall_floor_candidates:
        selection_guardrail_failure = True
        selected = min(
            recall_floor_candidates,
            key=lambda algorithm_id: (
                float(candidate_reports[algorithm_id]["aggregate"]["false_merge_rate"]),  # type: ignore[index]
                EVIDENCE_GRAPH_CANDIDATES[algorithm_id],
            ),
        )
        selection_rule = "fallback-lowest-false-merge-with-aggregate-recall-at-least-0.80"
    else:
        selection_guardrail_failure = True
        selected = "baseline-v7-heuristic"
        selection_rule = "remediation-failed-retain-baseline"

    report = {
        "schema_version": "delta-reconciliation-development-selection-v1",
        "protocol_role": "development-only-selection-before-confirmatory-v7-derivation",
        "inputs": {
            "scenario_configuration_sha256": sha256_file(arguments.config),
            "geography_catalog_sha256": sha256_file(arguments.geography),
            "acceptance_development_definition_sha256": sha256_file(arguments.acceptance),
            "selection_script_sha256": sha256_file(Path(__file__)),
            "reconciliation_implementation_sha256": sha256_file(
                Path(__file__).resolve().parents[1]
                / "src/trace_jepa/scenario/delta/reconciliation_v8.py"
            ),
        },
        "development_seed_count": len(seeds),
        "fold_rule": "seed-index-modulo-five",
        "candidate_ids_frozen_before_evaluation": list(EVIDENCE_GRAPH_CANDIDATES),
        "eligibility_rule": (
            "every fold lowers false-merge rate versus baseline and recall loss is at most 0.05"
        ),
        "baseline_aggregate": {
            metric: _mean([float(row[metric]) for row in baseline_rows]) for metric in metrics
        },
        "candidates": candidate_reports,
        "selected_algorithm_id": selected,
        "selection_rule_applied": selection_rule,
        "selection_guardrail_failure": selection_guardrail_failure,
        "holdout_primary_endpoint": "paired-seed-false-merge-rate-difference",
        "holdout_recall_noninferiority_margin": -0.05,
        "claim_rule": (
            "false-merge upper 95% bound below zero and recall-difference lower 95% bound above -0.05"
        ),
        "claim_limits": [
            "development-selection-not-confirmatory-evidence",
            "controller-visible-evidence-only",
            "no-learned-reconciliation-model",
        ],
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_bytes(canonical_json_bytes(report))


if __name__ == "__main__":
    main()
