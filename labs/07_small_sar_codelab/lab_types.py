"""The small set of inputs and outputs used by the student controller.

The workshop runtime creates these objects for students.  Each object is
immutable: a function returns a new decision instead of secretly changing an
earlier one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TraceDecision(str, Enum):
    """What TRACE says another component may do with a proposed action."""

    CLEAR = "clear"
    QUALIFY = "qualify"
    HOLD = "hold"
    BLOCK = "block"
    ESCALATE = "escalate"


class RescueEventType(str, Enum):
    """The three kinds of event the workshop controller can record."""

    ALLOCATION = "allocation"
    REFUSAL = "refusal"
    REPAIR = "repair"


class ReasonCode(str, Enum):
    """Short, consistent labels explaining why a decision happened."""

    ALLOCATED_COMPATIBLE_CAPACITY = "allocated_compatible_capacity"
    TRACE_NOT_CLEAR = "trace_not_clear"
    NO_COMPATIBLE_CAPACITY = "no_compatible_capacity"
    VISIBLE_EVIDENCE_REPAIR = "visible_evidence_repair"


@dataclass(frozen=True, slots=True)
class RescueRequest:
    """One requested rescue task, including its route and needed capability."""

    call_id: str
    belief_cluster_id: str
    call_type: str
    action_type: str
    required_capability: str
    route_id: str
    simulation_time_s: int


@dataclass(frozen=True, slots=True)
class ResourceView:
    """What the controller currently knows about one response unit."""

    resource_id: str
    capabilities: tuple[str, ...]
    currently_available: bool
    route_reachable: bool
    route_id: str
    routed_travel_s: int


@dataclass(frozen=True, slots=True)
class TraceAuthorization:
    """TRACE's decision plus the record and version that support it."""

    call_id: str
    belief_cluster_id: str
    record_id: str
    record_version: int
    decision: TraceDecision
    visible_evidence_basis: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RescueDecision:
    """One allocation, refusal, or repair returned by the student controller."""

    call_id: str
    belief_cluster_id: str
    event_type: RescueEventType
    reason_code: ReasonCode
    trace_record_id: str
    trace_record_version: int
    trace_decision: TraceDecision
    selected_resource_id: str | None = None
