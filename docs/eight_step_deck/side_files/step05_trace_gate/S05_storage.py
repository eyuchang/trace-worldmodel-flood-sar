from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from trace_jepa.contracts import Commitment, TraceRecord, WorldModelEvidence
from trace_jepa.util import canonical_json, sha256_value


class ImmutableWriteError(RuntimeError):
    pass


class EvidenceLedger:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, evidence: WorldModelEvidence) -> str:
        path = self.root / f"{evidence.evidence_id}.json"
        payload = evidence.model_dump(mode="json")
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if canonical_json(existing) != canonical_json(payload):
                raise ImmutableWriteError(f"evidence {evidence.evidence_id} already exists with different content")
            return evidence.evidence_id
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return evidence.evidence_id

    def get(self, evidence_id: str) -> WorldModelEvidence:
        path = self.root / f"{evidence_id}.json"
        if not path.exists():
            raise KeyError(evidence_id)
        return WorldModelEvidence.model_validate_json(path.read_text(encoding="utf-8"))


class TraceRepository:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def _envelopes(self) -> list[dict]:
        result: list[dict] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                result.append(json.loads(line))
        return result

    def write(self, record: TraceRecord) -> TraceRecord:
        envelopes = self._envelopes()
        key = (record.record_id, record.record_version)
        for envelope in envelopes:
            payload = envelope["payload"]
            if (payload["record_id"], payload["record_version"]) == key:
                if canonical_json(payload) == canonical_json(record.model_dump(mode="json")):
                    return record
                raise ImmutableWriteError(f"record version {key} already exists with different content")

        previous_hash = envelopes[-1]["entry_hash"] if envelopes else "GENESIS"
        payload = record.model_dump(mode="json")
        body = {
            "sequence": len(envelopes) + 1,
            "previous_hash": previous_hash,
            "payload_hash": sha256_value(payload),
            "payload": payload,
        }
        envelope = {**body, "entry_hash": sha256_value(body)}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(envelope, sort_keys=True) + "\n")
        return record

    def get(self, record_id: str, record_version: int | None = None) -> TraceRecord:
        matches = [
            TraceRecord.model_validate(item["payload"])
            for item in self._envelopes()
            if item["payload"]["record_id"] == record_id
        ]
        if not matches:
            raise KeyError(record_id)
        if record_version is None:
            return max(matches, key=lambda item: item.record_version)
        for record in matches:
            if record.record_version == record_version:
                return record
        raise KeyError((record_id, record_version))

    def all(self) -> list[TraceRecord]:
        return [TraceRecord.model_validate(item["payload"]) for item in self._envelopes()]

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
            if envelope["previous_hash"] != previous_hash:
                return False
            if envelope["payload_hash"] != sha256_value(payload):
                return False
            if envelope["entry_hash"] != sha256_value(body):
                return False
            previous_hash = envelope["entry_hash"]
        return True


class CommitmentLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def append(self, commitment: Commitment, record: TraceRecord) -> None:
        if commitment.authorizing_record_id != record.record_id:
            raise ValueError("commitment cites the wrong record id")
        if commitment.authorizing_record_version != record.record_version:
            raise ValueError("commitment cites the wrong record version")
        if not record.consumer_actions:
            raise ValueError("closure violation: record has no consumer action")
        last_action = record.consumer_actions[-1]
        if last_action.decision.value not in {"clear", "qualify"}:
            raise ValueError(f"closure violation: decision {last_action.decision.value} cannot authorize action")
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(commitment.model_dump(mode="json"), sort_keys=True) + "\n")

    def all(self) -> list[Commitment]:
        return [
            Commitment.model_validate(json.loads(line))
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
