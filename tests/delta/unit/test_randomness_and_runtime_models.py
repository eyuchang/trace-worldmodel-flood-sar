"""Boundary tests for random primitives and capacity/outcome invariants."""

from __future__ import annotations

import random

import pytest
from pydantic import ValidationError

from trace_jepa.scenario.delta.generation.randomness import KeyedRandom, sample_poisson
from trace_jepa.scenario.delta.runtime.models import DeltaResourceOutcome, DemandWindow


def _demand_window(**updates: object) -> DemandWindow:
    values: dict[str, object] = {
        "window_start_s": 0,
        "active_demand_units": 2,
        "strict_matched_capacity_units": 2,
        "strict_concurrent_load_ratio_milli": 1000,
        "strict_unserviceable": False,
        "uncapped_compatible_service_unit_capacity_units": 2,
        "uncapped_compatible_load_ratio_milli": 1000,
        "historical_capped_coverable_capacity_units": 2,
        "registered_normalized_coverable_load_index_milli": 1000,
        "commitment_covered_demand_units": 0,
        "residual_demand_units": 2,
        "free_strict_compatible_capacity_units": 2,
        "residual_strict_pressure_ratio_milli": 1000,
        "residual_strict_unserviceable": False,
    }
    values.update(updates)
    return DemandWindow.model_validate(values)


def test_random_primitives_reject_invalid_domains_and_cover_boundaries() -> None:
    rng = random.Random(7)
    with pytest.raises(ValueError, match="non-negative"):
        sample_poisson(rng, -0.1)
    assert sample_poisson(rng, 0.0) == 0
    assert sample_poisson(random.Random(7), 2.0) >= 0

    keyed = KeyedRandom(7, "parameters", "stage")
    with pytest.raises(ValueError, match="upper bound"):
        keyed.randint(2, 1, "invalid")
    with pytest.raises(ValueError, match="positive"):
        keyed.choice_index(0, "invalid")
    with pytest.raises(ValueError, match="between zero and one"):
        keyed.bernoulli(1.1, "invalid")
    with pytest.raises(ValueError, match="non-negative"):
        keyed.poisson(-0.1, "invalid")
    assert keyed.poisson(0.0, "zero") == 0
    assert keyed.poisson(2.0, "positive") >= 0


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"residual_demand_units": 1}, "covered plus residual"),
        (
            {
                "strict_matched_capacity_units": 0,
                "strict_unserviceable": False,
            },
            "strict unserviceable",
        ),
        (
            {
                "free_strict_compatible_capacity_units": 0,
                "residual_strict_unserviceable": False,
            },
            "residual unserviceable",
        ),
        (
            {
                "active_demand_units": 0,
                "commitment_covered_demand_units": 0,
                "residual_demand_units": 0,
                "strict_concurrent_load_ratio_milli": 1,
            },
            "must be zero",
        ),
    ],
)
def test_demand_window_rejects_inconsistent_accounting(
    updates: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        _demand_window(**updates)


def test_demand_window_legacy_properties_are_read_only_views() -> None:
    window = _demand_window()
    assert window.active_demand_service_units == 2
    assert window.gross_compatible_capacity_units == 2
    assert window.gross_load_ratio_milli == 1000
    assert window.gross_unserviceable is False
    assert window.residual_unassigned_demand_units == 2
    assert window.free_compatible_capacity_units == 2
    assert window.residual_pressure_ratio_milli == 1000
    assert window.residual_unserviceable is False


def _outcome(**updates: object) -> DeltaResourceOutcome:
    values: dict[str, object] = {
        "outcome_id": "outcome-1",
        "call_id": "call-1",
        "resource_id": "resource-1",
        "status": "completed_within_window",
        "scheduled_completion_s": 100,
        "observed_completion_s": 100,
        "censoring_s": 200,
        "authorizing_commitment_id": "commitment-1",
        "authorizing_trace_record_id": "trace-1",
        "authorizing_trace_record_version": 1,
    }
    values.update(updates)
    return DeltaResourceOutcome.model_validate(values)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"observed_completion_s": 99}, "scheduled time"),
        ({"scheduled_completion_s": 201, "observed_completion_s": 201}, "follow censoring"),
        (
            {
                "status": "active_at_scenario_censoring",
                "scheduled_completion_s": 201,
                "observed_completion_s": 201,
            },
            "no observed completion",
        ),
        (
            {
                "status": "active_at_scenario_censoring",
                "scheduled_completion_s": 200,
                "observed_completion_s": None,
            },
            "after censoring",
        ),
        ({"status": "unknown"}, "Input should be"),
    ],
)
def test_outcome_model_rejects_false_completion_or_censoring_claims(
    updates: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        _outcome(**updates)
