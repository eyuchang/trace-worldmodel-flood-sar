from __future__ import annotations

import json
from pathlib import Path

from trace_jepa.util import canonical_json, sha256_value
from trace_jepa.workbench.models import SimulationEvent


class EventStore:
    """Append-only, hash-chained simulation event log."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def _envelopes(self) -> list[dict]:
        rows: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def append(self, event: SimulationEvent) -> SimulationEvent:
        envelopes = self._envelopes()
        for envelope in envelopes:
            payload = envelope["payload"]
            if payload["event_id"] == event.event_id:
                if canonical_json(payload) == canonical_json(event.model_dump(mode="json")):
                    return event
                raise ValueError(f"event {event.event_id} already exists with different content")

        previous_hash = envelopes[-1]["entry_hash"] if envelopes else "GENESIS"
        payload = event.model_dump(mode="json")
        body = {
            "sequence": len(envelopes) + 1,
            "previous_hash": previous_hash,
            "payload_hash": sha256_value(payload),
            "payload": payload,
        }
        envelope = {**body, "entry_hash": sha256_value(body)}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(envelope, sort_keys=True) + "\n")
        return event

    def all(self) -> list[SimulationEvent]:
        return [SimulationEvent.model_validate(item["payload"]) for item in self._envelopes()]

    def verify_chain(self) -> bool:
        previous_hash = "GENESIS"
        for index, envelope in enumerate(self._envelopes(), start=1):
            payload = envelope["payload"]
            body = {
                "sequence": index,
                "previous_hash": previous_hash,
                "payload_hash": sha256_value(payload),
                "payload": payload,
            }
            if envelope["sequence"] != index:
                return False
            if envelope["previous_hash"] != previous_hash:
                return False
            if envelope["payload_hash"] != sha256_value(payload):
                return False
            if envelope["entry_hash"] != sha256_value(body):
                return False
            previous_hash = envelope["entry_hash"]
        return True

    def clear(self) -> None:
        self.path.write_text("", encoding="utf-8")
