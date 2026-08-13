"""Lazy chronological orchestration for the non-LEAP Reference mission."""

from __future__ import annotations

import heapq
import json
from collections.abc import Iterable, Iterator
from datetime import timedelta
from typing import Literal, cast

from trace_reference.decision import (
    AcquisitionOutcomeReceipt,
    AcquisitionRequestReceipt,
    ReferenceCompensationRecord,
    ReferenceConsistencyDebtRecord,
    ReferenceOutcomeContradictionEvidence,
    ReferencePhysicalEvidence,
    ReferenceServiceOutcome,
    ReferenceServiceOutcomeStatus,
    ServiceOutcomeInput,
    build_service_outcome,
)
from trace_reference.decision.canonical import decision_digest
from trace_reference.decision.domain import PublicCommitmentBelief, PublicOutcomeBelief
from trace_reference.domain import (
    ReferenceCoordinationFaultAttempt,
    ReferenceDecisionExecution,
    ReferenceEvent,
    ReferenceEventType,
    ReferenceFaultApplication,
    ReferenceFaultSchedule,
    ReferenceMissionDecision,
    ReferenceMissionRestartCheckpoint,
    ReferenceRawReport,
    ReferenceReportEnvelope,
    ReferenceResourceTelemetry,
    ReferenceScenarioArtifacts,
)
from trace_reference.domain.coordination import (
    ReferenceCoordinationDelivery,
    ReferenceResourceActivationEvent,
)
from trace_reference.domain.observations import ReferenceAuthorityId
from trace_reference.reconciliation import (
    ReferenceEvidenceGraph,
    ReferenceReconciliationStep,
)

from .acquisition_provider import (
    ReferenceRouteProviderInput,
    build_reference_route_provider_receipt,
    build_reference_route_provider_timeout,
)
from .decision_engine import ReferenceDecisionEngine, ReferenceDecisionInput
from .event_store import ReferenceEventLog, verify_reference_event
from .fault_overlay import (
    ReferenceCoordinationOverlay,
    build_reference_coordination_overlay,
    build_reference_fault_application,
    build_reference_target_fault_application,
)
from .mission_recovery import ReferenceMissionRecovery
from .mission_state import (
    EVALUATION_END_S,
    ReferenceAcquisitionContext,
    ReferenceActiveCommitment,
    ReferenceDecisionKey,
    ReferenceInputKind,
    ReferenceMissionRun,
    ReferencePendingAcquisition,
    ReferencePendingContradiction,
    ReferencePendingOutcome,
    ReferenceProviderBehavior,
    ReferenceScheduledInput,
    reference_content_digest,
    reference_runtime_profile_digest,
    reference_scenario_input_digest,
)
from .outcome_faults import build_reference_outcome_fault_artifacts
from .report_fault_overlay import build_reference_report_fault_overlay


def _physical_inputs(events: Iterable[ReferenceEvent]) -> Iterator[ReferenceScheduledInput]:
    for event in events:
        yield ReferenceScheduledInput(
            event.at_s,
            0,
            f"physical-{event.sequence:08d}",
            ReferenceInputKind.PHYSICAL,
            event,
        )


def _report_inputs(
    envelopes: Iterable[ReferenceReportEnvelope],
) -> Iterator[ReferenceScheduledInput]:
    for envelope in envelopes:
        yield ReferenceScheduledInput(
            envelope.delivered_at_s,
            20,
            envelope.envelope_id,
            ReferenceInputKind.REPORT,
            envelope,
        )


def _telemetry_inputs(
    telemetry: Iterable[ReferenceResourceTelemetry],
) -> Iterator[ReferenceScheduledInput]:
    for item in telemetry:
        yield ReferenceScheduledInput(
            item.delivered_at_s,
            21,
            item.telemetry_id,
            ReferenceInputKind.TELEMETRY,
            item,
        )


def _activation_inputs(
    events: Iterable[ReferenceResourceActivationEvent],
) -> Iterator[ReferenceScheduledInput]:
    for event in events:
        yield ReferenceScheduledInput(
            event.delivered_at_s,
            15,
            event.event_id,
            ReferenceInputKind.ACTIVATION,
            event,
        )


def _coordination_inputs(
    overlay: ReferenceCoordinationOverlay,
) -> Iterator[ReferenceScheduledInput]:
    for attempt in overlay.attempts:
        yield ReferenceScheduledInput(
            attempt.at_s,
            30,
            attempt.attempt_id,
            ReferenceInputKind.COORDINATION,
            attempt,
        )


