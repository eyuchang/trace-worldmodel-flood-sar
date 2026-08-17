"""Student exercise: finish the three controller functions marked TODO."""

from __future__ import annotations

from lab_types import (
    ReasonCode,  # noqa: F401 - ready for students to use in TODO 2/3
    RescueDecision,
    RescueEventType,  # noqa: F401 - ready for students to use in TODO 2/3
    RescueRequest,
    ResourceView,
    TraceAuthorization,
    TraceDecision,  # noqa: F401 - ready for students to use in TODO 2
)


def eligible_resources(
    request: RescueRequest,
    resources: tuple[ResourceView, ...],
) -> tuple[ResourceView, ...]:
    """Return the response units that can actually serve this request.

    TODO 1: Imagine these resources on a dispatch board. Keep a unit only when
    it is available, can reach the route, is assigned to the requested route,
    and can perform the requested task. Sort by travel time and then resource
    ID so tied inputs always produce the same order.
    """

    raise NotImplementedError("TODO 1: choose which response units are eligible")


def decide_rescue(
    request: RescueRequest,
    authorization: TraceAuthorization,
    resources: tuple[ResourceView, ...],
) -> RescueDecision:
    """Decide whether to allocate one response unit or refuse with a reason.

    TODO 2: TRACE answers whether the information may be used; this function
    answers whether a unit can be sent. Refuse first when TRACE is not CLEAR.
    With CLEAR, allocate the first eligible resource or refuse when none exist.
    """

    raise NotImplementedError("TODO 2: choose allocation or refusal")


def apply_visible_repair(
    history: tuple[RescueDecision, ...],
    repair_authorization: TraceAuthorization,
) -> tuple[RescueDecision, ...]:
    """Add a later correction without erasing the earlier decision.

    TODO 3: Check that the update belongs to the same situation and TRACE
    record chain, uses a later version, and names evidence the controller could
    see. Append one REPAIR event; do not replace the earlier allocation or
    select the resource again.
    """

    raise NotImplementedError("TODO 3: append the later repair")
