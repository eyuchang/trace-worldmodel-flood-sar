from __future__ import annotations

from trace_jepa.contracts import (
    ActionInstance,
    Claim,
    Commitment,
    ConsumerAction,
    EvaluationResult,
    TraceRecord,
    TraceStatus,
    WorldModelEvidence,
)
from trace_jepa.runtime.policy import PolicyEngine
from trace_jepa.runtime.storage import CommitmentLog, EvidenceLedger, TraceRepository


class TraceRuntime:
    def __init__(
        self,
        *,
        repository: TraceRepository,
        ledger: EvidenceLedger,
        commitments: CommitmentLog,
        policy: PolicyEngine,
    ):
        self.repository = repository
        self.ledger = ledger
        self.commitments = commitments
        self.policy = policy

    def assess(
        self,
        *,
        claim: Claim,
        evidence: WorldModelEvidence,
        action_name: str,
        reversible: bool,
        authority_present: bool,
        repair_hint: str | None = None,
        metadata: dict | None = None,
    ) -> tuple[TraceRecord, EvaluationResult]:
        evidence_ref = self.ledger.put(evidence)
        evaluation = self.policy.evaluate(
            claim,
            evidence,
            action_name=action_name,
            reversible=reversible,
            authority_present=authority_present,
            repair_hint=repair_hint,
        )
        record = TraceRecord(
            policy_version=self.policy.config.policy_version,
            claim=claim,
            evidence_refs=(evidence_ref,),
            final_status=evaluation.status,
            failed_gates=evaluation.failed_gates,
            missing_items=evaluation.missing_items,
            repair=evaluation.repair,
            metadata=metadata or {},
        )
        self.repository.write(record)
        return record, evaluation

    def consume(
        self,
        record: TraceRecord,
        evaluation: EvaluationResult,
        *,
        consumer: str = "mission-controller",
    ) -> TraceRecord:
        action = ConsumerAction(
            consumer=consumer,
            decision=evaluation.decision,
            consumer_policy_version=self.policy.config.policy_version,
            record_id=record.record_id,
            record_version=record.record_version,
            reason=evaluation.reason,
        )
        consumed = record.model_copy(
            update={
                "record_version": record.record_version + 1,
                "consumer_actions": record.consumer_actions + (action,),
                "supersedes_record_id": record.record_id,
                "supersedes_record_version": record.record_version,
            }
        )
        self.repository.write(consumed)
        return consumed

    def revise_with_outcome(
        self,
        record: TraceRecord,
        evidence: WorldModelEvidence,
        *,
        new_status: TraceStatus,
        reason: str,
        repair: str,
    ) -> TraceRecord:
        evidence_ref = self.ledger.put(evidence)
        revised = record.model_copy(
            update={
                "record_version": record.record_version + 1,
                "evidence_refs": record.evidence_refs + (evidence_ref,),
                "final_status": new_status,
                "failed_gates": record.failed_gates + ("realized_contradiction",),
                "repair": repair,
                "supersedes_record_id": record.record_id,
                "supersedes_record_version": record.record_version,
                "metadata": {**record.metadata, "revision_reason": reason},
            }
        )
        self.repository.write(revised)
        return revised

    def commit(
        self,
        *,
        record: TraceRecord,
        action: ActionInstance,
    ) -> Commitment:
        commitment = Commitment(
            action=action,
            authorizing_record_id=record.record_id,
            authorizing_record_version=record.record_version,
            consumer_policy_version=self.policy.config.policy_version,
        )
        self.commitments.append(commitment, record)
        return commitment
