"""Reference solution for the bounded TRACE Small SAR controller."""

from __future__ import annotations

from _support.types import (
    ReasonCode,
    RescueDecision,
    RescueEventType,
    RescueRequest,
    ResourceView,
    TraceAuthorization,
    TraceDecision,
)


def _decision_from_trace(
    authorization: TraceAuthorization,
    event_type: RescueEventType,
    reason_code: ReasonCode,
    selected_resource_id: str | None = None,
) -> RescueDecision:
    """Build a decision while copying the shared TRACE record fields."""

    return RescueDecision(
        call_id=authorization.call_id,
        belief_cluster_id=authorization.belief_cluster_id,
        event_type=event_type,
        reason_code=reason_code,
        trace_record_id=authorization.record_id,
        trace_record_version=authorization.record_version,
        trace_decision=authorization.decision,
        selected_resource_id=selected_resource_id,
    )


def eligible_resources(
    request: RescueRequest,
    resources: tuple[ResourceView, ...],
) -> tuple[ResourceView, ...]:
    """Return compatible resources in deterministic dispatch order."""

    eligible = (
        resource
        for resource in resources
        if resource.currently_available
        and resource.route_reachable
        and resource.route_id == request.route_id
        and request.required_capability in resource.capabilities
    )
    return tuple(sorted(eligible, key=lambda item: (item.routed_travel_s, item.resource_id)))


def decide_rescue(
    request: RescueRequest,
    authorization: TraceAuthorization,
    resources: tuple[ResourceView, ...],
) -> RescueDecision:
    """Convert TRACE authorization plus visible capacity into a decision."""

    if authorization.call_id != request.call_id:
        raise ValueError("TRACE authorization and rescue request must name the same call")
    if authorization.belief_cluster_id != request.belief_cluster_id:
        raise ValueError("TRACE authorization and rescue request must share a belief cluster")

    if authorization.decision is not TraceDecision.CLEAR:
        return _decision_from_trace(
            authorization,
            RescueEventType.REFUSAL,
            ReasonCode.TRACE_NOT_CLEAR,
        )

    compatible = eligible_resources(request, resources)
    if not compatible:
        return _decision_from_trace(
            authorization,
            RescueEventType.REFUSAL,
            ReasonCode.NO_COMPATIBLE_CAPACITY,
        )

    return _decision_from_trace(
        authorization,
        RescueEventType.ALLOCATION,
        ReasonCode.ALLOCATED_COMPATIBLE_CAPACITY,
        compatible[0].resource_id,
    )


def apply_visible_repair(
    history: tuple[RescueDecision, ...],
    repair_authorization: TraceAuthorization,
) -> tuple[RescueDecision, ...]:
    """Append one controller-visible repair while preserving prior events."""

    if not history:
        raise ValueError("a repair requires an existing decision history")

    prior = history[-1]
    if repair_authorization.belief_cluster_id != prior.belief_cluster_id:
        raise ValueError("repair must stay within the existing belief cluster")
    if repair_authorization.record_id != prior.trace_record_id:
        raise ValueError("repair must continue the same TRACE record chain")
    if repair_authorization.record_version <= prior.trace_record_version:
        raise ValueError("repair must use a later TRACE record version")
    if not repair_authorization.visible_evidence_basis:
        raise ValueError("repair requires an explicit controller-visible evidence basis")

    repair = _decision_from_trace(
        repair_authorization,
        RescueEventType.REPAIR,
        ReasonCode.VISIBLE_EVIDENCE_REPAIR,
    )
    return (*history, repair)
