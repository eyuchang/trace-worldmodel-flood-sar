"""Exact TRACE assessment, consumption, and commitment closure for Reference."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from trace_jepa.contracts import (
    ActionInstance,
    Claim,
    Commitment,
    CommitmentDecision,
    EvaluationResult,
    TraceRecord,
    TraceStatus,
    WorldModelEvidence,
)
from trace_jepa.predictor import PredictorRequest
from trace_jepa.runtime import TraceRuntime
from trace_jepa.support import canonical_json_bytes
from trace_reference.decision.artifacts import (
    CommitmentEnvelopeInput,
    ReferenceCommitmentEnvelope,
    build_commitment_envelope,
)
from trace_reference.decision.canonical import decision_digest, verify_model_digest
from trace_reference.decision.domain import (
    BaseSelectionReceipt,
    ControllerVisibleSnapshot,
    PhysicalActionProposal,
    ReferenceTraceAssessment,
    ResponseBundle,
    ResponseBundleCatalog,
    SafeAlternativeProposal,
)
from trace_reference.domain import ReferenceEventType

from .event_store import ReferenceEventLog

ActionProposal = PhysicalActionProposal | SafeAlternativeProposal


@dataclass(frozen=True)
class ProposalAssessmentInput:
    proposal: ActionProposal
    snapshot: ControllerVisibleSnapshot
    predictor_request: PredictorRequest
    evidence: WorldModelEvidence
    claim: Claim
    at_s: int
    created_at: datetime
    lineage_key: str


@dataclass(frozen=True)
class AssessedReferenceProposal:
    assessment: ReferenceTraceAssessment
    record: TraceRecord
    evaluation: EvaluationResult


@dataclass(frozen=True)
class SelectedCommitmentInput:
    bundle: ResponseBundle
    catalog: ResponseBundleCatalog
    selection: BaseSelectionReceipt
    proposal: ActionProposal
    assessment_input: ProposalAssessmentInput
    consumer_action_id: str


@dataclass(frozen=True)
class ReferenceClosureResult:
    assessment: ReferenceTraceAssessment
    consumed_record: TraceRecord
    commitment: Commitment | None
    commitment_envelope: ReferenceCommitmentEnvelope | None


def _artifact_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def core_action_from_proposal(proposal: ActionProposal) -> ActionInstance:
    """Convert an exact Reference proposal into the shared TRACE action contract."""

    action = proposal.action
    return ActionInstance(
        action_id=action.action_id,
        action_type=action.action_class,
        actor_id=action.actor_resource_id or "reference-unassigned-resource",
        origin=action.origin_node_id,
        destination=action.destination_public_id,
        route_id=action.route_id,
        parameters={
            "required_capability": action.required_capability,
            "reference_action_digest": action.action_digest,
            "actor_crew_id": action.actor_crew_id,
            "route_plan_digest": action.route_plan_digest,
            "route_crossing_ids": action.route_crossing_ids,
            "focal_crossing_id": action.focal_crossing_id,
            "route_gauge_id": action.route_gauge_id,
            "routed_travel_s": action.routed_travel_s,
            "route_status_at_proposal": action.route_status_at_proposal,
            "deterministic_service_duration_s": action.deterministic_service_duration_s,
            "commitment_horizon_end_s": action.commitment_horizon_end_s,
            "execution_not_before_s": action.execution_not_before_s,
            "execution_not_after_s": action.execution_not_after_s,
            "reversible": proposal.reversible,
        },
    )


def _verify_predictor_binding(values: ProposalAssessmentInput) -> None:
    proposal = values.proposal
    request = values.predictor_request
    action = core_action_from_proposal(proposal)
    if request.plan.first_action != action:
        raise ValueError("Reference predictor request does not bind the proposed action")
    request_digest = _artifact_sha256(request.model_dump(mode="json"))
    evidence_digest = _artifact_sha256(values.evidence.model_dump(mode="json"))
    if proposal.predictor_request_digest != request_digest:
        raise ValueError("Reference proposal predictor-request digest is invalid")
    if proposal.predictor_evidence_digest != evidence_digest:
        raise ValueError("Reference proposal predictor-evidence digest is invalid")
    if values.evidence.observation_window_hash != request_digest:
        raise ValueError("Reference evidence does not bind the complete predictor request")
    if values.evidence.candidate_plan_id != request.plan.plan_id:
        raise ValueError("Reference evidence does not bind the predictor plan")


def _authority_present(
    proposal: ActionProposal,
    snapshot: ControllerVisibleSnapshot,
) -> bool:
    requirement = proposal.authority_requirement
    if requirement is None:
        return True
    visible_ids = {
        delivery_id
        for evidence in snapshot.authority_evidence
        if evidence.authority_id == requirement
        for delivery_id in evidence.coordination_delivery_ids
    }
    declared = set(proposal.current_authority_evidence_ids)
    if not declared.issubset(visible_ids):
        raise ValueError("Reference proposal claims authority evidence outside its snapshot")
    return bool(declared)


class ReferenceTraceGateway:
    """Narrow runtime port that makes TRACE closure unavoidable and replayable."""

    def __init__(self, runtime: TraceRuntime, event_log: ReferenceEventLog) -> None:
        self.runtime = runtime
        self.event_log = event_log

    def assess(self, values: ProposalAssessmentInput) -> AssessedReferenceProposal:
        if not verify_model_digest(values.proposal, digest_field="proposal_digest"):
            raise ValueError("Reference action proposal digest is invalid")
        if not verify_model_digest(values.snapshot, digest_field="snapshot_digest"):
            raise ValueError("Reference public snapshot digest is invalid")
        _verify_predictor_binding(values)
        record, evaluation = self.runtime.assess(
            claim=values.claim,
            evidence=values.evidence,
            action_name=values.proposal.action.action_class,
            reversible=values.proposal.reversible,
            authority_present=_authority_present(values.proposal, values.snapshot),
            repair_hint="Obtain current public evidence or choose a TRACE-authorized alternative.",
            metadata={
                "decision_id": values.snapshot.decision_id,
                "proposal_id": values.proposal.proposal_id,
                "proposal_digest": values.proposal.proposal_digest,
                "public_snapshot_digest": values.snapshot.snapshot_digest,
                "predictor_request_digest": values.proposal.predictor_request_digest,
                "predictor_evidence_digest": values.proposal.predictor_evidence_digest,
                "authority_requirement": values.proposal.authority_requirement,
                "authority_evidence_ids": values.proposal.current_authority_evidence_ids,
            },
            lineage_key=values.lineage_key,
            trigger_event_id=values.snapshot.decision_id,
            created_at=values.created_at,
        )
        assessment_body = {
            "proposal_digest": values.proposal.proposal_digest,
            "commitment_decision": evaluation.decision.value,
            "trace_record_id": record.record_id,
            "trace_record_version": record.record_version,
            "evidence_digest": values.proposal.predictor_evidence_digest,
            "failed_gates": evaluation.failed_gates,
            "missing_items": evaluation.missing_items,
            "authorization_sufficient_for_action": evaluation.decision
            in {CommitmentDecision.CLEAR, CommitmentDecision.QUALIFY},
        }
        assessment = ReferenceTraceAssessment(
            **assessment_body,
            assessment_digest=decision_digest(assessment_body),
        )
        self._append_trace_record(values.at_s, record)
        return AssessedReferenceProposal(assessment, record, evaluation)

    def commit_selected(self, values: SelectedCommitmentInput) -> ReferenceClosureResult:
        self._verify_selection(values)
        assessed = self.assess(values.assessment_input)
        consumed = self.runtime.consume(
            assessed.record,
            assessed.evaluation,
            consumer="reference-mission-controller",
            consumer_action_id=values.consumer_action_id,
            created_at=values.assessment_input.created_at,
        )
        self._append_trace_record(values.assessment_input.at_s, consumed)
        authorized = assessed.evaluation.decision == CommitmentDecision.CLEAR or (
            assessed.evaluation.decision == CommitmentDecision.QUALIFY
            and values.proposal.reversible
        )
        if not authorized:
            return ReferenceClosureResult(assessed.assessment, consumed, None, None)
        commitment_id = (
            "reference-commitment-"
            + hashlib.sha256(
                f"{values.bundle.bundle_digest}|{consumed.record_id}|{consumed.record_version}".encode()
            ).hexdigest()[:20]
        )
        commitment = self.runtime.commit(
            record=consumed,
            action=core_action_from_proposal(values.proposal),
            commitment_id=commitment_id,
            created_at=values.assessment_input.created_at,
        )
        envelope = build_commitment_envelope(
            CommitmentEnvelopeInput(
                commitment_id=commitment.commitment_id,
                authorizing_trace_record_id=consumed.record_id,
                authorizing_trace_record_version=consumed.record_version,
                selected_bundle_id=values.bundle.bundle_id,
                selected_bundle_digest=values.bundle.bundle_digest,
                selection_digest=values.selection.selection_digest,
                public_snapshot_digest=values.assessment_input.snapshot.snapshot_digest,
                committed_at_s=values.assessment_input.at_s,
            )
        )
        self.event_log.append_public_artifact(
            at_s=values.assessment_input.at_s,
            event_type=ReferenceEventType.COMMITMENT_CREATED,
            artifact_id=envelope.commitment_id,
            artifact_schema_version=envelope.schema_version,
            artifact=envelope.model_dump(mode="json"),
        )
        return ReferenceClosureResult(assessed.assessment, consumed, commitment, envelope)

    def revise_from_outcome(
        self,
        record: TraceRecord,
        evidence: WorldModelEvidence,
        *,
        at_s: int,
        created_at: datetime,
    ) -> TraceRecord:
        """Persist a realized contradiction as the next version of its TRACE claim."""

        latest = self.runtime.repository.get(record.record_id)
        if latest != record:
            raise ValueError("Reference outcome revision does not target the latest TRACE record")
        revised = self.runtime.revise_with_outcome(
            record,
            evidence,
            new_status=TraceStatus.REVISE,
            reason="Authenticated public outcome evidence invalidated the authorization premise.",
            repair="Compensate the reversible commitment or escalate unresolved consistency debt.",
            created_at=created_at,
        )
        self._append_trace_record(at_s, revised)
        return revised

    def _verify_selection(self, values: SelectedCommitmentInput) -> None:
        if not verify_model_digest(values.selection, digest_field="selection_digest"):
            raise ValueError("Reference selection receipt digest is invalid")
        if not verify_model_digest(values.bundle, digest_field="bundle_digest"):
            raise ValueError("Reference selected bundle digest is invalid")
        if not verify_model_digest(values.catalog, digest_field="catalog_digest"):
            raise ValueError("Reference response catalog digest is invalid")
        if values.selection.catalog_digest != values.catalog.catalog_digest:
            raise ValueError("Reference selection receipt names another catalog")
        if values.selection.selected_bundle_id != values.bundle.bundle_id:
            raise ValueError("Reference selection receipt names another bundle")
        catalog_member = next(
            (item for item in values.catalog.bundles if item.bundle_id == values.bundle.bundle_id),
            None,
        )
        if catalog_member != values.bundle:
            raise ValueError("Reference selected bundle is not the exact catalog member")
        if values.bundle.proposal_digest != values.proposal.proposal_digest:
            raise ValueError("Reference selected bundle names another proposal")
        if values.bundle.public_snapshot_digest != values.assessment_input.snapshot.snapshot_digest:
            raise ValueError("Reference selected bundle names another public snapshot")
        if values.bundle.reversible != values.proposal.reversible:
            raise ValueError("Reference selected bundle changes proposal reversibility")

    def _append_trace_record(self, at_s: int, record: TraceRecord) -> None:
        artifact = record.model_dump(mode="json")
        self.event_log.append_public_artifact(
            at_s=at_s,
            event_type=ReferenceEventType.TRACE_DECISION_RECORDED,
            artifact_id=f"{record.record_id}-v{record.record_version}",
            artifact_schema_version=record.schema_version,
            artifact=artifact,
        )
