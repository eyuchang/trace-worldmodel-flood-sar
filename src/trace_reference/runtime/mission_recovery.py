"""Reconstruct Reference controller state solely from durable public prefixes."""

from __future__ import annotations

import heapq
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from trace_jepa.contracts import Commitment
from trace_reference.decision import (
    AcquisitionOutcomeReceipt,
    AcquisitionRequestReceipt,
    ProviderReceipt,
    ReferenceCompensationRecord,
    ReferenceConsistencyDebtRecord,
    ReferenceOutcomeContradictionEvidence,
    ReferenceServiceOutcome,
)
from trace_reference.decision.artifacts import ReferenceCommitmentEnvelope
from trace_reference.decision.canonical import verify_model_digest
from trace_reference.decision.domain import PublicCommitmentBelief, PublicOutcomeBelief
from trace_reference.domain import (
    ReferenceEventType,
    ReferenceEventVisibility,
    ReferenceFaultApplication,
    ReferenceFaultSchedule,
    ReferenceMissionDecision,
    ReferenceMissionRestartCheckpoint,
    ReferencePublicArtifactEnvelope,
    ReferenceRawReport,
    ReferenceReportEnvelope,
    ReferenceScenarioArtifacts,
)
from trace_reference.domain.coordination import ReferenceCoordinationDelivery
from trace_reference.domain.observations import ReferenceAuthorityId
from trace_reference.reconciliation import (
    ReferenceEvidenceGraph,
    ReferenceReconciliationStep,
)

from .decision_engine import ReferenceDecisionEngine
from .event_store import ReferenceEventLog
from .mission_state import (
    EVALUATION_END_S,
    ReferenceAcquisitionContext,
    ReferenceActiveCommitment,
    ReferenceDecisionKey,
    ReferenceInputKind,
    ReferencePendingAcquisition,
    ReferencePendingContradiction,
    ReferencePendingOutcome,
    ReferenceProviderBehavior,
    ReferenceScheduledInput,
    reference_outcome_for_commitment,
    reference_runtime_profile_digest,
    reference_scenario_input_digest,
)


@dataclass(frozen=True)
class ReferenceRecoveryResult:
    graphs: dict[ReferenceAuthorityId, ReferenceEvidenceGraph]
    active: dict[str, ReferenceActiveCommitment]
    known_outcomes: list[PublicOutcomeBelief]
    decided_clusters: set[ReferenceDecisionKey]
    decisions: list[ReferenceMissionDecision]
    outcomes: list[ReferenceServiceOutcome]
    contradictions: list[ReferenceOutcomeContradictionEvidence]
    compensations: list[ReferenceCompensationRecord]
    consistency_debts: list[ReferenceConsistencyDebtRecord]
    pending: list[ReferenceScheduledInput]
    seen_delivery_ids: set[str]
    fault_applications: list[ReferenceFaultApplication]


