"""Canonical event and checkpoint contracts for the Reference state machine."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import Field

from trace_jepa.scenario.delta.domain.base import DeltaModel


class ReferenceEventType(str, Enum):
    PUBLIC_ENVIRONMENT_SAMPLE = "public_environment_sample"
    HIDDEN_PHYSICAL_TRUTH = "hidden_physical_truth"
    BREACH_ACTIVATED = "breach_activated"
    CROSSING_STATE_CHANGED = "crossing_state_changed"
    CALL_DELIVERED = "call_delivered"
    COORDINATION_MESSAGE_DELIVERED = "coordination_message_delivered"
    RESOURCE_STATE_CHANGED = "resource_state_changed"
    TRACE_DECISION_RECORDED = "trace_decision_recorded"
    COMMITMENT_CREATED = "commitment_created"
    OUTCOME_RECORDED = "outcome_recorded"
    COMPENSATION_RECORDED = "compensation_recorded"
    PROVIDER_RECEIPT_RECORDED = "provider_receipt_recorded"


class ReferenceEventVisibility(str, Enum):
    CONTROLLER_VISIBLE = "controller_visible"
    HIDDEN_EVALUATION_ONLY = "hidden_evaluation_only"


class ReferenceEvent(DeltaModel):
    """One immutable hash-chained event with canonical JSON payload bytes."""

    schema_version: Literal["delta-reference-event-v1"]
    sequence: int = Field(ge=1)
    event_id: str = Field(pattern=r"^reference-event-[0-9a-f]{20}$")
    at_s: int = Field(ge=-172_800, le=345_600)
    event_type: ReferenceEventType
    visibility: ReferenceEventVisibility
    payload_json: str = Field(min_length=2)
    previous_event_digest: str = Field(pattern=r"^(GENESIS|[0-9a-f]{64})$")
    event_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReferenceRuntimeCheckpoint(DeltaModel):
    """Replay checkpoint bound to an exact event prefix and reducer state."""

    schema_version: Literal["delta-reference-runtime-checkpoint-v1"]
    sequence: int = Field(ge=0)
    at_s: int = Field(ge=-172_800, le=345_600)
    event_prefix_digest: str = Field(pattern=r"^(GENESIS|[0-9a-f]{64})$")
    state_json: str = Field(min_length=2)
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    checkpoint_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
