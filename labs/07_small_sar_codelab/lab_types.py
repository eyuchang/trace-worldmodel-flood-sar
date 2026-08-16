"""Small, immutable types used by the student SAR controller.

These types describe a teaching-only controller view.  They intentionally do
not expose latent incident truth or the registered simulator's internal state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TraceDecision(str, Enum):
    """Consumer actions that may appear in a public Small TRACE record."""

    CLEAR = "clear"
    QUALIFY = "qualify"
    HOLD = "hold"
    BLOCK = "block"
    ESCALATE = "escalate"


class RescueEventType(str, Enum):
    """Controller events taught by this bounded lab."""

    ALLOCATION = "allocation"
    REFUSAL = "refusal"
    REPAIR = "repair"


class ReasonCode(str, Enum):
    """Stable, machine-readable reasons for a teaching decision."""

    ALLOCATED_COMPATIBLE_CAPACITY = "allocated_compatible_capacity"
    TRACE_NOT_CLEAR = "trace_not_clear"
    NO_COMPATIBLE_CAPACITY = "no_compatible_capacity"
    VISIBLE_EVIDENCE_REPAIR = "visible_evidence_repair"


@dataclass(frozen=True, slots=True)
class RescueRequest:
    """Controller-visible action request projected from a public Small plan."""

    call_id: str
    belief_cluster_id: str
    call_type: str
    action_type: str
    required_capability: str
    route_id: str
    simulation_time_s: int


@dataclass(frozen=True, slots=True)
class ResourceView:
    """Resource state visible to the controller at one decision time."""

    resource_id: str
    capabilities: tuple[str, ...]
    currently_available: bool
    route_reachable: bool
    route_id: str
    routed_travel_s: int


@dataclass(frozen=True, slots=True)
class TraceAuthorization:
    """Exact public TRACE record/version used by the teaching controller."""

    call_id: str
    belief_cluster_id: str
    record_id: str
    record_version: int
    decision: TraceDecision
    failed_gates: tuple[str, ...]
    supersedes_record_id: str | None
    supersedes_record_version: int | None
    visible_evidence_basis: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RescueDecision:
    """One append-only event emitted by the student controller."""

    call_id: str
    belief_cluster_id: str
    event_type: RescueEventType
    reason_code: ReasonCode
    trace_record_id: str
    trace_record_version: int
    trace_decision: TraceDecision
    selected_resource_id: str | None = None
