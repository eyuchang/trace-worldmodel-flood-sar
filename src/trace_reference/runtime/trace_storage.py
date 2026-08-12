"""Bounded append-only TRACE persistence for the larger Reference workload."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from trace_jepa.contracts import Commitment, TraceRecord, WorldModelEvidence
from trace_jepa.runtime.storage import (
    CommitmentLog,
    EvidenceLedger,
    ImmutableWriteError,
    TraceRepository,
)
from trace_jepa.support import (
    atomic_write_bytes,
    canonical_json_bytes,
    safe_directory,
    safe_output_file,
    safe_regular_file,
)
from trace_jepa.util import sha256_value

_ARTIFACT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_MAX_LEDGER_BYTES = 256 * 1024 * 1024
_MAX_EVIDENCE_BYTES = 1024 * 1024


def _append_line(path: Path, value: object, *, trusted_root: Path, label: str) -> None:
    payload = canonical_json_bytes(value)
    safe = safe_regular_file(
        path,
        declared_root=trusted_root,
        maximum_bytes=_MAX_LEDGER_BYTES,
        label=label,
    )
    if safe.stat().st_size + len(payload) > _MAX_LEDGER_BYTES:
        raise ValueError(f"{label} exceeds the maximum expected size")
    with safe.open("ab") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _load_json_lines(path: Path, *, maximum_bytes: int, label: str) -> list[dict[str, object]]:
    safe = safe_regular_file(
        path,
        declared_root=path.parent,
        maximum_bytes=maximum_bytes,
        label=label,
    )
    values: list[dict[str, object]] = []
    with safe.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{label} line {line_number} is invalid JSON") from exc
            if not isinstance(value, dict):
                raise TypeError(f"{label} line {line_number} must be an object")
            values.append(value)
    return values


def _prepare_file(root: Path, relative_name: Path, label: str) -> Path:
    trusted = safe_directory(root, declared_root=root, label=label)
    relative = Path(relative_name)
    if relative.is_absolute() or len(relative.parts) != 1 or ".." in relative.parts:
        raise ValueError(f"{label} has an unsafe relative name")
    destination = trusted / relative
    safe_output_file(destination, declared_root=trusted, label=label)
    if not destination.exists():
        atomic_write_bytes(destination, b"", root=trusted, label=label)
    safe_regular_file(
        destination,
        declared_root=trusted,
        maximum_bytes=_MAX_LEDGER_BYTES,
        label=label,
    )
    return destination


class ReferenceEvidenceLedger(EvidenceLedger):
    """Immutable, canonical evidence objects beneath one caller-trusted root."""

    def __init__(self, trusted_root: Path, relative_name: Path = Path("evidence")) -> None:
        self._trusted_root = safe_directory(
            trusted_root,
            declared_root=trusted_root,
            label="Reference TRACE runtime",
        )
        relative = Path(relative_name)
        if relative.is_absolute() or len(relative.parts) != 1 or ".." in relative.parts:
            raise ValueError("Reference evidence directory has an unsafe relative name")
        self.root = self._trusted_root / relative
        self.root.mkdir(parents=True, exist_ok=True)
        safe_directory(
            self.root,
            declared_root=self._trusted_root,
            label="Reference evidence directory",
        )
        self._index_path = _prepare_file(
            self._trusted_root,
            Path(f"{relative.name}_index.jsonl"),
            "Reference evidence index",
        )
        self._index = _load_json_lines(
            self._index_path,
            maximum_bytes=_MAX_LEDGER_BYTES,
            label="Reference evidence index",
        )
        self._evidence_hashes: dict[str, str] = {}
        if not self.verify_chain():
            raise ValueError("Reference evidence index chain is invalid")

    @property
    def prefix_digest(self) -> str:
        return str(self._index[-1]["entry_hash"]) if self._index else "GENESIS"

    def verify_chain(self) -> bool:
        previous_hash = "GENESIS"
        seen: set[str] = set()
        discovered = {
            item.stem for item in self.root.iterdir() if item.is_file() and item.suffix == ".json"
        }
        for index, envelope in enumerate(self._index, start=1):
            try:
                evidence_id = str(envelope["evidence_id"])
                content_hash = str(envelope["content_sha256"])
                body = {
                    "sequence": index,
                    "previous_hash": previous_hash,
                    "evidence_id": evidence_id,
                    "content_sha256": content_hash,
                }
                if evidence_id in seen or _ARTIFACT_ID.fullmatch(evidence_id) is None:
                    return False
                if envelope.get("sequence") != index:
                    return False
                if envelope.get("previous_hash") != previous_hash:
                    return False
                if envelope.get("entry_hash") != sha256_value(body):
                    return False
                path = safe_regular_file(
                    self.root / f"{evidence_id}.json",
                    declared_root=self._trusted_root,
                    maximum_bytes=_MAX_EVIDENCE_BYTES,
                    label="Reference evidence artifact",
                )
                if hashlib.sha256(path.read_bytes()).hexdigest() != content_hash:
                    return False
                seen.add(evidence_id)
                self._evidence_hashes[evidence_id] = content_hash
                previous_hash = str(envelope["entry_hash"])
            except (KeyError, OSError, TypeError, ValueError):
                return False
        return seen == discovered

    def _path(self, evidence_id: str) -> Path:
        if _ARTIFACT_ID.fullmatch(evidence_id) is None:
            raise ValueError("Reference evidence ID is unsafe")
        path = self.root / f"{evidence_id}.json"
        safe_output_file(
            path,
            declared_root=self._trusted_root,
            label="Reference evidence artifact",
        )
        return path

    def put(self, evidence: WorldModelEvidence) -> str:
        path = self._path(evidence.evidence_id)
        payload = canonical_json_bytes(evidence.model_dump(mode="json"))
        if len(payload) > _MAX_EVIDENCE_BYTES:
            raise ValueError("Reference evidence exceeds the maximum expected size")
        if path.exists():
            existing = safe_regular_file(
                path,
                declared_root=self._trusted_root,
                maximum_bytes=_MAX_EVIDENCE_BYTES,
                label="Reference evidence artifact",
            ).read_bytes()
            if existing != payload:
                raise ImmutableWriteError(
                    f"evidence {evidence.evidence_id} already exists with different content"
                )
            if evidence.evidence_id not in self._evidence_hashes:
                raise ValueError("Reference evidence artifact is absent from its index")
            return evidence.evidence_id
        content_hash = hashlib.sha256(payload).hexdigest()
        atomic_write_bytes(
            path,
            payload,
            root=self._trusted_root,
            label="Reference evidence artifact",
        )
        body = {
            "sequence": len(self._index) + 1,
            "previous_hash": self.prefix_digest,
            "evidence_id": evidence.evidence_id,
            "content_sha256": content_hash,
        }
        envelope = {**body, "entry_hash": sha256_value(body)}
        _append_line(
            self._index_path,
            envelope,
            trusted_root=self._trusted_root,
            label="Reference evidence index",
        )
        self._index.append(envelope)
        self._evidence_hashes[evidence.evidence_id] = content_hash
        return evidence.evidence_id

    def get(self, evidence_id: str) -> WorldModelEvidence:
        path = self._path(evidence_id)
        if not path.exists():
            raise KeyError(evidence_id)
        safe = safe_regular_file(
            path,
            declared_root=self._trusted_root,
            maximum_bytes=_MAX_EVIDENCE_BYTES,
            label="Reference evidence artifact",
        )
        return WorldModelEvidence.model_validate_json(safe.read_text(encoding="utf-8"))


class ReferenceTraceRepository(TraceRepository):
    """Cached hash-chain repository with O(1) record identity lookup."""

    def __init__(
        self,
        trusted_root: Path,
        relative_name: Path = Path("trace_records.jsonl"),
    ) -> None:
        self.path = _prepare_file(trusted_root, relative_name, "Reference TRACE repository")
        self._trusted_root = Path(trusted_root)
        self._cache = _load_json_lines(
            self.path,
            maximum_bytes=_MAX_LEDGER_BYTES,
            label="Reference TRACE repository",
        )
        self._records: dict[tuple[str, int], TraceRecord] = {}
        self._latest: dict[str, TraceRecord] = {}
        self._ordered: list[TraceRecord] = []
        if not self.verify_chain():
            raise ValueError("Reference TRACE repository chain is invalid")
        for envelope in self._cache:
            record = TraceRecord.model_validate(envelope["payload"])
            key = (record.record_id, record.record_version)
            if key in self._records:
                raise ValueError("Reference TRACE record identity is duplicated")
            self._records[key] = record
            self._ordered.append(record)
            previous = self._latest.get(record.record_id)
            if previous is None or previous.record_version < record.record_version:
                self._latest[record.record_id] = record

    def _envelopes(self) -> list[dict[str, object]]:
        return list(self._cache)

    @property
    def prefix_digest(self) -> str:
        return str(self._cache[-1]["entry_hash"]) if self._cache else "GENESIS"

    def write(self, record: TraceRecord) -> TraceRecord:
        key = (record.record_id, record.record_version)
        existing = self._records.get(key)
        if existing is not None:
            if existing == record:
                return record
            raise ImmutableWriteError(f"record version {key} already exists with different content")
        previous_hash = str(self._cache[-1]["entry_hash"]) if self._cache else "GENESIS"
        payload = record.model_dump(mode="json")
        body = {
            "sequence": len(self._cache) + 1,
            "previous_hash": previous_hash,
            "payload_hash": sha256_value(payload),
            "payload": payload,
        }
        envelope = {**body, "entry_hash": sha256_value(body)}
        _append_line(
            self.path,
            envelope,
            trusted_root=self._trusted_root,
            label="Reference TRACE repository",
        )
        self._cache.append(envelope)
        self._records[key] = record
        self._ordered.append(record)
        previous = self._latest.get(record.record_id)
        if previous is None or previous.record_version < record.record_version:
            self._latest[record.record_id] = record
        return record

    def get(self, record_id: str, record_version: int | None = None) -> TraceRecord:
        if record_version is None:
            try:
                return self._latest[record_id]
            except KeyError as exc:
                raise KeyError(record_id) from exc
        try:
            return self._records[(record_id, record_version)]
        except KeyError as exc:
            raise KeyError((record_id, record_version)) from exc

    def all(self) -> list[TraceRecord]:
        return list(self._ordered)

    def verify_chain(self) -> bool:
        previous_hash = "GENESIS"
        seen: set[tuple[str, int]] = set()
        for index, envelope in enumerate(self._cache, start=1):
            try:
                payload = envelope["payload"]
                if not isinstance(payload, dict):
                    return False
                record = TraceRecord.model_validate(payload)
                key = (record.record_id, record.record_version)
                body = {
                    "sequence": index,
                    "previous_hash": previous_hash,
                    "payload_hash": sha256_value(payload),
                    "payload": payload,
                }
                if key in seen:
                    return False
                if envelope.get("sequence") != index:
                    return False
                if envelope.get("previous_hash") != previous_hash:
                    return False
                if envelope.get("payload_hash") != sha256_value(payload):
                    return False
                if envelope.get("entry_hash") != sha256_value(body):
                    return False
                seen.add(key)
                previous_hash = str(envelope["entry_hash"])
            except (KeyError, TypeError, ValueError):
                return False
        return True


class ReferenceCommitmentLog(CommitmentLog):
    """Idempotent commitment ledger with an independently verified hash chain."""

    def __init__(
        self,
        trusted_root: Path,
        relative_name: Path = Path("commitments.jsonl"),
    ) -> None:
        self.path = _prepare_file(trusted_root, relative_name, "Reference commitment log")
        self._trusted_root = Path(trusted_root)
        self._cache = _load_json_lines(
            self.path,
            maximum_bytes=_MAX_LEDGER_BYTES,
            label="Reference commitment log",
        )
        self._commitments: dict[str, Commitment] = {}
        if not self.verify_chain():
            raise ValueError("Reference commitment chain is invalid")
        for envelope in self._cache:
            commitment = Commitment.model_validate(envelope["payload"])
            if commitment.commitment_id in self._commitments:
                raise ValueError("Reference commitment identity is duplicated")
            self._commitments[commitment.commitment_id] = commitment

    def append(self, commitment: Commitment, record: TraceRecord) -> None:
        if commitment.authorizing_record_id != record.record_id:
            raise ValueError("commitment cites the wrong record id")
        if commitment.authorizing_record_version != record.record_version:
            raise ValueError("commitment cites the wrong record version")
        if not record.consumer_actions:
            raise ValueError("closure violation: record has no consumer action")
        if record.consumer_actions[-1].decision.value not in {"clear", "qualify"}:
            raise ValueError("closure violation: consumed decision cannot authorize action")
        existing = self._commitments.get(commitment.commitment_id)
        if existing is not None:
            if existing == commitment:
                return
            raise ImmutableWriteError(
                f"commitment {commitment.commitment_id} already exists with different content"
            )
        previous_hash = str(self._cache[-1]["entry_hash"]) if self._cache else "GENESIS"
        payload = commitment.model_dump(mode="json")
        body = {
            "sequence": len(self._cache) + 1,
            "previous_hash": previous_hash,
            "payload_hash": sha256_value(payload),
            "payload": payload,
        }
        envelope = {**body, "entry_hash": sha256_value(body)}
        _append_line(
            self.path,
            envelope,
            trusted_root=self._trusted_root,
            label="Reference commitment log",
        )
        self._cache.append(envelope)
        self._commitments[commitment.commitment_id] = commitment

    @property
    def prefix_digest(self) -> str:
        return str(self._cache[-1]["entry_hash"]) if self._cache else "GENESIS"

    def all(self) -> list[Commitment]:
        return [self._commitments[key] for key in sorted(self._commitments)]

    def verify_chain(self) -> bool:
        previous_hash = "GENESIS"
        seen: set[str] = set()
        for index, envelope in enumerate(self._cache, start=1):
            try:
                payload = envelope["payload"]
                if not isinstance(payload, dict):
                    return False
                commitment = Commitment.model_validate(payload)
                body = {
                    "sequence": index,
                    "previous_hash": previous_hash,
                    "payload_hash": sha256_value(payload),
                    "payload": payload,
                }
                if commitment.commitment_id in seen:
                    return False
                if envelope.get("sequence") != index:
                    return False
                if envelope.get("previous_hash") != previous_hash:
                    return False
                if envelope.get("payload_hash") != sha256_value(payload):
                    return False
                if envelope.get("entry_hash") != sha256_value(body):
                    return False
                seen.add(commitment.commitment_id)
                previous_hash = str(envelope["entry_hash"])
            except (KeyError, TypeError, ValueError):
                return False
        return True
