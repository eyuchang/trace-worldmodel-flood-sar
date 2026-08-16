"""Student exercise: finish the three controller functions marked TODO."""

from __future__ import annotations

from lab_types import (
    RescueDecision,
    RescueRequest,
    ResourceView,
    TraceAuthorization,
)


def eligible_resources(
    request: RescueRequest,
    resources: tuple[ResourceView, ...],
) -> tuple[ResourceView, ...]:
    """Return compatible resources in deterministic dispatch order.

    TODO 1: Keep only resources that are currently available, route-reachable,
    on the requested route, and able to provide the required capability. Sort
    by travel time and then resource ID so replay never depends on input order.
    """

    raise NotImplementedError("TODO 1: implement eligible_resources")


def decide_rescue(
    request: RescueRequest,
    authorization: TraceAuthorization,
    resources: tuple[ResourceView, ...],
) -> RescueDecision:
    """Convert TRACE authorization plus capacity into one rescue decision.

    TODO 2: Refuse first when TRACE is not CLEAR. If TRACE is CLEAR, allocate
    the first eligible resource, or refuse for lack of compatible capacity.
    Never treat CLEAR alone as an allocation.
    """

    raise NotImplementedError("TODO 2: implement decide_rescue")


def apply_visible_repair(
    history: tuple[RescueDecision, ...],
    repair_authorization: TraceAuthorization,
) -> tuple[RescueDecision, ...]:
    """Append a visible-evidence repair without erasing prior history.

    TODO 3: Validate that the repair belongs to the same belief cluster, uses a
    later version of the same TRACE record, and names visible evidence. Append
    one REPAIR event; do not replace the allocation or create a new commitment.
    """

    raise NotImplementedError("TODO 3: implement apply_visible_repair")