class ReferenceMissionRuntime:
    """Execute the 96-hour base Reference path without LEAP behavior."""

    def __init__(
        self,
        scenario: ReferenceScenarioArtifacts,
        decision_engine: ReferenceDecisionEngine,
        *,
        fault_schedule: ReferenceFaultSchedule | None = None,
        restart_checkpoint: ReferenceMissionRestartCheckpoint | None = None,
    ) -> None:
        if decision_engine.dependencies.scenario is not scenario:
            raise ValueError("Reference decision engine must bind the exact scenario object")
        if scenario.config.timeline.evaluation_end_s != EVALUATION_END_S:
            raise ValueError("Reference runtime requires the registered 96-hour horizon")
        if fault_schedule is not None and (
            fault_schedule.profile_id != scenario.config.fault_profiles.integration_acceptance
        ):
            raise ValueError("Reference fault schedule does not bind the configured profile")
        self.scenario = scenario
        self.engine = decision_engine
        self._fault_schedule = fault_schedule
        self._fault_overlay = build_reference_coordination_overlay(scenario, fault_schedule)
        self._report_fault_overlay = build_reference_report_fault_overlay(scenario, fault_schedule)
        self.event_log: ReferenceEventLog = decision_engine.dependencies.event_log
        runtime_reports = (
            *scenario.observations.raw.reports,
            *(item.report for item in self._report_fault_overlay.reports),
        )
        runtime_envelopes = (
            *scenario.observations.delivery.envelopes,
            *(item.envelope for item in self._report_fault_overlay.reports),
        )
        self._runtime_envelopes = tuple(
            sorted(runtime_envelopes, key=lambda item: (item.delivered_at_s, item.envelope_id))
        )
        self._reports = {item.call_id: item for item in runtime_reports}
        self._envelopes = {item.envelope_id: item for item in self._runtime_envelopes}
        self._envelope_by_call = {item.call_id: item for item in self._runtime_envelopes}
        self._injected_fault_by_envelope = {
            item.envelope.envelope_id: item.fault_id for item in self._report_fault_overlay.reports
        }
        self._telemetry = {item.telemetry_id: item for item in scenario.resources.public.telemetry}
        self._graphs: dict[ReferenceAuthorityId, ReferenceEvidenceGraph] = {
            cast(ReferenceAuthorityId, authority.authority_id): ReferenceEvidenceGraph(
                cast(ReferenceAuthorityId, authority.authority_id)
            )
            for authority in scenario.governance.authorities
        }
        self._active: dict[str, ReferenceActiveCommitment] = {}
        self._known_outcomes: list[PublicOutcomeBelief] = []
        self._decided_clusters: set[ReferenceDecisionKey] = set()
        self._decisions: list[ReferenceMissionDecision] = []
        self._outcomes: list[ReferenceServiceOutcome] = []
        self._contradictions: list[ReferenceOutcomeContradictionEvidence] = []
        self._compensations: list[ReferenceCompensationRecord] = []
        self._consistency_debts: list[ReferenceConsistencyDebtRecord] = []
        self._fault_applications: list[ReferenceFaultApplication] = []
        self._seen_delivery_ids: set[str] = set()
        self._pending_outcomes: list[ReferenceScheduledInput] = []
        self._run_started = False
        self._resume_after_s: int | None = None
        self._last_run_through_s: int | None = None
        self._validate_inputs(require_empty=restart_checkpoint is None)
        if restart_checkpoint is not None:
            self._restore(restart_checkpoint)

    def run(self, *, through_s: int = EVALUATION_END_S) -> ReferenceMissionRun:
        """Run once from burn-in through an inclusive characterization boundary."""

        if not -172_800 <= through_s <= EVALUATION_END_S:
            raise ValueError("Reference runtime boundary is outside the scenario window")
        if self._run_started:
            raise RuntimeError("Reference mission runtime instances are single-use")
        if self._resume_after_s is not None and through_s <= self._resume_after_s:
            raise ValueError("Reference resumed runtime must advance beyond its checkpoint")
        self._run_started = True
        external = iter(
            heapq.merge(
                _physical_inputs(self.scenario.physical.events),
                _activation_inputs(self.scenario.coordination.activations.events),
                _report_inputs(self._runtime_envelopes),
                _telemetry_inputs(self.scenario.resources.public.telemetry),
                _coordination_inputs(self._fault_overlay),
                _coordination_inputs(self._report_fault_overlay.coordination),
            )
        )
        if self._resume_after_s is not None:
            external = (item for item in external if item.at_s > self._resume_after_s)
        next_external = next(external, None)
        while next_external is not None or self._pending_outcomes:
            if next_external is None or (
                self._pending_outcomes and self._pending_outcomes[0] < next_external
            ):
                scheduled = heapq.heappop(self._pending_outcomes)
            else:
                scheduled = next_external
                next_external = next(external, None)
            if scheduled.at_s > through_s:
                break
            self._process(scheduled)
        self._last_run_through_s = through_s
        return self._result(through_s)

    def checkpoint(
        self,
        *,
        register_crash: bool = False,
    ) -> ReferenceMissionRestartCheckpoint:
        """Bind an executed prefix to every durable store needed for recovery."""

        if self._last_run_through_s is None or not self.event_log.events:
            raise RuntimeError("Reference mission must execute before checkpointing")
        if register_crash:
            self._record_registered_crash()
        dependencies = self.engine.dependencies
        body = {
            "schema_version": "delta-reference-mission-restart-checkpoint-v2",
            "through_s": self._last_run_through_s,
            "scenario_input_digest": reference_scenario_input_digest(self.scenario),
            "runtime_profile_digest": reference_runtime_profile_digest(self._fault_schedule),
            "event_sequence": len(self.event_log.events),
            "event_prefix_digest": self.event_log.prefix_digest,
            "trace_prefix_digest": dependencies.trace_repository.prefix_digest,
            "evidence_prefix_digest": dependencies.evidence_ledger.prefix_digest,
            "commitment_prefix_digest": dependencies.commitment_log.prefix_digest,
        }
        return ReferenceMissionRestartCheckpoint(
            **body,
            checkpoint_digest=decision_digest(body),
        )

    def _record_registered_crash(self) -> None:
        if self._fault_schedule is None or self._last_run_through_s is None:
            raise RuntimeError("Reference registered crash requires the faulted runtime")
        trigger = next(
            item
            for item in self._fault_schedule.triggers
            if item.family == "controller-crash-restart"
        )
        if self._last_run_through_s != trigger.anchor_s:
            raise ValueError("Reference registered crash checkpoint is not at its anchor")
        if any(item.fault_id == trigger.fault_id for item in self._fault_applications):
            raise RuntimeError("Reference registered crash was already recorded")
        self._record_target_fault_application(
            fault_id=trigger.fault_id,
            target_public_id=f"runtime-prefix-{self.event_log.prefix_digest[:20]}",
            applied_at_s=trigger.anchor_s,
            reason=(
                "The registered controller process boundary persisted this exact durable prefix "
                "for restart-equivalence evaluation."
            ),
        )

    def _process(self, scheduled: ReferenceScheduledInput) -> None:
        if scheduled.kind == ReferenceInputKind.PHYSICAL:
            self._append_physical(scheduled.payload)
        elif scheduled.kind == ReferenceInputKind.PROVIDER:
            self._complete_acquisition(scheduled.payload, scheduled.at_s)
        elif scheduled.kind == ReferenceInputKind.OUTCOME:
            self._record_outcome(scheduled.payload, scheduled.at_s)
        elif scheduled.kind == ReferenceInputKind.OUTCOME_CONTRADICTION:
            self._record_outcome_contradiction(scheduled.payload, scheduled.at_s)
        elif scheduled.kind == ReferenceInputKind.REPORT:
            self._record_report(scheduled.payload)
        elif scheduled.kind == ReferenceInputKind.TELEMETRY:
            self._record_telemetry(scheduled.payload)
        elif scheduled.kind == ReferenceInputKind.ACTIVATION:
            self._record_activation(scheduled.payload)
        else:
            self._deliver_coordination(scheduled.payload)

    def _append_physical(self, value: object) -> None:
        if not isinstance(value, ReferenceEvent):
            raise TypeError("Reference physical queue payload has the wrong type")
        payload = json.loads(value.payload_json)
        if not isinstance(payload, dict):
            raise TypeError("Reference physical event payload root must be an object")
        self.event_log.append(
            at_s=value.at_s,
            event_type=value.event_type,
            visibility=value.visibility,
            payload=payload,
        )

    def _record_report(self, value: object) -> None:
        if not isinstance(value, ReferenceReportEnvelope):
            raise TypeError("Reference report queue payload has the wrong type")
        report = self._reports[value.call_id]
        from trace_reference.generation import verify_reference_envelope

        if not verify_reference_envelope(report, value):
            raise ValueError("Reference report envelope authentication failed before delivery")
        fault_id = self._injected_fault_by_envelope.get(value.envelope_id)
        if fault_id is not None:
            self._record_target_fault_application(
                fault_id=fault_id,
                target_public_id=value.envelope_id,
                applied_at_s=value.delivered_at_s,
                reason=(
                    "The registered runtime-only report overlay delivered this authenticated "
                    "public evidence without changing the common raw-observation artifact."
                ),
            )
        self.event_log.append_public_artifact(
            at_s=value.delivered_at_s,
            event_type=ReferenceEventType.CALL_DELIVERED,
            artifact_id=value.envelope_id,
            artifact_schema_version="delta-reference-delivered-report-v1",
            artifact={
                "schema_version": "delta-reference-delivered-report-v1",
                "raw_report": report.model_dump(mode="json"),
                "delivery_envelope": value.model_dump(mode="json"),
            },
        )

    def _record_telemetry(self, value: object) -> None:
        if not isinstance(value, ReferenceResourceTelemetry):
            raise TypeError("Reference telemetry queue payload has the wrong type")
        self.event_log.append_public_artifact(
            at_s=value.delivered_at_s,
            event_type=ReferenceEventType.RESOURCE_STATE_CHANGED,
            artifact_id=value.telemetry_id,
            artifact_schema_version="delta-reference-resource-telemetry-item-v1",
            artifact={
                "schema_version": "delta-reference-resource-telemetry-item-v1",
                "telemetry": value.model_dump(mode="json"),
            },
        )

    def _record_activation(self, value: object) -> None:
        if not isinstance(value, ReferenceResourceActivationEvent):
            raise TypeError("Reference activation queue payload has the wrong type")
        self.event_log.append_public_artifact(
            at_s=value.delivered_at_s,
            event_type=ReferenceEventType.RESOURCE_ACTIVATION_UPDATED,
            artifact_id=value.event_id,
            artifact_schema_version=value.schema_version,
            artifact=value.model_dump(mode="json"),
        )

    def _deliver_coordination(self, value: object) -> None:
        if not isinstance(value, ReferenceCoordinationFaultAttempt):
            raise TypeError("Reference coordination queue payload has the wrong type")
        delivery = value.delivery
        if value.behavior == "stale-key-reject":
            self._record_fault_application(
                value,
                disposition="stale-key-rejected",
                reason=(
                    "The deterministic fixture key rotation rejected this stale "
                    "coordination acknowledgement before controller delivery."
                ),
            )
            return
        if delivery.delivery_id in self._seen_delivery_ids:
            self._record_fault_application(
                value,
                disposition="duplicate-effect-suppressed",
                reason=(
                    "The durable inbox recognized the previously applied delivery ID "
                    "and suppressed a second controller-visible effect."
                ),
            )
            return
        if value.behavior == "reordered-delivery":
            self._record_fault_application(
                value,
                disposition="applied",
                reason=(
                    "The registered transport overlay delayed this delivery while "
                    "leaving its source evidence content unchanged."
                ),
            )
        source = self._coordination_source(delivery)
        if (
            reference_content_digest(source.model_dump(mode="json"))
            != delivery.source_content_digest
        ):
            raise ValueError("Reference coordination delivery source digest is invalid")
        self.event_log.append_public_artifact(
            at_s=value.at_s,
            event_type=ReferenceEventType.COORDINATION_MESSAGE_DELIVERED,
            artifact_id=delivery.delivery_id,
            artifact_schema_version="delta-reference-coordination-delivery-v1",
            artifact={
                "schema_version": "delta-reference-coordination-delivery-v1",
                "delivery": delivery.model_dump(mode="json"),
            },
        )
        self._seen_delivery_ids.add(delivery.delivery_id)
        if delivery.evidence_kind != "public-report-envelope":
            return
        envelope = self._envelopes[delivery.evidence_id]
        report = self._reports[envelope.call_id]
        graph = self._graphs[delivery.recipient_authority_id]
        step = graph.process(report, delivered_at_s=value.at_s)
        self.event_log.append_public_artifact(
            at_s=value.at_s,
            event_type=ReferenceEventType.RECONCILIATION_UPDATED,
            artifact_id=f"{delivery.recipient_authority_id}-{report.call_id}",
            artifact_schema_version="delta-reference-reconciliation-step-v1",
            artifact=step.model_dump(mode="json"),
        )
        if not self._is_initial_decision_delivery(delivery, envelope):
            return
        cluster_key = (delivery.recipient_authority_id, step.belief_cluster_id)
        if cluster_key in self._decided_clusters:
            return
        execution = self.engine.execute(
            ReferenceDecisionInput(
                report=report,
                envelope=envelope,
                controller_authority_id=delivery.recipient_authority_id,
                reconciliation=step,
                active_commitments=self._active_beliefs(),
                known_outcomes=tuple(self._known_outcomes),
                coordination_latency_s=value.at_s - delivery.source_available_at_s,
                at_s=value.at_s,
                created_at=(
                    self.scenario.config.timeline.evaluation_start_iso8601
                    + self._seconds(value.at_s)
                ),
            )
        )
        self._decided_clusters.add(cluster_key)
        self._decisions.append(execution.result)
        if execution.commitment is not None:
            self._schedule_outcome(execution)
        elif execution.acquisition_request is not None:
            self._schedule_acquisition(
                execution,
                report,
                envelope,
                step,
                coordination_latency_s=value.at_s - delivery.source_available_at_s,
            )

    def _record_fault_application(
        self,
        attempt: ReferenceCoordinationFaultAttempt,
        *,
        disposition: Literal[
            "applied",
            "duplicate-effect-suppressed",
            "stale-key-rejected",
        ],
        reason: str,
    ) -> None:
        if self._fault_schedule is None:
            raise RuntimeError("Reference nominal runtime cannot record a fault application")
        application = build_reference_fault_application(
            self._fault_schedule,
            attempt,
            disposition=disposition,
            reason=reason,
        )
        self.event_log.append_fault_application(
            at_s=attempt.at_s,
            artifact=application.model_dump(mode="json"),
        )
        self._fault_applications.append(application)

    def _record_target_fault_application(
        self,
        *,
        fault_id: str,
        target_public_id: str,
        applied_at_s: int,
        reason: str,
    ) -> None:
        if self._fault_schedule is None:
            raise RuntimeError("Reference runtime fault lost its registered schedule")
        application = build_reference_target_fault_application(
            self._fault_schedule,
            fault_id=fault_id,
            target_public_id=target_public_id,
            applied_at_s=applied_at_s,
            disposition="applied",
            reason=reason,
        )
        self.event_log.append_fault_application(
            at_s=applied_at_s,
            artifact=application.model_dump(mode="json"),
        )
        self._fault_applications.append(application)

    @staticmethod
    def _seconds(value: int) -> timedelta:
        return timedelta(seconds=value)

    def _coordination_source(
        self,
        delivery: ReferenceCoordinationDelivery,
    ) -> ReferenceReportEnvelope | ReferenceResourceTelemetry:
        if delivery.evidence_kind == "public-report-envelope":
            return self._envelopes[delivery.evidence_id]
        return self._telemetry[delivery.evidence_id]

    def _validate_inputs(self, *, require_empty: bool) -> None:
        if require_empty and self.event_log.events:
            raise ValueError("Fresh Reference mission execution requires an empty event log")
        if not self.event_log.verify():
            raise ValueError("Reference mission event chain is invalid")
        expected_reports = len(self.scenario.observations.raw.reports) + len(
            self._report_fault_overlay.reports
        )
        if len(self._reports) != expected_reports:
            raise ValueError("Reference runtime report identifiers are not unique")
        if len(self._envelopes) != expected_reports:
            raise ValueError("Reference runtime envelope identifiers are not unique")
        if len(self._telemetry) != len(self.scenario.resources.public.telemetry):
            raise ValueError("Reference runtime telemetry identifiers are not unique")
        self._validate_activation_sources()
        self._validate_physical_chain()
        self._validate_public_sources()

    def _validate_activation_sources(self) -> None:
        schedule = self.scenario.coordination.activations
        catalog = self.scenario.resources.public_catalog
        if schedule.resource_catalog_digest != catalog.resource_catalog_digest:
            raise ValueError("Reference activation schedule binds another resource catalog")
        resources = {item.resource_id: item for item in catalog.resources}
        if {item.resource_id for item in schedule.events} != set(resources):
            raise ValueError("Reference activation schedule must cover the exact resource roster")
        for event in schedule.events:
            resource = resources[event.resource_id]
            if (
                event.tier != resource.tier
                or event.approving_authority_id != resource.owning_authority_id
            ):
                raise ValueError("Reference activation event conflicts with its resource roster")

    def _validate_physical_chain(self) -> None:
        previous = "GENESIS"
        for sequence, event in enumerate(self.scenario.physical.events, start=1):
            if event.sequence != sequence or event.previous_event_digest != previous:
                raise ValueError("Reference physical event chain is not contiguous")
            if not verify_reference_event(event):
                raise ValueError("Reference physical event chain contains invalid content")
            previous = event.event_digest

    def _validate_public_sources(self) -> None:
        from trace_reference.generation import verify_reference_envelope

        for envelope in self._envelopes.values():
            report = self._reports[envelope.call_id]
            if not verify_reference_envelope(report, envelope):
                raise ValueError("Reference scenario contains an unauthenticated report envelope")
        attempts = (
            *self._fault_overlay.attempts,
            *self._report_fault_overlay.coordination.attempts,
        )
        for attempt in attempts:
            source = self._coordination_source(attempt.delivery)
            if (
                reference_content_digest(source.model_dump(mode="json"))
                != attempt.delivery.source_content_digest
            ):
                raise ValueError("Reference scenario coordination source digest is invalid")

    def _restore(self, checkpoint: ReferenceMissionRestartCheckpoint) -> None:
        restored = ReferenceMissionRecovery(
            self.scenario,
            self.engine,
            self.event_log,
            self._fault_schedule,
            reports=self._reports,
            envelopes=self._envelopes,
        ).restore(checkpoint)
        self._graphs = restored.graphs
        self._active = restored.active
        self._known_outcomes = restored.known_outcomes
        self._decided_clusters = restored.decided_clusters
        self._decisions = restored.decisions
        self._outcomes = restored.outcomes
        self._contradictions = restored.contradictions
        self._compensations = restored.compensations
        self._consistency_debts = restored.consistency_debts
        self._pending_outcomes = restored.pending
        self._seen_delivery_ids = restored.seen_delivery_ids
        self._fault_applications = restored.fault_applications
        self._resume_after_s = checkpoint.through_s

    def _is_initial_decision_delivery(
        self,
        delivery: ReferenceCoordinationDelivery,
        envelope: ReferenceReportEnvelope,
    ) -> bool:
        authority = (
            "AUTH-01"
            if self.scenario.coordination.public.phi == 1
            else envelope.initial_authority_id
        )
        return (
            delivery.delivered_at_s >= 0
            and delivery.recipient_authority_id == authority
            and delivery.source_available_at_s == envelope.delivered_at_s
        )

    def _schedule_outcome(self, execution: ReferenceDecisionExecution) -> None:
        selected = next(
            item
            for item in execution.catalog.bundles
            if item.bundle_id == execution.selection.selected_bundle_id
        )
        action = selected.action
        commitment = execution.commitment
        envelope = execution.result
        if action is None or commitment is None or envelope.selected_resource_id is None:
            raise RuntimeError("Reference allocated decision lacks its exact action closure")
        scheduled_completion_s = action.commitment_horizon_end_s
        outcome_id = f"reference-outcome-{commitment.commitment_id[-20:]}"
        within = scheduled_completion_s <= EVALUATION_END_S
        partial_fault_id = self._selected_commitment_fault(
            "partial-service-outcome",
            commitment.commitment_id,
        )
        partial = partial_fault_id is not None and within
        status: ReferenceServiceOutcomeStatus = (
            "partial_service_within_window"
            if partial
            else ("completed_within_window" if within else "active_at_scenario_censoring")
        )
        outcome = build_service_outcome(
            ServiceOutcomeInput(
                outcome_id=outcome_id,
                commitment_id=commitment.commitment_id,
                status=status,
                scheduled_completion_s=scheduled_completion_s,
                observed_at_s=(scheduled_completion_s if within else EVALUATION_END_S),
                observed_completion_s=(scheduled_completion_s if within and not partial else None),
                realized_service_fraction_micros=(
                    None if not within else (500_000 if partial else 1_000_000)
                ),
                affected_public_subject_ids=(action.destination_public_id,),
                authorizing_trace_record_id=commitment.authorizing_trace_record_id,
                authorizing_trace_record_version=commitment.authorizing_trace_record_version,
            )
        )
        belief = PublicCommitmentBelief(
            commitment_id=commitment.commitment_id,
            resource_id=envelope.selected_resource_id,
            action_class=action.action_class,
            active_from_s=envelope.decided_at_s,
            active_until_s=scheduled_completion_s,
            authorizing_trace_record_id=commitment.authorizing_trace_record_id,
            authorizing_trace_record_version=commitment.authorizing_trace_record_version,
        )
        if belief.resource_id in self._active:
            raise RuntimeError("Reference runtime double-committed one physical resource")
        self._active[belief.resource_id] = ReferenceActiveCommitment(belief, outcome)
        heapq.heappush(
            self._pending_outcomes,
            ReferenceScheduledInput(
                min(scheduled_completion_s, EVALUATION_END_S),
                10,
                outcome_id,
                ReferenceInputKind.OUTCOME,
                ReferencePendingOutcome(
                    outcome,
                    belief.resource_id,
                    partial_fault_id if partial else None,
                ),
            ),
        )
        contradiction_fault_id = self._selected_commitment_fault(
            "contradictory-outcome-evidence",
            commitment.commitment_id,
        )
        if contradiction_fault_id is not None:
            if self._fault_schedule is None:
                raise RuntimeError("Reference outcome contradiction lost its fault schedule")
            compensation = next(
                item
                for item in self._fault_schedule.triggers
                if item.family == "failed-compensation"
            )
            heapq.heappush(
                self._pending_outcomes,
                ReferenceScheduledInput(
                    action.execution_not_after_s,
                    9,
                    f"reference-contradiction-{commitment.commitment_id}",
                    ReferenceInputKind.OUTCOME_CONTRADICTION,
                    ReferencePendingContradiction(
                        commitment_id=commitment.commitment_id,
                        resource_id=belief.resource_id,
                        affected_public_subject_ids=(action.destination_public_id,),
                        contradiction_fault_id=contradiction_fault_id,
                        compensation_fault_id=compensation.fault_id,
                    ),
                ),
            )

    def _selected_commitment_fault(
        self,
        family: Literal["partial-service-outcome", "contradictory-outcome-evidence"],
        commitment_id: str,
    ) -> str | None:
        if self._fault_schedule is None:
            return None
        trigger = next(item for item in self._fault_schedule.triggers if item.family == family)
        eligible = tuple(
            sorted(
                (
                    item
                    for item in self.engine.dependencies.commitment_log.all()
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
        if index >= len(eligible) or eligible[index].commitment_id != commitment_id:
            return None
        return trigger.fault_id

    def _schedule_acquisition(
        self,
        execution: ReferenceDecisionExecution,
        report: ReferenceRawReport,
        envelope: ReferenceReportEnvelope,
        reconciliation: ReferenceReconciliationStep,
        *,
        coordination_latency_s: int,
    ) -> None:
        request = execution.acquisition_request
        if request is None:
            raise RuntimeError("Reference acquisition decision lacks its request")
        if request.expected_delivery_s > EVALUATION_END_S:
            return
        silent_fault_id = self._select_silent_provider_fault(request)
        context = ReferenceAcquisitionContext(
            request,
            report,
            envelope,
            reconciliation,
            execution.result,
            coordination_latency_s,
        )
        if silent_fault_id is not None:
            if self._fault_schedule is None:
                raise RuntimeError("Reference provider fault lost its registered schedule")
            trigger = next(
                item for item in self._fault_schedule.triggers if item.fault_id == silent_fault_id
            )
            self._record_target_fault_application(
                fault_id=silent_fault_id,
                target_public_id=request.request_id,
                applied_at_s=request.requested_at_s,
                reason=(
                    "The registered semantic trigger selected this acquisition for a "
                    "client timeout followed by a later authenticated provider success."
                ),
            )
            self._push_pending_acquisition(
                request.expected_delivery_s,
                context,
                behavior="client-timeout",
                fault_id=silent_fault_id,
            )
            self._push_pending_acquisition(
                request.expected_delivery_s + trigger.delivery_offset_s,
                context,
                behavior="late-success",
                fault_id=silent_fault_id,
            )
            return
        self._push_pending_acquisition(
            request.expected_delivery_s,
            context,
            behavior="nominal-success",
            fault_id=None,
        )

    def _select_silent_provider_fault(
        self,
        request: AcquisitionRequestReceipt,
    ) -> str | None:
        if self._fault_schedule is None:
            return None
        trigger = next(
            item
            for item in self._fault_schedule.triggers
            if item.family == "silent-provider-success-after-timeout"
        )
        existing = next(
            (
                item
                for item in self._fault_applications
                if item.family == "silent-provider-success-after-timeout"
            ),
            None,
        )
        if existing is not None or request.requested_at_s < trigger.anchor_s:
            return None
        eligible = tuple(
            item
            for item in self._decisions
            if item.acquisition_request_id is not None and item.decided_at_s >= trigger.anchor_s
        )
        return trigger.fault_id if len(eligible) == trigger.ordinal else None

    def _push_pending_acquisition(
        self,
        at_s: int,
        context: ReferenceAcquisitionContext,
        *,
        behavior: ReferenceProviderBehavior,
        fault_id: str | None,
    ) -> None:
        heapq.heappush(
            self._pending_outcomes,
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

    def _complete_acquisition(self, value: object, at_s: int) -> None:
        if not isinstance(value, ReferencePendingAcquisition):
            raise TypeError("Reference provider queue payload has the wrong type")
        context = value.context
        if value.behavior == "client-timeout":
            receipt = build_reference_route_provider_timeout(context.request)
        else:
            late = value.behavior == "late-success"
            receipt = build_reference_route_provider_receipt(
                ReferenceRouteProviderInput(
                    request=context.request,
                    report=context.report,
                    route_service=self.engine.dependencies.route_service,
                    resources=self.scenario.resources,
                    observed_at_s=(context.request.expected_delivery_s if late else None),
                    delivered_at_s=(at_s if late else None),
                    receipt_id_suffix=("late-success" if late else None),
                )
            )
        if receipt.delivered_at_s != at_s:
            raise RuntimeError("Reference provider receipt missed its scheduled delivery")
        self.event_log.append_public_artifact(
            at_s=at_s,
            event_type=ReferenceEventType.PROVIDER_RECEIPT_RECORDED,
            artifact_id=receipt.receipt_id,
            artifact_schema_version=receipt.schema_version,
            artifact=receipt.model_dump(mode="json"),
        )
        outcome, evidence = self.engine.dependencies.acquisition_executor.ingest(receipt)
        self._record_acquisition_outcome(outcome, at_s)
        if value.behavior == "client-timeout" and (
            evidence is not None or outcome.outcome_status != "provider-timeout"
        ):
            raise RuntimeError("Reference client timeout produced an invalid provider result")
        if evidence is not None:
            self._validate_acquired_targets(context.request, evidence)
            self.event_log.append_public_artifact(
                at_s=at_s,
                event_type=ReferenceEventType.PHYSICAL_EVIDENCE_RECORDED,
                artifact_id=evidence.evidence_id,
                artifact_schema_version=evidence.schema_version,
                artifact=evidence.model_dump(mode="json"),
            )
        self._reassess_after_acquisition(context, outcome, evidence, at_s)

    def _reassess_after_acquisition(
        self,
        context: ReferenceAcquisitionContext,
        outcome: AcquisitionOutcomeReceipt,
        evidence: ReferencePhysicalEvidence | None,
        at_s: int,
    ) -> None:
        reassessment = self.engine.execute(
            ReferenceDecisionInput(
                report=context.report,
                envelope=context.envelope,
                controller_authority_id=context.original_decision.controller_authority_id,
                reconciliation=context.reconciliation,
                active_commitments=self._active_beliefs(),
                known_outcomes=tuple(self._known_outcomes),
                at_s=at_s,
                created_at=(
                    self.scenario.config.timeline.evaluation_start_iso8601 + self._seconds(at_s)
                ),
                reassessment_of_decision_id=context.original_decision.decision_id,
                acquisition_outcome=outcome,
                physical_evidence=evidence,
                coordination_latency_s=context.coordination_latency_s,
            )
        )
        self._decisions.append(reassessment.result)
        if reassessment.commitment is not None:
            self._schedule_outcome(reassessment)
        if reassessment.acquisition_request is not None:
            raise RuntimeError(
                "Reference post-acquisition reassessment requested another acquisition"
            )

    def _record_acquisition_outcome(
        self,
        outcome: AcquisitionOutcomeReceipt,
        at_s: int,
    ) -> None:
        self.event_log.append_public_artifact(
            at_s=at_s,
            event_type=ReferenceEventType.ACQUISITION_OUTCOME_RECORDED,
            artifact_id=f"acquisition-outcome-{outcome.provider_receipt_id}",
            artifact_schema_version=outcome.schema_version,
            artifact=outcome.model_dump(mode="json"),
        )

    @staticmethod
    def _validate_acquired_targets(
        request: AcquisitionRequestReceipt,
        evidence: ReferencePhysicalEvidence,
    ) -> None:
        from trace_reference.decision import ReferenceRouteVerificationPayload

        payload = ReferenceRouteVerificationPayload.model_validate_json(evidence.payload_json)
        if payload.request_id != request.request_id:
            raise ValueError("Reference provider evidence names another acquisition request")
        if payload.call_id != request.target_call_id:
            raise ValueError("Reference provider evidence names another public report")
        if payload.route_catalog_digest_at_request != request.route_catalog_digest:
            raise ValueError("Reference provider evidence names another requested route catalog")
        requested = tuple(
            zip(request.target_resource_ids, request.target_route_plan_ids, strict=True)
        )
        observed = tuple(
            (item.requested_resource_id, item.requested_route_plan_id)
            for item in payload.observations
        )
        if observed != tuple(sorted(requested)):
            raise ValueError(
                "Reference provider evidence does not cover the exact requested routes"
            )

    def _record_outcome(self, value: object, at_s: int) -> None:
        if not isinstance(value, ReferencePendingOutcome):
            raise TypeError("Reference outcome queue payload has the wrong type")
        active = self._active.get(value.resource_id)
        if active is None or active.scheduled_outcome != value.outcome:
            raise RuntimeError("Reference outcome does not bind one active commitment")
        if value.fault_id is not None:
            self._record_target_fault_application(
                fault_id=value.fault_id,
                target_public_id=value.outcome.commitment_id,
                applied_at_s=at_s,
                reason=(
                    "The registered semantic trigger produced a half-complete public service "
                    "outcome and retained its affected public subject set."
                ),
            )
        censor_fault_id = self._selected_censoring_fault(value.outcome.commitment_id)
        if censor_fault_id is not None:
            self._record_target_fault_application(
                fault_id=censor_fault_id,
                target_public_id=value.outcome.commitment_id,
                applied_at_s=at_s,
                reason=(
                    "The registered censoring boundary preserved this active commitment's "
                    "untruncated scheduled completion without reporting it as completed."
                ),
            )
        self.event_log.append_public_artifact(
            at_s=at_s,
            event_type=ReferenceEventType.OUTCOME_RECORDED,
            artifact_id=value.outcome.outcome_id,
            artifact_schema_version=value.outcome.schema_version,
            artifact=value.outcome.model_dump(mode="json"),
        )
        self._outcomes.append(value.outcome)
        self._known_outcomes.append(
            PublicOutcomeBelief(
                outcome_id=value.outcome.outcome_id,
                commitment_id=value.outcome.commitment_id,
                status=value.outcome.status,
                observed_at_s=value.outcome.observed_at_s,
            )
        )
        if value.outcome.status != "active_at_scenario_censoring":
            del self._active[value.resource_id]

    def _record_outcome_contradiction(self, value: object, at_s: int) -> None:
        if not isinstance(value, ReferencePendingContradiction):
            raise TypeError("Reference contradiction queue payload has the wrong type")
        active = self._active.get(value.resource_id)
        if active is None or active.belief.commitment_id != value.commitment_id:
            raise RuntimeError("Reference contradiction does not bind one active commitment")
        dependencies = self.engine.dependencies
        record = dependencies.trace_repository.get(active.belief.authorizing_trace_record_id)
        if record.record_version != active.belief.authorizing_trace_record_version:
            raise RuntimeError("Reference contradiction found a superseded authorizing record")
        original_evidence = dependencies.evidence_ledger.get(record.evidence_refs[-1])
        created_at = self.scenario.config.timeline.evaluation_start_iso8601 + self._seconds(at_s)
        artifacts = build_reference_outcome_fault_artifacts(
            commitment_id=value.commitment_id,
            affected_public_subject_ids=value.affected_public_subject_ids,
            authorizing_record=record,
            original_evidence=original_evidence,
            at_s=at_s,
            created_at=created_at,
        )
        self._record_target_fault_application(
            fault_id=value.contradiction_fault_id,
            target_public_id=value.commitment_id,
            applied_at_s=at_s,
            reason=(
                "The registered semantic trigger delivered authenticated public outcome "
                "evidence contradicting this active reversible commitment."
            ),
        )
        self.event_log.append_public_artifact(
            at_s=at_s,
            event_type=ReferenceEventType.OUTCOME_EVIDENCE_RECORDED,
            artifact_id=artifacts.contradiction.evidence_id,
            artifact_schema_version=artifacts.contradiction.schema_version,
            artifact=artifacts.contradiction.model_dump(mode="json"),
        )
        revised = dependencies.trace_gateway.revise_from_outcome(
            record,
            artifacts.world_evidence,
            at_s=at_s,
            created_at=created_at,
        )
        if (
            revised.record_id != artifacts.compensation.triggering_trace_record_id
            or revised.record_version != artifacts.compensation.triggering_trace_record_version
        ):
            raise RuntimeError("Reference compensation does not bind the realized TRACE revision")
        self.event_log.append_public_artifact(
            at_s=at_s,
            event_type=ReferenceEventType.COMPENSATION_RECORDED,
            artifact_id=artifacts.compensation.compensation_id,
            artifact_schema_version=artifacts.compensation.schema_version,
            artifact=artifacts.compensation.model_dump(mode="json"),
        )
        self._record_target_fault_application(
            fault_id=value.compensation_fault_id,
            target_public_id=artifacts.compensation.compensation_id,
            applied_at_s=at_s,
            reason=(
                "The registered dependent fault caused this corrective compensation attempt "
                "to fail and leave explicit residual consistency debt."
            ),
        )
        self.event_log.append_public_artifact(
            at_s=at_s,
            event_type=ReferenceEventType.CONSISTENCY_DEBT_RECORDED,
            artifact_id=artifacts.debt.debt_id,
            artifact_schema_version=artifacts.debt.schema_version,
            artifact=artifacts.debt.model_dump(mode="json"),
        )
        self._contradictions.append(artifacts.contradiction)
        self._compensations.append(artifacts.compensation)
        self._consistency_debts.append(artifacts.debt)
        self._known_outcomes.append(
            PublicOutcomeBelief(
                outcome_id=artifacts.contradiction.evidence_id,
                commitment_id=value.commitment_id,
                status="authorization-premise-contradicted",
                observed_at_s=at_s,
            )
        )

    def _selected_censoring_fault(self, commitment_id: str) -> str | None:
        if self._fault_schedule is None:
            return None
        trigger = next(
            item
            for item in self._fault_schedule.triggers
            if item.family == "completion-after-scenario-censoring"
        )
        eligible = tuple(
            sorted(
                item.scheduled_outcome.commitment_id
                for item in self._active.values()
                if item.scheduled_outcome.status == "active_at_scenario_censoring"
            )
        )
        index = trigger.ordinal - 1
        if index >= len(eligible) or eligible[index] != commitment_id:
            return None
        return trigger.fault_id

    def _active_beliefs(self) -> tuple[PublicCommitmentBelief, ...]:
        return tuple(
            sorted(
                (item.belief for item in self._active.values()),
                key=lambda item: item.commitment_id,
            )
        )

    def _result(self, through_s: int) -> ReferenceMissionRun:
        reconciliations = tuple(
            self._graphs[authority_id].artifact() for authority_id in sorted(self._graphs)
        )
        dependencies = self.engine.dependencies
        return ReferenceMissionRun(
            through_s=through_s,
            complete=through_s == EVALUATION_END_S,
            decisions=tuple(self._decisions),
            outcomes=tuple(self._outcomes),
            contradictions=tuple(self._contradictions),
            compensations=tuple(self._compensations),
            consistency_debts=tuple(self._consistency_debts),
            reconciliations=reconciliations,
            event_prefix_digest=self.event_log.prefix_digest,
            trace_prefix_digest=dependencies.trace_repository.prefix_digest,
            evidence_prefix_digest=dependencies.evidence_ledger.prefix_digest,
            commitment_prefix_digest=dependencies.commitment_log.prefix_digest,
            fault_profile_id=(
                "reference-nominal-v1"
                if self._fault_schedule is None
                else self._fault_schedule.profile_id
            ),
            fault_applications=tuple(self._fault_applications),
            unreachable_delivery_fault_ids=tuple(
                sorted(
                    {
                        *self._fault_overlay.unreachable_fault_ids,
                        *self._report_fault_overlay.coordination.unreachable_fault_ids,
                    }
                )
            ),
        )
