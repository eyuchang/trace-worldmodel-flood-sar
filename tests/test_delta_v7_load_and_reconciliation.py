from __future__ import annotations

from pathlib import Path

import pytest

from trace_jepa.predictor import ToyActionPrefixPredictor
from trace_jepa.scenario.delta.evaluation import evaluate_partitions
from trace_jepa.scenario.delta.generator import generate_delta_small
from trace_jepa.scenario.delta.runner import (
    _historical_capped_coverable_capacity_units,
    _strict_matched_capacity_units,
    _uncapped_compatible_service_unit_capacity,
    evaluate_capacity_windows,
    run_delta_small,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/scenarios/wf_dfld_01_small.yaml"
GEOGRAPHY = ROOT / "data/scenario/delta/geography/delta_small_geography_v2.yaml"
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
    assert _strict_matched_capacity_units(scenario, incidents, 300, ()) == 1
    assert _uncapped_compatible_service_unit_capacity(scenario, incidents, 300, ()) == 2
    assert _historical_capped_coverable_capacity_units(scenario, incidents, 300, ()) == 2


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
    assert _strict_matched_capacity_units(amended, [incident], 300, ()) == 0
    assert _uncapped_compatible_service_unit_capacity(amended, [incident], 300, ()) == 1
    assert _historical_capped_coverable_capacity_units(amended, [incident], 300, ()) == 1


def test_zero_demand_and_zero_capacity_have_explicit_semantics() -> None:
    scenario, incidents = _two_single_unit_incidents()
    assert _strict_matched_capacity_units(scenario, [], 300, ()) == 0
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
    assert result.occupant_revision_correctness == 0.5
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
