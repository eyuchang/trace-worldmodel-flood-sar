"""Deterministic event chain, reducer, checkpoint, and restart support."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from trace_jepa.support import canonical_json_bytes
from trace_reference.domain.events import (
    ReferenceEvent,
    ReferenceEventType,
    ReferenceEventVisibility,
    ReferenceRuntimeCheckpoint,
)


def _canonical_payload(payload: Mapping[str, object]) -> str:
    return canonical_json_bytes(payload).decode("utf-8").rstrip("\n")


def _digest(value: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _event_body(
    *,
    sequence: int,
    at_s: int,
    event_type: ReferenceEventType,
    visibility: ReferenceEventVisibility,
    payload_json: str,
    previous_event_digest: str,
) -> dict[str, object]:
    return {
        "schema_version": "delta-reference-event-v1",
        "sequence": sequence,
        "at_s": at_s,
        "event_type": event_type.value,
        "visibility": visibility.value,
        "payload_json": payload_json,
        "previous_event_digest": previous_event_digest,
    }


def create_reference_event(
    *,
    sequence: int,
    at_s: int,
    event_type: ReferenceEventType,
    visibility: ReferenceEventVisibility,
    payload: Mapping[str, object],
    previous_event_digest: str,
) -> ReferenceEvent:
    """Create one content-addressed event without nondeterministic identifiers."""

    payload_json = _canonical_payload(payload)
    body = _event_body(
        sequence=sequence,
        at_s=at_s,
        event_type=event_type,
        visibility=visibility,
        payload_json=payload_json,
        previous_event_digest=previous_event_digest,
    )
    event_digest = _digest(body)
    return ReferenceEvent(
        **body,
        event_id=f"reference-event-{event_digest[:20]}",
        event_digest=event_digest,
    )


def verify_reference_event(event: ReferenceEvent) -> bool:
    body = _event_body(
        sequence=event.sequence,
        at_s=event.at_s,
        event_type=event.event_type,
        visibility=event.visibility,
        payload_json=event.payload_json,
        previous_event_digest=event.previous_event_digest,
    )
    digest = _digest(body)
    return digest == event.event_digest and event.event_id == f"reference-event-{digest[:20]}"


@dataclass
class ReferenceWorldState:
    """Minimal physical reducer state; later slices add public mission state."""

    at_s: int = -172_800
    breach_active: bool = False
    breach_width_milli_ft: int = 0
    stored_milli_acre_ft: int = 0
    crossing_status: dict[str, str] = field(default_factory=dict)
    public_environment_digest: str = "GENESIS"
    event_prefix_digest: str = "GENESIS"

    def canonical_value(self) -> dict[str, object]:
        return {
            "at_s": self.at_s,
            "breach_active": self.breach_active,
            "breach_width_milli_ft": self.breach_width_milli_ft,
            "stored_milli_acre_ft": self.stored_milli_acre_ft,
            "crossing_status": dict(sorted(self.crossing_status.items())),
            "public_environment_digest": self.public_environment_digest,
            "event_prefix_digest": self.event_prefix_digest,
        }

    def apply(self, event: ReferenceEvent) -> None:
        if not verify_reference_event(event):
            raise ValueError("Reference event digest is invalid")
        payload = json.loads(event.payload_json)
        if not isinstance(payload, dict):
            raise TypeError("Reference event payload root must be an object")
        self.at_s = event.at_s
        if event.event_type == ReferenceEventType.HIDDEN_PHYSICAL_TRUTH:
            breach = payload.get("breach")
            if not isinstance(breach, dict):
                raise TypeError("hidden physical event requires a breach object")
            self.breach_active = bool(breach["active"])
            self.breach_width_milli_ft = int(breach["width_milli_ft"])
            self.stored_milli_acre_ft = int(breach["stored_milli_acre_ft"])
        elif event.event_type == ReferenceEventType.CROSSING_STATE_CHANGED:
            crossing_id = str(payload["crossing_id"])
            self.crossing_status[crossing_id] = str(payload["status"])
        elif event.event_type == ReferenceEventType.PUBLIC_ENVIRONMENT_SAMPLE:
            self.public_environment_digest = hashlib.sha256(
                event.payload_json.encode("utf-8")
            ).hexdigest()
        self.event_prefix_digest = event.event_digest


class ReferenceEventLog:
    """Append-only event log with chain, replay, checkpoint, and restart verification."""

    def __init__(self, events: Iterable[ReferenceEvent] = ()) -> None:
        self._events: list[ReferenceEvent] = []
        for event in events:
            self.append_existing(event)

    @property
    def events(self) -> tuple[ReferenceEvent, ...]:
        return tuple(self._events)

    @property
    def prefix_digest(self) -> str:
        return self._events[-1].event_digest if self._events else "GENESIS"

    def append(
        self,
        *,
        at_s: int,
        event_type: ReferenceEventType,
        visibility: ReferenceEventVisibility,
        payload: Mapping[str, object],
    ) -> ReferenceEvent:
        if self._events and at_s < self._events[-1].at_s:
            raise ValueError("Reference event time cannot move backwards")
        event = create_reference_event(
            sequence=len(self._events) + 1,
            at_s=at_s,
            event_type=event_type,
            visibility=visibility,
            payload=payload,
            previous_event_digest=self.prefix_digest,
        )
        self._events.append(event)
        return event

    def append_existing(self, event: ReferenceEvent) -> None:
        if event.sequence != len(self._events) + 1:
            raise ValueError("Reference event sequence is not contiguous")
        if event.previous_event_digest != self.prefix_digest:
            raise ValueError("Reference event previous digest does not match chain prefix")
        if self._events and event.at_s < self._events[-1].at_s:
            raise ValueError("Reference event time cannot move backwards")
        if not verify_reference_event(event):
            raise ValueError("Reference event digest is invalid")
        self._events.append(event)

    def verify(self) -> bool:
        try:
            ReferenceEventLog(self._events)
        except ValueError:
            return False
        return True

    def replay(self, *, through_sequence: int | None = None) -> ReferenceWorldState:
        state = ReferenceWorldState()
        limit = len(self._events) if through_sequence is None else through_sequence
        if limit < 0 or limit > len(self._events):
            raise ValueError("Reference replay boundary is outside the event log")
        for event in self._events[:limit]:
            state.apply(event)
        return state

    def checkpoint(self, *, through_sequence: int) -> ReferenceRuntimeCheckpoint:
        state = self.replay(through_sequence=through_sequence)
        state_json = _canonical_payload(state.canonical_value())
        state_digest = hashlib.sha256(state_json.encode("utf-8")).hexdigest()
        body = {
            "schema_version": "delta-reference-runtime-checkpoint-v1",
            "sequence": through_sequence,
            "at_s": state.at_s,
            "event_prefix_digest": state.event_prefix_digest,
            "state_json": state_json,
            "state_digest": state_digest,
        }
        return ReferenceRuntimeCheckpoint(**body, checkpoint_digest=_digest(body))

    def resume(
        self,
        checkpoint: ReferenceRuntimeCheckpoint,
    ) -> ReferenceWorldState:
        body = checkpoint.model_dump(mode="json", exclude={"checkpoint_digest"})
        if _digest(body) != checkpoint.checkpoint_digest:
            raise ValueError("Reference checkpoint digest is invalid")
        prefix = (
            "GENESIS"
            if checkpoint.sequence == 0
            else self._events[checkpoint.sequence - 1].event_digest
        )
        if prefix != checkpoint.event_prefix_digest:
            raise ValueError("Reference checkpoint does not bind this event log")
        expected = self.replay(through_sequence=checkpoint.sequence)
        expected_json = _canonical_payload(expected.canonical_value())
        if hashlib.sha256(expected_json.encode("utf-8")).hexdigest() != checkpoint.state_digest:
            raise ValueError("Reference checkpoint state digest is invalid")
        if expected_json != checkpoint.state_json:
            raise ValueError("Reference checkpoint state does not match event replay")
        return expected
