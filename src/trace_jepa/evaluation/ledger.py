from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trace_jepa.util import canonical_json, sha256_value
from trace_jepa.evaluation.adjudication import ExecutionTruthLabel
from trace_jepa.workbench.models import EventType, SimulationEvent


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CommitmentLedgerRow(FrozenModel):
    schema_version: Literal["trace-commitment-ledger-v1"] = (
        "trace-commitment-ledger-v1"
    )
    proposal_sequence: int = Field(ge=1)
    plan_id: str
    record_id: str
    record_version: int = Field(ge=1)
    action_class: str
    route_id: str | None = None
    proposed_at: float = Field(ge=0.0)
    decision: str | None = None
    selected: bool = False
    proposed: bool = True
    executed: bool = False
    held: bool = False
    escalated: bool = False
    executed_stale: bool = False
    execution_sequence: int | None = Field(default=None, ge=1)
    truth_safe_at_execution: bool | None = None
    authorization_outside_tolerance: bool | None = None
    truth_oracle: str | None = None
    withdrawal_mode: str | None = None
    loss_components: dict[str, float]

    @model_validator(mode="after")
    def validate_accounting(self) -> "CommitmentLedgerRow":
        if sum((self.executed, self.held, self.escalated)) != 1:
            raise ValueError(
                "each proposal must resolve to exactly one final disposition"
            )
        if self.executed_stale and not self.executed:
            raise ValueError("executed_stale must be a subset of executed")
        if self.executed != (self.execution_sequence is not None):
            raise ValueError("execution_sequence must exist exactly for executed rows")
        return self


class CommitmentUnitLedgerRow(FrozenModel):
    """One stable commitment, collapsed across TRACE record revisions.

    ``CommitmentLedgerRow`` deliberately preserves every proposal event for
    forensic replay.  The paper's unit of analysis is instead the commitment:
    repeated versions of the same stable ``plan_id`` are one unit, not new
    opportunities created by the controller's replanning cadence.
    """

    schema_version: Literal["trace-commitment-unit-ledger-v1"] = (
        "trace-commitment-unit-ledger-v1"
    )
    plan_id: str
    record_id: str
    first_record_version: int = Field(ge=1)
    last_record_version: int = Field(ge=1)
    first_proposal_sequence: int = Field(ge=1)
    last_proposal_sequence: int = Field(ge=1)
    proposal_record_count: int = Field(ge=1)
    action_class: str
    route_id: str | None = None
    first_proposed_at: float = Field(ge=0.0)
    last_proposed_at: float = Field(ge=0.0)
    final_decision: str | None = None
    selected: bool = False
    proposed: bool = True
    executed: bool = False
    held: bool = False
    escalated: bool = False
    executed_stale: bool = False
    execution_sequence: int | None = Field(default=None, ge=1)
    truth_safe_at_execution: bool | None = None
    authorization_outside_tolerance: bool | None = None
    truth_oracle: str | None = None
    withdrawal_mode: str | None = None
    loss_components: dict[str, float]

    @model_validator(mode="after")
    def validate_accounting(self) -> "CommitmentUnitLedgerRow":
        if sum((self.executed, self.held, self.escalated)) != 1:
            raise ValueError(
                "each commitment unit must have exactly one final disposition"
            )
        if self.executed_stale and not self.executed:
            raise ValueError("executed_stale must be a subset of executed")
        if self.executed != (self.execution_sequence is not None):
            raise ValueError("execution_sequence must exist exactly for executed units")
        if self.first_record_version > self.last_record_version:
            raise ValueError("record-version bounds are reversed")
        if self.first_proposal_sequence > self.last_proposal_sequence:
            raise ValueError("proposal-sequence bounds are reversed")
        if self.first_proposed_at > self.last_proposed_at:
            raise ValueError("proposal-time bounds are reversed")
        return self


