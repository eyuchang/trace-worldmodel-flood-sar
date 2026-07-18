from __future__ import annotations

import json
from pathlib import Path

from trace_jepa.contracts import TraceRecord
from trace_jepa.runtime.storage import ImmutableWriteError, TraceRepository
from trace_jepa.util import canonical_json, sha256_value
from trace_jepa.workbench.models import SimulationEvent
from trace_jepa.workbench.store import EventStore


class CachedEventStore(EventStore):
    """Run-local O(1) append cache with the frozen EventStore byte contract.

    The published log is still independently verified by the unmodified
    EventStore. This class only avoids reparsing the complete file for every
    append and sequence lookup during accelerated experiment execution.
    """

    def __init__(self, path: str | Path):
        super().__init__(path)
        envelopes = super()._envelopes()
        self._events = [
            SimulationEvent.model_validate(envelope["payload"])
            for envelope in envelopes
        ]
        self._payload_by_id = {
            event.event_id: event.model_dump(mode="json") for event in self._events
        }
        self._head = envelopes[-1]["entry_hash"] if envelopes else "GENESIS"

    def append(self, event: SimulationEvent) -> SimulationEvent:
        payload = event.model_dump(mode="json")
        existing = self._payload_by_id.get(event.event_id)
        if existing is not None:
            if canonical_json(existing) == canonical_json(payload):
                return event
            raise ValueError(
                f"event {event.event_id} already exists with different content"
            )
        body = {
            "sequence": len(self._events) + 1,
            "previous_hash": self._head,
            "payload_hash": sha256_value(payload),
            "payload": payload,
        }
        envelope = {**body, "entry_hash": sha256_value(body)}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(envelope, sort_keys=True) + "\n")
        self._events.append(event)
        self._payload_by_id[event.event_id] = payload
        self._head = envelope["entry_hash"]
        return event

    def all(self) -> list[SimulationEvent]:
        return list(self._events)

    def clear(self) -> None:
        super().clear()
        self._events.clear()
        self._payload_by_id.clear()
        self._head = "GENESIS"


class CachedTraceRepository(TraceRepository):
    """Run-local TRACE cache preserving the frozen repository log format."""

    def __init__(self, path: Path):
        super().__init__(path)
        envelopes = super()._envelopes()
        self._records = [
            TraceRecord.model_validate(envelope["payload"])
            for envelope in envelopes
        ]
        self._by_key = {
            (record.record_id, record.record_version): record
            for record in self._records
        }
        self._latest: dict[str, TraceRecord] = {}
        for record in self._records:
            current = self._latest.get(record.record_id)
            if current is None or record.record_version > current.record_version:
                self._latest[record.record_id] = record
        self._head = envelopes[-1]["entry_hash"] if envelopes else "GENESIS"

    def write(self, record: TraceRecord) -> TraceRecord:
        key = (record.record_id, record.record_version)
        existing = self._by_key.get(key)
        if existing is not None:
            if canonical_json(existing.model_dump(mode="json")) == canonical_json(
                record.model_dump(mode="json")
            ):
                return record
            raise ImmutableWriteError(
                f"record version {key} already exists with different content"
            )
        payload = record.model_dump(mode="json")
        body = {
            "sequence": len(self._records) + 1,
            "previous_hash": self._head,
            "payload_hash": sha256_value(payload),
            "payload": payload,
        }
        envelope = {**body, "entry_hash": sha256_value(body)}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(envelope, sort_keys=True) + "\n")
        self._records.append(record)
        self._by_key[key] = record
        current = self._latest.get(record.record_id)
        if current is None or record.record_version > current.record_version:
            self._latest[record.record_id] = record
        self._head = envelope["entry_hash"]
        return record

    def get(self, record_id: str, record_version: int | None = None) -> TraceRecord:
        if record_version is None:
            if record_id not in self._latest:
                raise KeyError(record_id)
            return self._latest[record_id]
        try:
            return self._by_key[(record_id, record_version)]
        except KeyError as exc:
            raise KeyError((record_id, record_version)) from exc

    def all(self) -> list[TraceRecord]:
        return list(self._records)
