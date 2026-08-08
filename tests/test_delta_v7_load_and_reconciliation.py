from __future__ import annotations

import json
from pathlib import Path

import pytest

from trace_jepa.predictor import ToyActionPrefixPredictor
from trace_jepa.scenario.delta.evaluation import evaluate_partitions
from trace_jepa.scenario.delta.generator import generate_delta_small
from trace_jepa.scenario.delta.loading import load_scenario_config
from trace_jepa.scenario.delta.models import CallRecord
from trace_jepa.scenario.delta.reconciliation_selection import (
    CANONICAL_RECONCILIATION_ALGORITHM,
)
from trace_jepa.scenario.delta.reconciliation_v8 import EvidenceGraphReconciler
from trace_jepa.scenario.delta.runner import evaluate_capacity_windows, run_delta_small
from trace_jepa.scenario.delta.runtime import CapacityEvaluator

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/scenarios/wf_dfld_01_small.yaml"
GEOGRAPHY = ROOT / "data/scenario/delta/geography/delta_small_geography_v3.yaml"
POLICY = ROOT / "configs/policies/trace_delta_small_v1.yaml"


def _scenario():
    return generate_delta_small(CONFIG, GEOGRAPHY)


def _two_single_unit_incidents():
    scenario = _scenario()
    template = scenario.truth.incidents[0]
    incidents = [
        template.model_copy(
            update={
                "incident_id": f"fixture-{index}",
                "required_capability": "welfare_check",
                "service_units": 1,
                "onset_s": 0,
                "service_duration_s": 900,
            }
        )
        for index in range(2)
    ]
    return scenario, incidents


def test_strict_matching_enforces_one_resource_per_incident() -> None:
    scenario, incidents = _two_single_unit_incidents()
    evaluator = CapacityEvaluator(scenario)
    assert evaluator.strict_matched_units(incidents, 300, ()) == 1
    assert evaluator.uncapped_units(incidents, 300, ()) == 2
    assert evaluator.historical_capped_units(incidents, 300, ()) == 2


def test_multiunit_incident_requires_a_sufficient_physical_resource() -> None:
    scenario, incidents = _two_single_unit_incidents()
    incident = incidents[0].model_copy(update={"service_units": 2})
    units = [
        unit.model_copy(update={"service_units": 1})
        if unit.resource_id == "RES-ENGINE-01"
        else unit
        for unit in scenario.resources.units
    ]
    amended = scenario.model_copy(
        update={"resources": scenario.resources.model_copy(update={"units": units})}
    )
    evaluator = CapacityEvaluator(amended)
    assert evaluator.strict_matched_units([incident], 300, ()) == 0
    assert evaluator.uncapped_units([incident], 300, ()) == 1
    assert evaluator.historical_capped_units([incident], 300, ()) == 1


def test_zero_demand_and_zero_capacity_have_explicit_semantics() -> None:
    scenario, incidents = _two_single_unit_incidents()
    assert CapacityEvaluator(scenario).strict_matched_units([], 300, ()) == 0
    unavailable = scenario.model_copy(
        update={
            "resources": scenario.resources.model_copy(
                update={
                    "units": [
                        unit.model_copy(update={"is_available": False})
                        for unit in scenario.resources.units
                    ]
                }
            )
        }
    )
    windows = evaluate_capacity_windows(
        unavailable.model_copy(
            update={"truth": unavailable.truth.model_copy(update={"incidents": incidents[:1]})}
        ),
        [],
    )
    assert windows[0].strict_concurrent_load_ratio_milli is None
    assert windows[0].strict_unserviceable is True
    empty_windows = evaluate_capacity_windows(
        scenario.model_copy(update={"truth": scenario.truth.model_copy(update={"incidents": []})}),
        [],
    )
    assert all(item.strict_concurrent_load_ratio_milli == 0 for item in empty_windows)
    assert all(item.residual_strict_pressure_ratio_milli == 0 for item in empty_windows)


