"""Public contradiction, TRACE revision, compensation, and debt artifacts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from trace_jepa.contracts import TraceRecord, WorldModelEvidence
from trace_reference.decision import (
    CompensationRecordInput,
    ConsistencyDebtInput,
    OutcomeContradictionInput,
    ReferenceCompensationRecord,
    ReferenceConsistencyDebtRecord,
    ReferenceOutcomeContradictionEvidence,
    build_compensation_record,
    build_consistency_debt,
    build_outcome_contradiction,
)


def _hex(*parts: object) -> str:
    return hashlib.sha256("|".join(str(item) for item in parts).encode()).hexdigest()


@dataclass(frozen=True)
class ReferenceOutcomeFaultArtifacts:
    contradiction: ReferenceOutcomeContradictionEvidence
    world_evidence: WorldModelEvidence
    compensation: ReferenceCompensationRecord
    debt: ReferenceConsistencyDebtRecord


def build_reference_outcome_fault_artifacts(
    *,
    commitment_id: str,
    affected_public_subject_ids: tuple[str, ...],
    authorizing_record: TraceRecord,
    original_evidence: WorldModelEvidence,
    at_s: int,
    created_at: datetime,
) -> ReferenceOutcomeFaultArtifacts:
    """Build the controller-visible artifacts for one registered failed repair."""

    key = _hex(commitment_id, authorizing_record.record_id, authorizing_record.record_version, at_s)
    contradiction = build_outcome_contradiction(
        OutcomeContradictionInput(
            evidence_id=f"reference-outcome-contradiction-{key[:20]}",
            commitment_id=commitment_id,
            affected_public_subject_ids=affected_public_subject_ids,
            observed_at_s=at_s,
            authorizing_trace_record_id=authorizing_record.record_id,
            authorizing_trace_record_version=authorizing_record.record_version,
            reason=(
                "Authenticated public outcome evidence contradicts the route/resource premise "
                "that authorized the active reversible commitment."
            ),
        )
    )
    world_evidence = WorldModelEvidence.model_validate(
        {
            **original_evidence.model_dump(mode="json"),
            "evidence_id": f"reference-realized-outcome-{key[:20]}",
            "rollout_id": f"reference-realized-rollout-{key[20:40]}",
            "observation_window_hash": contradiction.evidence_digest,
            "reachability_evidence": {
                **original_evidence.reachability_evidence,
                "outcome_contradiction_evidence_digest": contradiction.evidence_digest,
                "outcome_observed_at_s": at_s,
            },
            "observation_age_s": 0.0,
            "decisively_contradicted": True,
            "realized_outcome": contradiction.model_dump(mode="json"),
            "prediction_residual": {
                "status": "authorization-premise-invalidated",
                "affected_public_subject_ids": affected_public_subject_ids,
            },
            "created_at": created_at,
        }
    )
    compensation = build_compensation_record(
        CompensationRecordInput(
            compensation_id=f"reference-compensation-{key[:20]}",
            invalidated_commitment_id=commitment_id,
            triggering_trace_record_id=authorizing_record.record_id,
            triggering_trace_record_version=authorizing_record.record_version + 1,
            attempted_at_s=at_s,
            status="failed",
            reason=(
                "The corrective action could not close the invalidated commitment's public "
                "affected set; mission-authority escalation is required."
            ),
        )
    )
    debt = build_consistency_debt(
        ConsistencyDebtInput(
            debt_id=f"reference-consistency-debt-{key[:20]}",
            invalidated_commitment_id=commitment_id,
            triggering_trace_record_id=authorizing_record.record_id,
            triggering_trace_record_version=authorizing_record.record_version + 1,
            failed_compensation_id=compensation.compensation_id,
            affected_public_subject_ids=affected_public_subject_ids,
            recorded_at_s=at_s,
            reason=(
                "The commitment remains active after contradictory outcome evidence and a "
                "failed compensation attempt; mission authority escalation is required."
            ),
        )
    )
    return ReferenceOutcomeFaultArtifacts(contradiction, world_evidence, compensation, debt)
