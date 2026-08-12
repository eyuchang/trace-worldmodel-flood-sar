"""Canonical event and checkpoint contracts for the Reference state machine."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel
from trace_jepa.support import canonical_json_bytes


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


class ReferencePublicArtifactEnvelope(DeltaModel):
    """Canonical public artifact carried by one controller-visible runtime event."""

    schema_version: Literal["delta-reference-public-event-artifact-v1"]
    artifact_id: str = Field(min_length=1, max_length=200)
    artifact_schema_version: str = Field(min_length=1, max_length=200)
    artifact_json: str = Field(min_length=2, max_length=1_000_000)
    artifact_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_canonical_public_artifact(self) -> ReferencePublicArtifactEnvelope:
        try:
            value = json.loads(self.artifact_json)
        except json.JSONDecodeError as exc:
            raise ValueError("Reference public event artifact is not JSON") from exc
        if not isinstance(value, dict):
            raise TypeError("Reference public event artifact root must be an object")
        canonical = canonical_json_bytes(value).decode("utf-8").rstrip("\n")
        if canonical != self.artifact_json:
            raise ValueError("Reference public event artifact must use canonical JSON")
        digest = hashlib.sha256(self.artifact_json.encode("utf-8")).hexdigest()
        if digest != self.artifact_content_sha256:
            raise ValueError("Reference public event artifact digest is invalid")
        _reject_hidden_public_value(value)
        return self


def _reject_hidden_public_value(value: object) -> None:
    forbidden_keys = {
        "accepted_truth_incident_id",
        "affected_truth_person_ids",
        "candidate_digest",
        "episode_key",
        "hidden_lineage",
        "truth_incident_id",
        "truth_person_id",
        "truth_person_ids",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).casefold() in forbidden_keys:
                raise ValueError("Reference public event artifact contains a hidden-truth field")
            _reject_hidden_public_value(item)
        return
    if isinstance(value, list):
        for item in value:
            _reject_hidden_public_value(item)
        return
    if isinstance(value, str) and value.startswith(("RI-", "RP-")):
        raise ValueError("Reference public event artifact contains a hidden-truth identifier")