def test_v5_configuration_has_no_active_historical_ratio_target() -> None:
    config = load_scenario_config(CONFIG)
    assert config.schema_version == "trace-delta-scenario-v5"
    assert config.demand_capacity.schema_version == "delta-demand-capacity-v5"
    assert config.demand_capacity.target_ratio is None
    assert config.demand_capacity.tolerance is None
    raw = CONFIG.read_text("utf-8")
    assert "target_ratio:" not in raw
    assert "tolerance:" not in raw


def test_v5_result_serializes_only_finite_qualified_peak_names() -> None:
    result = run_delta_small(_scenario(), ToyActionPrefixPredictor(), POLICY)
    payload = result.model_dump(mode="json")
    expected = {
        "peak_finite_strict_concurrent_load_ratio_milli",
        "peak_finite_uncapped_compatible_load_ratio_milli",
        "peak_finite_registered_normalized_coverable_load_index_milli",
        "peak_finite_residual_strict_pressure_ratio_milli",
    }
    assert expected <= payload.keys()
    assert "peak_strict_concurrent_load_ratio_milli" not in payload
    assert "peak_uncapped_compatible_load_ratio_milli" not in payload
    assert "peak_registered_normalized_coverable_load_index_milli" not in payload
    assert result.peak_strict_concurrent_load_ratio_milli == (
        result.peak_finite_strict_concurrent_load_ratio_milli
    )


def test_complete_partition_metrics_penalize_false_merges() -> None:
    result = evaluate_partitions(
        {"a": "truth-1", "b": "truth-1", "c": "truth-2", "d": "false-d"},
        {"a": "belief-1", "b": "belief-1", "c": "belief-2", "d": "belief-2"},
        {"d"},
        revision_links=(("b", "a", True), ("c", "a", False)),
        occupant_revision_results=(True, False),
    )
    assert result.true_positive_pairs == 1
    assert result.false_positive_pairs == 1
    assert result.false_negative_pairs == 0
    assert result.pairwise_precision == 0.5
    assert result.pairwise_recall == 1.0
    assert result.pairwise_f1 == pytest.approx(2 / 3)
    assert result.false_merge_rate == 0.5
    assert result.missed_link_rate == 0.0
    assert result.false_report_merge_rate == 1.0
    assert result.revision_link_precision == 1.0
    assert result.revision_link_recall == 1.0
    assert result.reported_occupant_revision_truth_accuracy == 0.5
    assert result.controller_occupant_belief_accuracy is None
    assert result.adjusted_rand_index < 1.0


def test_runtime_emits_complete_reconciliation_evaluation() -> None:
    scenario = _scenario()
    result = run_delta_small(scenario, ToyActionPrefixPredictor(), POLICY)
    evaluation = result.reconciliation_evaluation
    assert evaluation.call_count == len(scenario.observations.calls)
    assert evaluation.reference_cluster_count > 0
    assert evaluation.controller_cluster_count > 0
    assert 0.0 <= evaluation.pairwise_f1 <= 1.0
    assert -1.0 <= evaluation.adjusted_rand_index <= 1.0
    assert result.reconciliation_artifact is not None
    assert result.reconciliation_artifact.hidden_lineage_used is False


def test_v8_selection_report_matches_the_frozen_canonical_algorithm() -> None:
    report = json.loads(
        (ROOT / "data/scenario/delta/calibration/v8_reconciliation_selection_v1.json").read_text(
            "utf-8"
        )
    )
    assert report["selected_algorithm_id"] == CANONICAL_RECONCILIATION_ALGORITHM
    assert report["selection_guardrail_failure"] is False
    assert report["candidates"][CANONICAL_RECONCILIATION_ALGORITHM]["every_fold_eligible"]
    assert all(
        fold["eligible"]
        for fold in report["candidates"][CANONICAL_RECONCILIATION_ALGORITHM]["folds"]
    )


