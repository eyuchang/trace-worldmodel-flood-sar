from __future__ import annotations

from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trace_jepa.evaluation.ledger import (
    CommitmentLedgerRow,
    CommitmentUnitLedgerRow,
    RefreshLedgerRow,
)


ELIGIBLE_COMMITMENT_ACTIONS = frozenset(
    {
        "dispatch_rescue_boat",
        "dispatch_helicopter",
        "deploy_ground_team",
        "evacuate_to_safety",
        "select_dock",
        "rendezvous",
    }
)


class CommitmentMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    proposal_records: int | None = Field(default=None, ge=0)
    proposed: int = Field(ge=0)
    executed: int = Field(ge=0)
    held: int = Field(ge=0)
    escalated: int = Field(ge=0)
    executed_stale: int = Field(ge=0)
    coverage: float = Field(ge=0.0, le=1.0)
    stale_execution_rate: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_conservation(self) -> "CommitmentMetrics":
        if self.proposed != self.executed + self.held + self.escalated:
            raise ValueError("commitment accounting does not conserve proposals")
        if self.executed_stale > self.executed:
            raise ValueError("executed_stale exceeds executed")
        if self.proposal_records is not None and self.proposal_records < self.proposed:
            raise ValueError("proposal_records cannot be smaller than commitments proposed")
        return self


class RefreshMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    trigger_decisions: int = Field(ge=0)
    trigger_family_events: int = Field(ge=0)
    evidence_acquisitions: int = Field(ge=0)
    usable_evidence_acquisitions: int = Field(ge=0)
    total_cost: float = Field(ge=0.0)
    family_counts: dict[str, int]


def compute_commitment_unit_metrics(
    rows: Iterable[CommitmentUnitLedgerRow],
    *,
    eligible_actions: frozenset[str] = ELIGIBLE_COMMITMENT_ACTIONS,
    proposal_records: int | None = None,
) -> CommitmentMetrics:
    eligible = [row for row in rows if row.action_class in eligible_actions]
    proposed = len(eligible)
    executed = sum(row.executed for row in eligible)
    held = sum(row.held for row in eligible)
    escalated = sum(row.escalated for row in eligible)
    executed_stale = sum(row.executed_stale for row in eligible)
    return CommitmentMetrics(
        proposal_records=proposal_records,
        proposed=proposed,
        executed=executed,
        held=held,
        escalated=escalated,
        executed_stale=executed_stale,
        coverage=executed / proposed if proposed else 0.0,
        stale_execution_rate=(
            executed_stale / executed if executed else None
        ),
    )


def compute_proposal_record_metrics(
    rows: Iterable[CommitmentLedgerRow],
    *,
    eligible_actions: frozenset[str] = ELIGIBLE_COMMITMENT_ACTIONS,
) -> CommitmentMetrics:
    """Recompute the legacy v1 record-level metric for old artifacts only."""

    eligible = [row for row in rows if row.action_class in eligible_actions]
    proposed = len(eligible)
    executed = sum(row.executed for row in eligible)
    held = sum(row.held for row in eligible)
    escalated = sum(row.escalated for row in eligible)
    executed_stale = sum(row.executed_stale for row in eligible)
    return CommitmentMetrics(
        proposed=proposed,
        executed=executed,
        held=held,
        escalated=escalated,
        executed_stale=executed_stale,
        coverage=executed / proposed if proposed else 0.0,
        stale_execution_rate=(executed_stale / executed if executed else None),
    )


def eligible_proposal_record_count(
    rows: Iterable[CommitmentLedgerRow],
    *,
    eligible_actions: frozenset[str] = ELIGIBLE_COMMITMENT_ACTIONS,
) -> int:
    return sum(row.action_class in eligible_actions for row in rows)


# Backward-compatible public name. New callers should pass commitment-unit
# rows; old run validation calls ``compute_proposal_record_metrics`` explicitly.
compute_commitment_metrics = compute_commitment_unit_metrics


def compute_refresh_metrics(rows: Iterable[RefreshLedgerRow]) -> RefreshMetrics:
    """Aggregate one acquisition once even when several trigger families fired.

    The event contract records one REFRESH_TRIGGERED event per family. A single
    routed observation is therefore linked to several family rows when triggers
    co-fire. Acquisition sequence is the causal deduplication key for costs and
    evidence counts.
    """

    materialized = list(rows)
    decision_keys = {
        row.refresh_decision_id
        for row in materialized
    }
    acquisitions: dict[int, tuple[float | None, float | None, bool | None]] = {}
    for row in materialized:
        if row.acquisition_sequence is None:
            continue
        value = (row.cost, row.latency_s, row.usable)
        previous = acquisitions.setdefault(row.acquisition_sequence, value)
        if previous != value:
            raise ValueError(
                "rows sharing an acquisition sequence disagree on acquisition data"
            )
    family_counts: dict[str, int] = {}
    for row in materialized:
        family_counts[row.family] = family_counts.get(row.family, 0) + 1
    return RefreshMetrics(
        trigger_decisions=len(decision_keys),
        trigger_family_events=len(materialized),
        evidence_acquisitions=len(acquisitions),
        usable_evidence_acquisitions=sum(
            usable is True for _, _, usable in acquisitions.values()
        ),
        total_cost=sum(cost or 0.0 for cost, _, _ in acquisitions.values()),
        family_counts=dict(sorted(family_counts.items())),
    )
