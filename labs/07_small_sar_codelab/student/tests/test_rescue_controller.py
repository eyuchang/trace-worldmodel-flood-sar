"""Readable behavioral checks for the three student TODO functions."""

from __future__ import annotations

from dataclasses import replace
from types import ModuleType

import pytest
from _support import runtime
from _support.types import ReasonCode, RescueDecision, RescueEventType, TraceDecision
from exercise import rescue_controller


@pytest.fixture(scope="session")
def controller() -> ModuleType:
    """Use the one controller file students edit."""

    return rescue_controller


@pytest.fixture(scope="session")
def public_cases() -> dict[str, runtime.PublicCase]:
    """Load the four provided, public-only workshop cases."""

    return runtime.build_cases()


def test_eligible_resources_filters_and_sorts(
    controller: ModuleType,
    public_cases: dict[str, runtime.PublicCase],
) -> None:
    case = public_cases["allocation"]
    slower = replace(
        case.resources[0],
        resource_id="RES-SLOWER",
        routed_travel_s=case.resources[0].routed_travel_s + 100,
    )
    wrong_route = replace(case.resources[0], resource_id="RES-WRONG-ROUTE", route_id="XNG-03")
    unreachable = replace(case.resources[0], resource_id="RES-UNREACHABLE", route_reachable=False)
    unavailable = replace(case.resources[0], resource_id="RES-BUSY", currently_available=False)

    selected = controller.eligible_resources(
        case.request,
        (slower, wrong_route, unreachable, unavailable, case.resources[0]),
    )

    assert [item.resource_id for item in selected] == ["RES-ENGINE-01", "RES-SLOWER"]


def test_clear_plus_capacity_allocates(
    controller: ModuleType,
    public_cases: dict[str, runtime.PublicCase],
) -> None:
    case = public_cases["allocation"]

    decision = controller.decide_rescue(case.request, case.authorization, case.resources)

    assert decision.event_type is RescueEventType.ALLOCATION
    assert decision.reason_code is ReasonCode.ALLOCATED_COMPATIBLE_CAPACITY
    assert decision.selected_resource_id == "RES-ENGINE-01"
    assert decision.call_id == case.authorization.call_id
    assert decision.trace_record_id == case.authorization.record_id


def test_hold_refuses_even_when_capacity_exists(
    controller: ModuleType,
    public_cases: dict[str, runtime.PublicCase],
) -> None:
    case = public_cases["evidence_hold"]
    assert any(resource.currently_available for resource in case.resources)

    decision = controller.decide_rescue(case.request, case.authorization, case.resources)

    assert decision.trace_decision is TraceDecision.HOLD
    assert decision.event_type is RescueEventType.REFUSAL
    assert decision.reason_code is ReasonCode.TRACE_NOT_CLEAR
    assert decision.selected_resource_id is None


def test_clear_without_capacity_refuses(
    controller: ModuleType,
    public_cases: dict[str, runtime.PublicCase],
) -> None:
    case = public_cases["capacity_refusal"]
    assert case.authorization.decision is TraceDecision.CLEAR
    assert not any(resource.currently_available for resource in case.resources)

    decision = controller.decide_rescue(case.request, case.authorization, case.resources)

    assert decision.event_type is RescueEventType.REFUSAL
    assert decision.reason_code is ReasonCode.NO_COMPATIBLE_CAPACITY
    assert decision.selected_resource_id is None


def test_decision_rejects_mismatched_call(
    controller: ModuleType,
    public_cases: dict[str, runtime.PublicCase],
) -> None:
    case = public_cases["allocation"]
    mismatched = replace(case.authorization, call_id="C8-not-the-request")

    with pytest.raises(ValueError):
        controller.decide_rescue(case.request, mismatched, case.resources)


def test_decision_rejects_mismatched_situation(
    controller: ModuleType,
    public_cases: dict[str, runtime.PublicCase],
) -> None:
    case = public_cases["allocation"]
    mismatched = replace(case.authorization, belief_cluster_id="BC-not-the-request")

    with pytest.raises(ValueError):
        controller.decide_rescue(case.request, mismatched, case.resources)


def _initial_allocation(
    controller: ModuleType,
    public_cases: dict[str, runtime.PublicCase],
) -> RescueDecision:
    """Create the earlier allocation needed by the repair tests."""

    allocation = public_cases["allocation"]
    return controller.decide_rescue(
        allocation.request,
        allocation.authorization,
        allocation.resources,
    )


def test_visible_repair_appends_and_preserves_allocation(
    controller: ModuleType,
    public_cases: dict[str, runtime.PublicCase],
) -> None:
    repair = public_cases["visible_repair"]
    initial = _initial_allocation(controller, public_cases)

    history = controller.apply_visible_repair((initial,), repair.authorization)

    assert history[0] is initial
    assert len(history) == 2
    assert history[1].event_type is RescueEventType.REPAIR
    assert history[1].reason_code is ReasonCode.VISIBLE_EVIDENCE_REPAIR
    assert history[1].selected_resource_id is None
    assert history[1].trace_record_version > history[0].trace_record_version


def test_repair_requires_visible_basis(
    controller: ModuleType,
    public_cases: dict[str, runtime.PublicCase],
) -> None:
    repair = public_cases["visible_repair"]
    initial = _initial_allocation(controller, public_cases)
    unsupported = replace(repair.authorization, visible_evidence_basis=())

    with pytest.raises(ValueError):
        controller.apply_visible_repair((initial,), unsupported)


def test_repair_rejects_empty_history(
    controller: ModuleType,
    public_cases: dict[str, runtime.PublicCase],
) -> None:
    repair = public_cases["visible_repair"]

    with pytest.raises(ValueError):
        controller.apply_visible_repair((), repair.authorization)


def test_repair_rejects_a_different_situation(
    controller: ModuleType,
    public_cases: dict[str, runtime.PublicCase],
) -> None:
    initial = _initial_allocation(controller, public_cases)
    repair = public_cases["visible_repair"]
    wrong_situation = replace(repair.authorization, belief_cluster_id="BC-different")

    with pytest.raises(ValueError):
        controller.apply_visible_repair((initial,), wrong_situation)


def test_repair_rejects_a_different_trace_record(
    controller: ModuleType,
    public_cases: dict[str, runtime.PublicCase],
) -> None:
    initial = _initial_allocation(controller, public_cases)
    repair = public_cases["visible_repair"]
    wrong_record = replace(repair.authorization, record_id="TR-different")

    with pytest.raises(ValueError):
        controller.apply_visible_repair((initial,), wrong_record)


def test_repair_requires_a_later_version(
    controller: ModuleType,
    public_cases: dict[str, runtime.PublicCase],
) -> None:
    initial = _initial_allocation(controller, public_cases)
    repair = public_cases["visible_repair"]
    old_version = replace(repair.authorization, record_version=initial.trace_record_version)

    with pytest.raises(ValueError):
        controller.apply_visible_repair((initial,), old_version)