def test_evidence_graph_hard_revision_and_available_callback_confirm() -> None:
    scenario = _scenario()
    calls = scenario.observations.calls
    first = calls[0].model_copy(
        update={
            "call_id": "hard-first",
            "callback_token": "SYNTH-CB-SHARED",
            "quality": calls[0].quality.model_copy(
                update={"callback_failed": False, "revision_of_call_id": None}
            ),
        }
    )
    callback = calls[1].model_copy(
        update={
            "call_id": "hard-callback",
            "callback_token": "SYNTH-CB-SHARED",
            "quality": calls[1].quality.model_copy(
                update={"callback_failed": False, "revision_of_call_id": None}
            ),
        }
    )
    revision = calls[2].model_copy(
        update={
            "call_id": "hard-revision",
            "callback_token": "SYNTH-CB-UNAVAILABLE-hard-revision",
            "quality": calls[2].quality.model_copy(
                update={"callback_failed": True, "revision_of_call_id": "hard-first"}
            ),
        }
    )
    reconciler = EvidenceGraphReconciler("evidence-graph-q100")
    first_step = reconciler.process(first, first.received_s)
    callback_step = reconciler.process(callback, max(callback.received_s, first.received_s))
    revision_step = reconciler.process(
        revision, max(revision.received_s, callback.received_s, first.received_s)
    )
    assert first_step.confirmed_link is None
    assert callback_step.confirmed_link is not None
    assert callback_step.confirmed_link.evidence_families == (
        "exact_shared_available_callback_token",
    )
    assert revision_step.confirmed_link is not None
    assert revision_step.confirmed_link.evidence_families == ("explicit_report_revision",)
    assert len(set(reconciler.artifact().cluster_by_call.values())) == 1


def test_evidence_graph_ambiguous_soft_relationship_stays_suspected_and_separate() -> None:
    template = _scenario().observations.calls[0]

    def fixture(call_id: str, received_s: int) -> CallRecord:
        return template.model_copy(
            update={
                "call_id": call_id,
                "received_s": received_s,
                "received_ts": template.received_ts,
                "callback_token": f"SYNTH-CB-{call_id}",
                "quality": template.quality.model_copy(
                    update={"callback_failed": False, "revision_of_call_id": None}
                ),
            }
        )

    first = fixture("ambiguous-a", 0)
    second = fixture("ambiguous-b", 3_000)
    current = fixture("ambiguous-current", 1_500)
    reconciler = EvidenceGraphReconciler("evidence-graph-q100")
    reconciler.process(first, 0)
    reconciler.process(second, 3_000)
    step = reconciler.process(current, 4_000)
    assert step.confirmed_link is None
    assert len(step.emitted_links) == 2
    assert all(item.status == "suspected" for item in step.emitted_links)
    artifact = reconciler.artifact()
    assert len(set(artifact.cluster_by_call.values())) == 3


def test_evidence_graph_visible_contradiction_rejects_soft_link() -> None:
    template = _scenario().observations.calls[0]
    first = template.model_copy(
        update={
            "call_id": "contradiction-first",
            "callback_token": "SYNTH-CB-first",
            "reported": template.reported.model_copy(update={"occupants": 0}),
            "quality": template.quality.model_copy(
                update={"callback_failed": False, "revision_of_call_id": None}
            ),
        }
    )
    current = template.model_copy(
        update={
            "call_id": "contradiction-current",
            "received_s": first.received_s + 60,
            "callback_token": "SYNTH-CB-current",
            "reported": template.reported.model_copy(update={"occupants": 4}),
            "quality": template.quality.model_copy(
                update={"callback_failed": False, "revision_of_call_id": None}
            ),
        }
    )
    reconciler = EvidenceGraphReconciler("evidence-graph-q100")
    reconciler.process(first, first.received_s)
    step = reconciler.process(current, current.received_s)
    assert step.confirmed_link is None
    assert len(step.emitted_links) == 1
    assert step.emitted_links[0].status == "rejected"