class RefreshLedgerRow(FrozenModel):
    schema_version: Literal["trace-refresh-ledger-v1"] = "trace-refresh-ledger-v1"
    trigger_sequence: int = Field(ge=1)
    refresh_decision_id: str
    evidence_request_id: str | None = None
    simulation_time: float = Field(ge=0.0)
    policy: str
    commitment_id: str
    claim_id: str
    record_id: str
    record_version: int = Field(ge=1)
    plan_id: str
    route_id: str | None = None
    family: str
    q: float | None = Field(default=None, ge=0.0, le=1.0)
    d_or_margin: float | None = None
    voi_table: tuple[dict[str, Any], ...] = ()
    selected_channel: str | None = None
    acquisition_sequence: int | None = Field(default=None, ge=1)
    cost: float | None = Field(default=None, ge=0.0)
    latency_s: float | None = Field(default=None, ge=0.0)
    usable: bool | None = None


def _latest_open_index(rows: list[dict[str, Any]], plan_id: str) -> int | None:
    for index in range(len(rows) - 1, -1, -1):
        row = rows[index]
        if row["plan_id"] == plan_id and not row.get("finalized", False):
            return index
    return None


def derive_commitment_ledger(
    events: Iterable[SimulationEvent],
    *,
    execution_truth: dict[int, ExecutionTruthLabel] | None = None,
) -> list[CommitmentLedgerRow]:
    rows: list[dict[str, Any]] = []
    for event in events:
        payload = event.payload
        if event.event_type == EventType.PLAN_PROPOSED:
            action = dict(payload["action"])
            rows.append(
                {
                    "proposal_sequence": event.sequence,
                    "plan_id": str(payload["plan_id"]),
                    "record_id": str(payload["record_id"]),
                    "record_version": int(payload["record_version"]),
                    "action_class": str(action["action_type"]),
                    "route_id": action.get("route_id"),
                    "proposed_at": event.simulation_time,
                    "decision": None,
                    "selected": False,
                    "executed": False,
                    "held": False,
                    "escalated": False,
                    "executed_stale": False,
                    "execution_sequence": None,
                    "truth_safe_at_execution": None,
                    "authorization_outside_tolerance": None,
                    "truth_oracle": None,
                    "withdrawal_mode": None,
                    "finalized": False,
                }
            )
            continue
        plan_id = payload.get("plan_id")
        if not plan_id:
            continue
        index = _latest_open_index(rows, str(plan_id))
        if index is None:
            continue
        row = rows[index]
        if event.event_type == EventType.COMMITMENT_DECISION:
            row["decision"] = payload.get("decision")
        elif event.event_type == EventType.PLAN_SELECTED:
            row["selected"] = True
        elif event.event_type == EventType.AUTH_WITHDRAWN:
            withdrawal_mode = str(payload.get("mode", "hold"))
            row["withdrawal_mode"] = withdrawal_mode
            row["escalated"] = withdrawal_mode == "escalate"
            row["held"] = not row["escalated"]
            row["finalized"] = True
        elif event.event_type == EventType.ACTION_STARTED:
            independent = (
                execution_truth.get(event.sequence)
                if execution_truth is not None
                else None
            )
            truth_safe = (
                independent.truth_safe
                if independent is not None
                else payload.get("truth_safe_at_execution")
            )
            executed_stale = (
                independent.executed_stale
                if independent is not None
                else bool(payload.get("executed_stale", False))
            )
            row.update(
                {
                    "selected": True,
                    "executed": True,
                    "execution_sequence": event.sequence,
                    "truth_safe_at_execution": truth_safe,
                    "authorization_outside_tolerance": payload.get(
                        "authorization_outside_tolerance"
                    ),
                    "executed_stale": executed_stale,
                    "truth_oracle": independent.oracle if independent else None,
                    "finalized": True,
                }
            )

    result: list[CommitmentLedgerRow] = []
    for row in rows:
        if not row["finalized"]:
            if row.get("decision") in {"hold", "block", "escalate"}:
                row["escalated"] = row.get("decision") == "escalate"
                row["held"] = not row["escalated"]
                row["finalized"] = True
            elif row["selected"]:
                row["held"] = True
                row["finalized"] = True
            else:
                # A clear/qualified alternative that merely lost planner
                # selection was never a pending commitment and is outside the
                # commitment risk set; it is not a gate HOLD.
                continue
        row["loss_components"] = {
            "failure_loss_if_stale": 100.0,
            "reroute_loss": 15.0,
            "missed_rescue_loss": 200.0,
            "false_hold_rate_per_hour": 10.0,
            "escalation_cost": 3.0,
            "realized_stale_loss": 100.0 if row["executed_stale"] else 0.0,
            "realized_escalation_cost": 3.0 if row["escalated"] else 0.0,
        }
        row.pop("finalized", None)
        result.append(CommitmentLedgerRow.model_validate(row))
    return result


