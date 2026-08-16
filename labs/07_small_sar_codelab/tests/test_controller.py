"""Readable behavioral checks for the three student TODO functions."""

from __future__ import annotations

from dataclasses import replace
from types import ModuleType

import lab_runtime
import pytest
from lab_types import ReasonCode, RescueEventType, TraceDecision


def test_eligible_resources_filters_and_sorts(
    controller: ModuleType,
    public_cases: dict[str, lab_runtime.PublicCase],
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
    public_cases: dict[str, lab_runtime.PublicCase],
) -> None:
    case = public_cases["allocation"]

    decision = controller.decide_rescue(case.request, case.authorization, case.resources)

    assert decision.event_type is RescueEventType.ALLOCATION
    assert decision.reason_code is ReasonCode.ALLOCATED_COMPATIBLE_CAPACITY
    assert decision.selected_resource_id == "RES-ENGINE-01"


def test_hold_refuses_even_when_capacity_exists(
    controller: ModuleType,
    public_cases: dict[str, lab_runtime.PublicCase],
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
    public_cases: dict[str, lab_runtime.PublicCase],
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
    public_cases: dict[str, lab_runtime.PublicCase],
) -> None:
    case = public_cases["allocation"]
    mismatched = replace(case.authorization, call_id="C8-not-the-request")

    with pytest.raises(ValueError, match="same call"):
        controller.decide_rescue(case.request, mismatched, case.resources)


def test_visible_repair_appends_and_preserves_allocation(
    controller: ModuleType,
    public_cases: dict[str, lab_runtime.PublicCase],
) -> None:
    allocation = public_cases["allocation"]
    repair = public_cases["visible_repair"]
    initial = controller.decide_rescue(
        allocation.request,
        allocation.authorization,
        allocation.resources,
    )

    history = controller.apply_visible_repair((initial,), repair.authorization)

    assert history[0] is initial
    assert len(history) == 2
    assert history[1].event_type is RescueEventType.REPAIR
    assert history[1].reason_code is ReasonCode.VISIBLE_EVIDENCE_REPAIR
    assert history[1].selected_resource_id is None
    assert history[1].trace_record_version > history[0].trace_record_version


def test_repair_requires_visible_basis(
    controller: ModuleType,
    public_cases: dict[str, lab_runtime.PublicCase],
) -> None:
    allocation = public_cases["allocation"]
    repair = public_cases["visible_repair"]
    initial = controller.decide_rescue(
        allocation.request,
        allocation.authorization,
        allocation.resources,
    )
    unsupported = replace(repair.authorization, visible_evidence_basis=())

    with pytest.raises(ValueError, match="visible evidence"):
        controller.apply_visible_repair((initial,), unsupported)