class ReferenceMissionRecovery:
    """Verify a checkpoint and rebuild the exact next controller state."""

    def __init__(
        self,
        scenario: ReferenceScenarioArtifacts,
        engine: ReferenceDecisionEngine,
        event_log: ReferenceEventLog,
        fault_schedule: ReferenceFaultSchedule | None,
        *,
        reports: Mapping[str, ReferenceRawReport] | None = None,
        envelopes: Mapping[str, ReferenceReportEnvelope] | None = None,
    ) -> None:
        self.scenario = scenario
        self.engine = engine
        self.event_log = event_log
        self.fault_schedule = fault_schedule
        self.reports = (
            dict(reports)
            if reports is not None
            else {item.call_id: item for item in scenario.observations.raw.reports}
        )
        self.envelopes = (
            dict(envelopes)
            if envelopes is not None
            else {item.envelope_id: item for item in scenario.observations.delivery.envelopes}
        )
        self.envelope_by_call = {item.call_id: item for item in self.envelopes.values()}
        self.graphs: dict[ReferenceAuthorityId, ReferenceEvidenceGraph] = {
            cast(ReferenceAuthorityId, authority.authority_id): ReferenceEvidenceGraph(
                cast(ReferenceAuthorityId, authority.authority_id)
            )
            for authority in scenario.governance.authorities
        }
        self.decisions: list[ReferenceMissionDecision] = []
        self.steps: dict[tuple[str, str], ReferenceReconciliationStep] = {}
        self.requests: dict[str, AcquisitionRequestReceipt] = {}
        self.acquisition_outcomes: tuple[AcquisitionOutcomeReceipt, ...] = ()
        self.fault_applications: list[ReferenceFaultApplication] = []
        self.contradictions: list[ReferenceOutcomeContradictionEvidence] = []
        self.compensations: list[ReferenceCompensationRecord] = []
        self.consistency_debts: list[ReferenceConsistencyDebtRecord] = []

    def restore(self, checkpoint: ReferenceMissionRestartCheckpoint) -> ReferenceRecoveryResult:
        self._verify_checkpoint(checkpoint)
        artifacts = self._public_artifacts()
        fault_applications = self._restore_fault_applications()
        seen_deliveries = self._restore_delivery_state(artifacts, fault_applications)
        self.fault_applications = fault_applications
        self._restore_decisions_and_reconciliation(artifacts)
        self._restore_provider_state(artifacts)
        self._restore_outcome_fault_state(artifacts)
        active, known, outcomes, pending = self._restore_commitments(
            artifacts,
            checkpoint.through_s,
        )
        self._restore_pending_acquisitions(checkpoint.through_s, pending)
        decided = {
            (item.controller_authority_id, item.belief_cluster_id)
            for item in self.decisions
            if item.reassessment_of_decision_id is None
        }
        return ReferenceRecoveryResult(
            graphs=self.graphs,
            active=active,
            known_outcomes=known,
            decided_clusters=decided,
            decisions=self.decisions,
            outcomes=outcomes,
            contradictions=self.contradictions,
            compensations=self.compensations,
            consistency_debts=self.consistency_debts,
            pending=pending,
            seen_delivery_ids=seen_deliveries,
            fault_applications=fault_applications,
        )

    def _verify_checkpoint(self, checkpoint: ReferenceMissionRestartCheckpoint) -> None:
        if not verify_model_digest(checkpoint, digest_field="checkpoint_digest"):
            raise ValueError("Reference mission restart checkpoint digest is invalid")
        if checkpoint.scenario_input_digest != reference_scenario_input_digest(self.scenario):
            raise ValueError("Reference mission restart checkpoint names another scenario")
        if checkpoint.runtime_profile_digest != reference_runtime_profile_digest(
            self.fault_schedule
        ):
            raise ValueError("Reference mission restart checkpoint names another runtime profile")
        if checkpoint.event_sequence != len(self.event_log.events):
            raise ValueError("Reference mission restart checkpoint event count is invalid")
        if checkpoint.event_prefix_digest != self.event_log.prefix_digest:
            raise ValueError("Reference mission restart checkpoint event prefix is invalid")
        dependencies = self.engine.dependencies
        expected_prefixes = (
            dependencies.trace_repository.prefix_digest,
            dependencies.evidence_ledger.prefix_digest,
            dependencies.commitment_log.prefix_digest,
        )
        checkpoint_prefixes = (
            checkpoint.trace_prefix_digest,
            checkpoint.evidence_prefix_digest,
            checkpoint.commitment_prefix_digest,
        )
        if expected_prefixes != checkpoint_prefixes:
            raise ValueError("Reference mission restart checkpoint durable prefixes disagree")
        if not self.event_log.events or self.event_log.events[-1].at_s > checkpoint.through_s:
            raise ValueError("Reference mission restart checkpoint time precedes its event prefix")

    def _public_artifacts(self) -> dict[ReferenceEventType, list[dict[str, object]]]:
        restored: dict[ReferenceEventType, list[dict[str, object]]] = {}
        direct_event_types = {
            ReferenceEventType.PUBLIC_ENVIRONMENT_SAMPLE,
            ReferenceEventType.CROSSING_STATE_CHANGED,
        }
        for event in self.event_log.events:
            if event.visibility != ReferenceEventVisibility.CONTROLLER_VISIBLE:
                continue
            if event.event_type in direct_event_types:
                continue
            envelope = ReferencePublicArtifactEnvelope.model_validate_json(event.payload_json)
            value = json.loads(envelope.artifact_json)
            if not isinstance(value, dict):
                raise TypeError("Reference restored public artifact root must be an object")
            restored.setdefault(event.event_type, []).append(value)
        return restored

    def _restore_fault_applications(self) -> list[ReferenceFaultApplication]:
        applications = [
            ReferenceFaultApplication.model_validate_json(event.payload_json)
            for event in self.event_log.events
            if event.event_type == ReferenceEventType.FAULT_APPLIED
        ]
        for application in applications:
            if not verify_model_digest(application, digest_field="application_digest"):
                raise ValueError("Reference restored fault application digest is invalid")
        return applications

    @staticmethod
    def _restore_delivery_state(
        artifacts: dict[ReferenceEventType, list[dict[str, object]]],
        applications: list[ReferenceFaultApplication],
    ) -> set[str]:
        seen = {
            ReferenceCoordinationDelivery.model_validate(value["delivery"]).delivery_id
            for value in artifacts.get(
                ReferenceEventType.COORDINATION_MESSAGE_DELIVERED,
                (),
            )
        }
        for application in applications:
            if (
                application.disposition == "duplicate-effect-suppressed"
                and application.target_public_id not in seen
            ):
                raise ValueError("Reference restored duplicate suppression lacks prior effect")
        return seen

    def _restore_decisions_and_reconciliation(
        self,
        artifacts: dict[ReferenceEventType, list[dict[str, object]]],
    ) -> None:
        expected_steps = {
            (item.controller_authority_id, item.call_id): item
            for value in artifacts.get(ReferenceEventType.RECONCILIATION_UPDATED, ())
            for item in (ReferenceReconciliationStep.model_validate(value),)
        }
        for value in artifacts.get(ReferenceEventType.COORDINATION_MESSAGE_DELIVERED, ()):
            delivery = ReferenceCoordinationDelivery.model_validate(value["delivery"])
            if delivery.evidence_kind != "public-report-envelope":
                continue
            envelope = self.envelopes[delivery.evidence_id]
            report = self.reports[envelope.call_id]
            step = self.graphs[delivery.recipient_authority_id].process(
                report,
                delivered_at_s=delivery.delivered_at_s,
            )
            key = (delivery.recipient_authority_id, report.call_id)
            if expected_steps.get(key) != step:
                raise ValueError("Reference restored reconciliation disagrees with public history")
            self.steps[key] = step
        if set(self.steps) != set(expected_steps):
            raise ValueError("Reference restored reconciliation history is incomplete")
        for value in artifacts.get(ReferenceEventType.DECISION_MANIFEST_RECORDED, ()):
            self.decisions.append(ReferenceMissionDecision.model_validate(value["decision"]))

    def _restore_provider_state(
        self,
        artifacts: dict[ReferenceEventType, list[dict[str, object]]],
    ) -> None:
        self.requests = {
            item.request_id: item
            for value in artifacts.get(ReferenceEventType.ACQUISITION_REQUESTED, ())
            for item in (AcquisitionRequestReceipt.model_validate(value),)
        }
        outcomes = {
            item.provider_receipt_id: item
            for value in artifacts.get(ReferenceEventType.ACQUISITION_OUTCOME_RECORDED, ())
            for item in (AcquisitionOutcomeReceipt.model_validate(value),)
        }
        executor = self.engine.dependencies.acquisition_executor
        for request in self.requests.values():
            executor.restore_request(request)
        for value in artifacts.get(ReferenceEventType.PROVIDER_RECEIPT_RECORDED, ()):
            receipt = ProviderReceipt.model_validate(value)
            outcome, _evidence = executor.ingest(receipt)
            if outcomes.get(receipt.receipt_id) != outcome:
                raise ValueError(
                    "Reference restored provider outcome disagrees with public history"
                )
        self.acquisition_outcomes = tuple(outcomes.values())

    def _restore_outcome_fault_state(
        self,
        artifacts: dict[ReferenceEventType, list[dict[str, object]]],
    ) -> None:
        self.contradictions = [
            ReferenceOutcomeContradictionEvidence.model_validate(value)
            for value in artifacts.get(ReferenceEventType.OUTCOME_EVIDENCE_RECORDED, ())
        ]
        self.compensations = [
            ReferenceCompensationRecord.model_validate(value)
            for value in artifacts.get(ReferenceEventType.COMPENSATION_RECORDED, ())
        ]
        self.consistency_debts = [
            ReferenceConsistencyDebtRecord.model_validate(value)
            for value in artifacts.get(ReferenceEventType.CONSISTENCY_DEBT_RECORDED, ())
        ]
        for item, digest_field in (
            *((item, "evidence_digest") for item in self.contradictions),
            *((item, "compensation_digest") for item in self.compensations),
            *((item, "debt_digest") for item in self.consistency_debts),
        ):
            if not verify_model_digest(item, digest_field=digest_field):
                raise ValueError("Reference restored outcome-fault artifact digest is invalid")
        compensation_by_id = {item.compensation_id: item for item in self.compensations}
        if len(compensation_by_id) != len(self.compensations):
            raise ValueError("Reference restored compensation identity is duplicated")
        if len(self.contradictions) != len(self.compensations) or len(self.compensations) != len(
            self.consistency_debts
        ):
            raise ValueError("Reference restored outcome-fault closure is incomplete")
        for debt in self.consistency_debts:
            compensation = compensation_by_id.get(debt.failed_compensation_id)
            if compensation is None or compensation.invalidated_commitment_id != (
                debt.invalidated_commitment_id
            ):
                raise ValueError("Reference restored debt names another compensation")

    def _restore_commitments(
        self,
        artifacts: dict[ReferenceEventType, list[dict[str, object]]],
        through_s: int,
    ) -> tuple[
        dict[str, ReferenceActiveCommitment],
        list[PublicOutcomeBelief],
        list[ReferenceServiceOutcome],
        list[ReferenceScheduledInput],
    ]:
        envelopes = {
            item.commitment_id: item
            for value in artifacts.get(ReferenceEventType.COMMITMENT_CREATED, ())
            for item in (ReferenceCommitmentEnvelope.model_validate(value),)
        }
        outcomes = {
            item.commitment_id: item
            for value in artifacts.get(ReferenceEventType.OUTCOME_RECORDED, ())
            for item in (ReferenceServiceOutcome.model_validate(value),)
        }
        known = self._known_outcome_beliefs(outcomes)
        decisions = {
            item.commitment_id: item for item in self.decisions if item.commitment_id is not None
        }
        active: dict[str, ReferenceActiveCommitment] = {}
        pending: list[ReferenceScheduledInput] = []
        commitments = self.engine.dependencies.commitment_log.all()
        partial_fault_id, partial_target_id = self._commitment_fault_target(
            commitments,
            "partial-service-outcome",
        )
        contradiction_fault_id, contradiction_target_id = self._commitment_fault_target(
            commitments,
            "contradictory-outcome-evidence",
        )
        compensation_fault_id = (
            None
            if self.fault_schedule is None
            else next(
                item.fault_id
                for item in self.fault_schedule.triggers
                if item.family == "failed-compensation"
            )
        )
        contradicted_ids = {item.commitment_id for item in self.contradictions}
        for commitment in commitments:
            envelope = envelopes.get(commitment.commitment_id)
            decision = decisions.get(commitment.commitment_id)
            if envelope is None or decision is None or decision.selected_resource_id is None:
                raise ValueError("Reference restored commitment lacks its public closure")
            if commitment.commitment_id in outcomes:
                continue
            parameters = commitment.action.parameters
            completion_s = int(parameters["commitment_horizon_end_s"])
            duration_s = int(parameters["deterministic_service_duration_s"])
            if completion_s - duration_s < envelope.committed_at_s:
                raise ValueError("Reference restored commitment has an invalid service schedule")
            partial = (
                commitment.commitment_id == partial_target_id and completion_s <= EVALUATION_END_S
            )
            outcome = reference_outcome_for_commitment(
                commitment,
                completion_s,
                partial=partial,
            )
            belief = PublicCommitmentBelief(
                commitment_id=commitment.commitment_id,
                resource_id=decision.selected_resource_id,
                action_class=commitment.action.action_type,
                active_from_s=envelope.committed_at_s,
                active_until_s=completion_s,
                authorizing_trace_record_id=commitment.authorizing_record_id,
                authorizing_trace_record_version=commitment.authorizing_record_version,
            )
            if belief.resource_id in active:
                raise ValueError("Reference restored state double-commits a physical resource")
            if min(completion_s, EVALUATION_END_S) <= through_s:
                raise ValueError("Reference restored active commitment is missing its outcome")
            active[belief.resource_id] = ReferenceActiveCommitment(belief, outcome)
            heapq.heappush(
                pending,
                ReferenceScheduledInput(
                    min(completion_s, EVALUATION_END_S),
                    10,
                    outcome.outcome_id,
                    ReferenceInputKind.OUTCOME,
                    ReferencePendingOutcome(
                        outcome,
                        belief.resource_id,
                        partial_fault_id if partial else None,
                    ),
                ),
            )
            if commitment.commitment_id == contradiction_target_id and (
                commitment.commitment_id not in contradicted_ids
            ):
                self._push_pending_contradiction(
                    pending,
                    commitment=commitment,
                    belief=belief,
                    through_s=through_s,
                    contradiction_fault_id=contradiction_fault_id,
                    compensation_fault_id=compensation_fault_id,
                )
        self._validate_restored_outcome_fault_closure(outcomes, contradicted_ids)
        return active, known, list(outcomes.values()), pending

    def _known_outcome_beliefs(
        self,
        outcomes: dict[str, ReferenceServiceOutcome],
    ) -> list[PublicOutcomeBelief]:
        known = [
            PublicOutcomeBelief(
                outcome_id=item.outcome_id,
                commitment_id=item.commitment_id,
                status=item.status,
                observed_at_s=item.observed_at_s,
            )
            for item in outcomes.values()
        ]
        known.extend(
            PublicOutcomeBelief(
                outcome_id=item.evidence_id,
                commitment_id=item.commitment_id,
                status="authorization-premise-contradicted",
                observed_at_s=item.observed_at_s,
            )
            for item in self.contradictions
        )
        return known

    @staticmethod
    def _push_pending_contradiction(
        pending: list[ReferenceScheduledInput],
        *,
        commitment: Commitment,
        belief: PublicCommitmentBelief,
        through_s: int,
        contradiction_fault_id: str | None,
        compensation_fault_id: str | None,
    ) -> None:
        contradiction_s = int(commitment.action.parameters["execution_not_after_s"])
        if contradiction_s <= through_s:
            raise ValueError("Reference restored commitment is missing its contradiction")
        if contradiction_fault_id is None or compensation_fault_id is None:
            raise ValueError("Reference restored contradiction lost its registered faults")
        destination = commitment.action.destination
        if destination is None:
            raise ValueError("Reference restored contradiction lacks its public affected subject")
        heapq.heappush(
            pending,
            ReferenceScheduledInput(
                contradiction_s,
                9,
                f"reference-contradiction-{commitment.commitment_id}",
                ReferenceInputKind.OUTCOME_CONTRADICTION,
                ReferencePendingContradiction(
                    commitment_id=commitment.commitment_id,
                    resource_id=belief.resource_id,
                    affected_public_subject_ids=(destination,),
                    contradiction_fault_id=contradiction_fault_id,
                    compensation_fault_id=compensation_fault_id,
                ),
            ),
        )

    def _validate_restored_outcome_fault_closure(
        self,
        outcomes: dict[str, ReferenceServiceOutcome],
        contradicted_ids: set[str],
    ) -> None:
        partial_outcomes = {
            item.commitment_id
            for item in outcomes.values()
            if item.status == "partial_service_within_window"
        }
        applied_partial = {
            item.target_public_id
            for item in self.fault_applications
            if item.family == "partial-service-outcome"
        }
        if partial_outcomes != applied_partial:
            raise ValueError("Reference restored partial service fault closure is incomplete")
        censored = tuple(
            sorted(
                item.commitment_id
                for item in outcomes.values()
                if item.status == "active_at_scenario_censoring"
            )
        )
        applied_censoring = {
            item.target_public_id
            for item in self.fault_applications
            if item.family == "completion-after-scenario-censoring"
        }
        expected_censoring = set(censored[:1]) if self.fault_schedule is not None else set()
        if applied_censoring != expected_censoring:
            raise ValueError("Reference restored censoring fault closure is incomplete")
        applied_contradictions = {
            item.target_public_id
            for item in self.fault_applications
            if item.family == "contradictory-outcome-evidence"
        }
        applied_compensations = {
            item.target_public_id
            for item in self.fault_applications
            if item.family == "failed-compensation"
        }
        if applied_contradictions != contradicted_ids:
            raise ValueError("Reference restored contradiction fault closure is incomplete")
        if applied_compensations != {item.compensation_id for item in self.compensations}:
            raise ValueError("Reference restored compensation fault closure is incomplete")

    def _commitment_fault_target(
        self,
        commitments: list[Commitment],
        family: str,
    ) -> tuple[str | None, str | None]:
        if self.fault_schedule is None:
            return None, None
        trigger = next(item for item in self.fault_schedule.triggers if item.family == family)
        eligible = tuple(
            sorted(
                (
                    item
                    for item in commitments
                    if bool(item.action.parameters.get("reversible"))
                    and int(item.action.parameters["execution_not_before_s"]) >= trigger.anchor_s
                ),
                key=lambda item: (
                    int(item.action.parameters["execution_not_before_s"]),
                    item.commitment_id,
                ),
            )
        )
        index = trigger.ordinal - 1
        if index >= len(eligible):
            return trigger.fault_id, None
        return trigger.fault_id, eligible[index].commitment_id

    def _restore_pending_acquisitions(
        self,
        through_s: int,
        pending: list[ReferenceScheduledInput],
    ) -> None:
        decisions = {
            item.acquisition_request_id: item
            for item in self.decisions
            if item.acquisition_request_id is not None
        }
        outcomes_by_request: dict[str, list[AcquisitionOutcomeReceipt]] = {}
        for outcome in self.acquisition_outcomes:
            outcomes_by_request.setdefault(outcome.request_id, []).append(outcome)
        silent_application = next(
            (
                item
                for item in self.fault_applications
                if item.family == "silent-provider-success-after-timeout"
            ),
            None,
        )
        if (
            silent_application is not None
            and silent_application.target_public_id not in self.requests
        ):
            raise ValueError("Reference restored provider fault names an absent request")
        for request_id, request in self.requests.items():
            decision = decisions.get(request_id)
            if decision is None:
                raise ValueError("Reference restored acquisition lacks its public decision")
            context = self._acquisition_context(request, decision)
            outcomes = outcomes_by_request.get(request_id, [])
            if silent_application is not None and request_id == silent_application.target_public_id:
                self._restore_silent_provider(
                    context,
                    outcomes,
                    through_s,
                    pending,
                    silent_application.fault_id,
                )
                continue
            if outcomes:
                continue
            if request.expected_delivery_s <= through_s:
                raise ValueError("Reference restored acquisition is missing its provider outcome")
            self._push_recovered_acquisition(
                pending,
                at_s=request.expected_delivery_s,
                context=context,
                behavior="nominal-success",
                fault_id=None,
            )

    def _acquisition_context(
        self,
        request: AcquisitionRequestReceipt,
        decision: ReferenceMissionDecision,
    ) -> ReferenceAcquisitionContext:
        envelope = self.envelope_by_call[request.target_call_id]
        return ReferenceAcquisitionContext(
            request,
            self.reports[request.target_call_id],
            envelope,
            self.steps[(decision.controller_authority_id, request.target_call_id)],
            decision,
            decision.decided_at_s - envelope.delivered_at_s,
        )

    def _restore_silent_provider(
        self,
        context: ReferenceAcquisitionContext,
        outcomes: list[AcquisitionOutcomeReceipt],
        through_s: int,
        pending: list[ReferenceScheduledInput],
        fault_id: str,
    ) -> None:
        if self.fault_schedule is None:
            raise ValueError("Reference restored provider fault lacks its schedule")
        trigger = next(item for item in self.fault_schedule.triggers if item.fault_id == fault_id)
        timeout_s = context.request.expected_delivery_s
        success_s = timeout_s + trigger.delivery_offset_s
        if any(
            item.outcome_status not in {"provider-timeout", "evidence-accepted"}
            for item in outcomes
        ):
            raise ValueError("Reference restored silent provider has an unexpected outcome")
        timeout_count = sum(item.outcome_status == "provider-timeout" for item in outcomes)
        accepted_count = sum(item.outcome_status == "evidence-accepted" for item in outcomes)
        if timeout_count > 1 or accepted_count > 1:
            raise ValueError("Reference restored silent-provider outcomes are duplicated")
        if accepted_count:
            if not timeout_count:
                raise ValueError("Reference silent provider success lacks its prior client timeout")
            return
        if timeout_s <= through_s and not timeout_count:
            raise ValueError("Reference restored silent provider is missing its client timeout")
        if timeout_s > through_s:
            self._push_recovered_acquisition(
                pending,
                at_s=timeout_s,
                context=context,
                behavior="client-timeout",
                fault_id=fault_id,
            )
        if success_s <= through_s:
            raise ValueError("Reference restored silent provider is missing its late success")
        self._push_recovered_acquisition(
            pending,
            at_s=success_s,
            context=context,
            behavior="late-success",
            fault_id=fault_id,
        )

    @staticmethod
    def _push_recovered_acquisition(
        pending: list[ReferenceScheduledInput],
        *,
        at_s: int,
        context: ReferenceAcquisitionContext,
        behavior: ReferenceProviderBehavior,
        fault_id: str | None,
    ) -> None:
        heapq.heappush(
            pending,
            ReferenceScheduledInput(
                at_s,
                10,
                f"{context.request.request_id}-{behavior}",
                ReferenceInputKind.PROVIDER,
                ReferencePendingAcquisition(
                    context,
                    behavior,
                    fault_id,
                ),
            ),
        )
