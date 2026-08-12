"""Reconstruct Reference controller state solely from durable public prefixes."""

from __future__ import annotations

import heapq
import json
from dataclasses import dataclass
from typing import cast

from trace_reference.decision import (
    AcquisitionOutcomeReceipt,
    AcquisitionRequestReceipt,
    ProviderReceipt,
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
    ) -> None:
        self.scenario = scenario
        self.engine = engine
        self.event_log = event_log
        self.fault_schedule = fault_schedule
        self.reports = {item.call_id: item for item in scenario.observations.raw.reports}
        self.envelopes = {
            item.envelope_id: item for item in scenario.observations.delivery.envelopes
        }
        self.envelope_by_call = {
            item.call_id: item for item in scenario.observations.delivery.envelopes
        }
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

    def restore(self, checkpoint: ReferenceMissionRestartCheckpoint) -> ReferenceRecoveryResult:
        self._verify_checkpoint(checkpoint)
        artifacts = self._public_artifacts()
        fault_applications = self._restore_fault_applications()
        seen_deliveries = self._restore_delivery_state(artifacts, fault_applications)
        self.fault_applications = fault_applications
        self._restore_decisions_and_reconciliation(artifacts)
        self._restore_provider_state(artifacts)
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
        known = [
            PublicOutcomeBelief(
                outcome_id=item.outcome_id,
                commitment_id=item.commitment_id,
                status=item.status,
                observed_at_s=(
                    item.observed_completion_s
                    if item.observed_completion_s is not None
                    else EVALUATION_END_S
                ),
            )
            for item in outcomes.values()
        ]
        decisions = {
            item.commitment_id: item for item in self.decisions if item.commitment_id is not None
        }
        active: dict[str, ReferenceActiveCommitment] = {}
        pending: list[ReferenceScheduledInput] = []
        for commitment in self.engine.dependencies.commitment_log.all():
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
            outcome = reference_outcome_for_commitment(commitment, completion_s)
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
                    ReferencePendingOutcome(outcome, belief.resource_id),
                ),
            )
        return active, known, list(outcomes.values()), pending

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