def derive_refresh_ledger(
    events: Iterable[SimulationEvent],
) -> list[RefreshLedgerRow]:
    rows: list[dict[str, Any]] = []
    open_by_decision: dict[str, list[int]] = {}
    for event in events:
        payload = event.payload
        if event.event_type == EventType.REFRESH_TRIGGERED:
            commitment_id = str(payload["commitment_id"])
            refresh_decision_id = str(payload["refresh_decision_id"])
            row = {
                "trigger_sequence": event.sequence,
                "refresh_decision_id": refresh_decision_id,
                "evidence_request_id": payload.get("evidence_request_id"),
                "simulation_time": event.simulation_time,
                "policy": str(payload["policy"]),
                "commitment_id": commitment_id,
                "claim_id": str(payload["claim_id"]),
                "record_id": str(payload["record_id"]),
                "record_version": int(payload["record_version"]),
                "plan_id": str(payload["plan_id"]),
                "route_id": payload.get("route_id"),
                "family": str(payload["family"]),
                "q": payload.get("q"),
                "d_or_margin": payload.get("d_or_margin"),
                "voi_table": tuple(payload.get("voi_table", ())),
                "selected_channel": payload.get("selected_channel"),
                "acquisition_sequence": None,
                "cost": None,
                "latency_s": None,
                "usable": None,
            }
            rows.append(row)
            if row["selected_channel"] is not None:
                open_by_decision.setdefault(refresh_decision_id, []).append(
                    len(rows) - 1
                )
            continue
        if event.event_type != EventType.EVIDENCE_ACQUIRED:
            continue
        refresh_decision_id = payload.get("refresh_decision_id")
        if refresh_decision_id is None:
            continue
        indices = open_by_decision.pop(str(refresh_decision_id), [])
        for index in indices:
            rows[index].update(
                {
                    "acquisition_sequence": event.sequence,
                    "cost": payload.get("cost"),
                    "latency_s": payload.get("latency_s"),
                    "usable": payload.get("usable"),
                }
            )
    return [RefreshLedgerRow.model_validate(row) for row in rows]


