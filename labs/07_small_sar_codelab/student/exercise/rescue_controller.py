"""Student exercise: finish the three controller functions marked TODO."""

from __future__ import annotations

from _support.types import (
    ReasonCode,
    RescueDecision,
    RescueEventType,
    RescueRequest,
    ResourceView,
    TraceAuthorization,
    TraceDecision,  # noqa: F401 - use this enum in TODO 2
)


def _decision_from_trace(
    authorization: TraceAuthorization,
    event_type: RescueEventType,
    reason_code: ReasonCode,
    selected_resource_id: str | None = None,
) -> RescueDecision:
    """Build a decision while copying the shared TRACE record fields.

    This helper is complete. Use it in TODO 2 and TODO 3 so that your code can
    focus on *which* decision to make instead of repeatedly copying fields.
    """

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
    """Return the response units that can actually serve this request.

    Imagine the resources on a dispatch board. Keep a unit only when it is
    available, can reach the route, is assigned to the requested route, and can
    perform the requested task. Sort by travel time and then resource ID.
    """

    # TODO 1
    # 1. Build a collection containing only resources that pass all four rules.
    # 2. Sort that collection by (routed_travel_s, resource_id).
    # 3. Return the sorted resources as a tuple.
    raise NotImplementedError("TODO 1: choose which response units are eligible")


def decide_rescue(
    request: RescueRequest,
    authorization: TraceAuthorization,
    resources: tuple[ResourceView, ...],
) -> RescueDecision:
    """Decide whether to allocate one response unit or refuse with a reason.

    TRACE answers whether the information may be used; this function answers
    whether a unit can be sent. CLEAR allows the resource check—it does not
    guarantee an allocation.
    """

    # TODO 2
    # 1. Use ValueError unless both call_id and belief_cluster_id match.
    # 2. If TRACE is not CLEAR, return an information refusal.
    # 3. Call eligible_resources exactly once.
    # 4. If that tuple is empty, return a capacity refusal.
    # 5. Otherwise allocate the first eligible resource.
    #
    # Use _decision_from_trace(...) for every returned decision.
    raise NotImplementedError("TODO 2: choose allocation or refusal")


def apply_visible_repair(
    history: tuple[RescueDecision, ...],
    repair_authorization: TraceAuthorization,
) -> tuple[RescueDecision, ...]:
    """Add a later correction without erasing the earlier decision.

    Check that the update belongs to the same situation and TRACE record chain,
    uses a later version, and names evidence the controller could see. Append
    one REPAIR event; do not replace the earlier allocation.
    """

    # TODO 3
    # 1. Require at least one earlier decision.
    # 2. Compare the update with history[-1].
    # 3. Require the same belief cluster and TRACE record ID.
    # 4. Require a larger record version and nonempty visible evidence.
    # 5. Create a REPAIR with _decision_from_trace(...), then return
    #    (*history, repair). Do not select a resource for the repair.
    raise NotImplementedError("TODO 3: append the later repair")