def derive_commitment_unit_ledger(
    rows: Iterable[CommitmentLedgerRow],
) -> list[CommitmentUnitLedgerRow]:
    """Collapse proposal records by stable plan identity.

    An execution is terminal for accounting.  Otherwise any escalation is
    retained as the unit disposition; all remaining units are held.  The raw
    proposal ledger remains the authoritative record-version history.
    """

    grouped: dict[str, list[CommitmentLedgerRow]] = {}
    for row in rows:
        grouped.setdefault(row.plan_id, []).append(row)

    units: list[CommitmentUnitLedgerRow] = []
    for plan_id, group in grouped.items():
        ordered = sorted(group, key=lambda row: row.proposal_sequence)
        identity = {
            (row.record_id, row.action_class, row.route_id) for row in ordered
        }
        if len(identity) != 1:
            raise ValueError(
                f"proposal records disagree on stable identity for plan {plan_id}"
            )
        versions = [row.record_version for row in ordered]
        if len(versions) != len(set(versions)) or versions != sorted(versions):
            raise ValueError(
                f"proposal record versions are not unique and ordered for plan {plan_id}"
            )
        executions = [row for row in ordered if row.executed]
        if len(executions) > 1:
            raise ValueError(f"commitment {plan_id} executed more than once")

        execution = executions[0] if executions else None
        escalations = [row for row in ordered if row.escalated]
        disposition_source = execution or (escalations[-1] if escalations else ordered[-1])
        executed = execution is not None
        escalated = not executed and bool(escalations)
        final_decision = next(
            (row.decision for row in reversed(ordered) if row.decision is not None),
            None,
        )
        withdrawal_mode = next(
            (
                row.withdrawal_mode
                for row in reversed(ordered)
                if row.withdrawal_mode is not None
            ),
            None,
        )
        record_id, action_class, route_id = next(iter(identity))
        units.append(
            CommitmentUnitLedgerRow(
                plan_id=plan_id,
                record_id=record_id,
                first_record_version=versions[0],
                last_record_version=versions[-1],
                first_proposal_sequence=ordered[0].proposal_sequence,
                last_proposal_sequence=ordered[-1].proposal_sequence,
                proposal_record_count=len(ordered),
                action_class=action_class,
                route_id=route_id,
                first_proposed_at=ordered[0].proposed_at,
                last_proposed_at=ordered[-1].proposed_at,
                final_decision=final_decision,
                selected=any(row.selected for row in ordered),
                executed=executed,
                held=not executed and not escalated,
                escalated=escalated,
                executed_stale=bool(execution and execution.executed_stale),
                execution_sequence=(
                    execution.execution_sequence if execution is not None else None
                ),
                truth_safe_at_execution=(
                    execution.truth_safe_at_execution
                    if execution is not None
                    else None
                ),
                authorization_outside_tolerance=(
                    execution.authorization_outside_tolerance
                    if execution is not None
                    else None
                ),
                truth_oracle=(execution.truth_oracle if execution is not None else None),
                withdrawal_mode=withdrawal_mode,
                loss_components=disposition_source.loss_components,
            )
        )
    return sorted(units, key=lambda row: row.first_proposal_sequence)


T = TypeVar("T", bound=BaseModel)


def write_hashed_ledger(path: str | Path, rows: Iterable[BaseModel]) -> str:
    """Atomically write a deterministic hash-chained JSONL sidecar."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    previous_hash = "GENESIS"
    envelopes = []
    for sequence, row in enumerate(rows, start=1):
        payload = row.model_dump(mode="json")
        body = {
            "sequence": sequence,
            "previous_hash": previous_hash,
            "payload_hash": sha256_value(payload),
            "payload": payload,
        }
        envelope = {**body, "entry_hash": sha256_value(body)}
        envelopes.append(envelope)
        previous_hash = envelope["entry_hash"]

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for envelope in envelopes:
                handle.write(canonical_json(envelope) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return previous_hash


def verify_hashed_ledger(path: str | Path) -> bool:
    previous_hash = "GENESIS"
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        for sequence, line in enumerate(lines, start=1):
            envelope = json.loads(line)
            payload = envelope["payload"]
            body = {
                "sequence": sequence,
                "previous_hash": previous_hash,
                "payload_hash": sha256_value(payload),
                "payload": payload,
            }
            if envelope["sequence"] != sequence:
                return False
            if envelope["previous_hash"] != previous_hash:
                return False
            if envelope["payload_hash"] != sha256_value(payload):
                return False
            if envelope["entry_hash"] != sha256_value(body):
                return False
            previous_hash = envelope["entry_hash"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return True


def read_hashed_ledger(path: str | Path, model: type[T]) -> list[T]:
    if not verify_hashed_ledger(path):
        raise ValueError("ledger hash chain verification failed")
    return [
        model.model_validate(json.loads(line)["payload"])
        for line in Path(path).read_text(encoding="utf-8").splitlines()
    ]
