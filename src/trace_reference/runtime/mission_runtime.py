"""Lazy chronological orchestration for the non-LEAP Reference mission."""

from __future__ import annotations

import hashlib
import heapq
import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import cast

from trace_jepa.support import canonical_json_bytes
from trace_reference.decision import (
    AcquisitionOutcomeReceipt,
    AcquisitionRequestReceipt,
    ReferencePhysicalEvidence,
    ReferenceServiceOutcome,
    ServiceOutcomeInput,
    build_service_outcome,
)
from trace_reference.decision.domain import PublicCommitmentBelief, PublicOutcomeBelief
from trace_reference.domain import (
    ReferenceDecisionExecution,
    ReferenceEvent,
    ReferenceEventType,
    ReferenceMissionDecision,
    ReferenceRawReport,
    ReferenceReportEnvelope,
    ReferenceResourceTelemetry,
    ReferenceScenarioArtifacts,
)
from trace_reference.domain.coordination import ReferenceCoordinationDelivery
from trace_reference.domain.observations import ReferenceAuthorityId
from trace_reference.reconciliation import (
    ReferenceEvidenceGraph,
    ReferenceReconciliationArtifact,
    ReferenceReconciliationStep,
)

from .acquisition_provider import (
    ReferenceRouteProviderInput,
    build_reference_route_provider_receipt,
)
from .decision_engine import ReferenceDecisionEngine, ReferenceDecisionInput
from .event_store import ReferenceEventLog, verify_reference_event

_EVALUATION_END_S = 345_600


class _InputKind(str, Enum):
    PHYSICAL = "physical"
    PROVIDER = "provider"
    OUTCOME = "outcome"
    REPORT = "report"
    TELEMETRY = "telemetry"
    COORDINATION = "coordination"


@dataclass(order=True, frozen=True)
class _ScheduledInput:
    """One queue item; payload is excluded from ordering and never copied."""

    at_s: int
    priority: int
    stable_id: str
    kind: _InputKind = field(compare=False)
    payload: object = field(compare=False)


@dataclass(frozen=True)
class _PendingOutcome:
    outcome: ReferenceServiceOutcome
    resource_id: str


@dataclass(frozen=True)
class _PendingAcquisition:
    request: AcquisitionRequestReceipt
    report: ReferenceRawReport
    envelope: ReferenceReportEnvelope
    reconciliation: ReferenceReconciliationStep
    original_decision: ReferenceMissionDecision


@dataclass(frozen=True)
class _ActiveCommitment:
    belief: PublicCommitmentBelief
    scheduled_outcome: ReferenceServiceOutcome


@dataclass(frozen=True)
class ReferenceMissionRun:
    """Bounded in-memory view; the append-only stores remain authoritative."""

    through_s: int
    complete: bool
    decisions: tuple[ReferenceMissionDecision, ...]
    outcomes: tuple[ReferenceServiceOutcome, ...]
    reconciliations: tuple[ReferenceReconciliationArtifact, ...]
    event_prefix_digest: str
    trace_prefix_digest: str
    evidence_prefix_digest: str
    commitment_prefix_digest: str


def _content_digest(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _physical_inputs(events: Iterable[ReferenceEvent]) -> Iterator[_ScheduledInput]:
    for event in events:
        yield _ScheduledInput(
            event.at_s,
            0,
            f"physical-{event.sequence:08d}",
            _InputKind.PHYSICAL,
            event,
        )


def _report_inputs(
    envelopes: Iterable[ReferenceReportEnvelope],
) -> Iterator[_ScheduledInput]:
    for envelope in envelopes:
        yield _ScheduledInput(
            envelope.delivered_at_s,
            20,
            envelope.envelope_id,
            _InputKind.REPORT,
            envelope,
        )


def _telemetry_inputs(
    telemetry: Iterable[ReferenceResourceTelemetry],
) -> Iterator[_ScheduledInput]:
    for item in telemetry:
        yield _ScheduledInput(
            item.delivered_at_s,
            21,
            item.telemetry_id,
            _InputKind.TELEMETRY,
            item,
        )


def _coordination_inputs(scenario: ReferenceScenarioArtifacts) -> Iterator[_ScheduledInput]:
    for delivery in scenario.coordination.public.deliveries:
        yield _ScheduledInput(
            delivery.delivered_at_s,
            30,
            delivery.delivery_id,
            _InputKind.COORDINATION,
            delivery,
        )


class ReferenceMissionRuntime:
    """Execute the 96-hour base Reference path without LEAP behavior."""

    def __init__(
        self,
        scenario: ReferenceScenarioArtifacts,
        decision_engine: ReferenceDecisionEngine,
    ) -> None:
        if decision_engine.dependencies.scenario is not scenario:
            raise ValueError("Reference decision engine must bind the exact scenario object")
        if scenario.config.timeline.evaluation_end_s != _EVALUATION_END_S:
            raise ValueError("Reference runtime requires the registered 96-hour horizon")
        self.scenario = scenario
        self.engine = decision_engine
        self.event_log: ReferenceEventLog = decision_engine.dependencies.event_log
        self._reports = {item.call_id: item for item in scenario.observations.raw.reports}
        self._envelopes = {
            item.envelope_id: item for item in scenario.observations.delivery.envelopes
        }
        self._envelope_by_call = {
            item.call_id: item for item in scenario.observations.delivery.envelopes
        }
        self._telemetry = {
            item.telemetry_id: item for item in scenario.resources.public.telemetry
        }
        self._graphs = {
            authority.authority_id: ReferenceEvidenceGraph(
                cast(ReferenceAuthorityId, authority.authority_id)
            )
            for authority in scenario.governance.authorities
        }
        self._active: dict[str, _ActiveCommitment] = {}
        self._known_outcomes: list[PublicOutcomeBelief] = []
        self._decided_clusters: set[tuple[str, str]] = set()
        self._decisions: list[ReferenceMissionDecision] = []
        self._outcomes: list[ReferenceServiceOutcome] = []
        self._pending_outcomes: list[_ScheduledInput] = []
        self._run_started = False
        self._validate_inputs()

    def run(self, *, through_s: int = _EVALUATION_END_S) -> ReferenceMissionRun:
        """Run once from burn-in through an inclusive characterization boundary."""

        if not -172_800 <= through_s <= _EVALUATION_END_S:
            raise ValueError("Reference runtime boundary is outside the scenario window")
        if self._run_started:
            raise RuntimeError("Reference mission runtime instances are single-use")
        self._run_started = True
        external = iter(
            heapq.merge(
                _physical_inputs(self.scenario.physical.events),
                _report_inputs(self.scenario.observations.delivery.envelopes),
                _telemetry_inputs(self.scenario.resources.public.telemetry),
                _coordination_inputs(self.scenario),
            )
        )
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
        return self._result(through_s)

    def _process(self, scheduled: _ScheduledInput) -> None:
        if scheduled.kind == _InputKind.PHYSICAL:
            self._append_physical(scheduled.payload)
        elif scheduled.kind == _InputKind.PROVIDER:
            self._complete_acquisition(scheduled.payload, scheduled.at_s)
        elif scheduled.kind == _InputKind.OUTCOME:
            self._record_outcome(scheduled.payload, scheduled.at_s)
        elif scheduled.kind == _InputKind.REPORT:
            self._record_report(scheduled.payload)
        elif scheduled.kind == _InputKind.TELEMETRY:
            self._record_telemetry(scheduled.payload)
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

    def _deliver_coordination(self, value: object) -> None:
        if not isinstance(value, ReferenceCoordinationDelivery):
            raise TypeError("Reference coordination queue payload has the wrong type")
        source = self._coordination_source(value)
        if _content_digest(source.model_dump(mode="json")) != value.source_content_digest:
            raise ValueError("Reference coordination delivery source digest is invalid")
        self.event_log.append_public_artifact(
            at_s=value.delivered_at_s,
            event_type=ReferenceEventType.COORDINATION_MESSAGE_DELIVERED,
            artifact_id=value.delivery_id,
            artifact_schema_version="delta-reference-coordination-delivery-v1",
            artifact={
                "schema_version": "delta-reference-coordination-delivery-v1",
                "delivery": value.model_dump(mode="json"),
            },
        )
        if value.evidence_kind != "public-report-envelope":
            return
        envelope = self._envelopes[value.evidence_id]
        report = self._reports[envelope.call_id]
        graph = self._graphs[value.recipient_authority_id]
        step = graph.process(report, delivered_at_s=value.delivered_at_s)
        self.event_log.append_public_artifact(
            at_s=value.delivered_at_s,
            event_type=ReferenceEventType.RECONCILIATION_UPDATED,
            artifact_id=f"{value.recipient_authority_id}-{report.call_id}",
            artifact_schema_version="delta-reference-reconciliation-step-v1",
            artifact=step.model_dump(mode="json"),
        )
        if not self._is_initial_decision_delivery(value, envelope):
            return
        cluster_key = (value.recipient_authority_id, step.belief_cluster_id)
        if cluster_key in self._decided_clusters:
            return
        execution = self.engine.execute(
            ReferenceDecisionInput(
                report=report,
                envelope=envelope,
                controller_authority_id=value.recipient_authority_id,
                reconciliation=step,
                active_commitments=self._active_beliefs(),
                known_outcomes=tuple(self._known_outcomes),
                at_s=value.delivered_at_s,
                created_at=(
                    self.scenario.config.timeline.evaluation_start_iso8601
                    + self._seconds(value.delivered_at_s)
                ),
            )
        )
        self._decided_clusters.add(cluster_key)
        self._decisions.append(execution.result)
        if execution.commitment is not None:
            self._schedule_outcome(execution)
        elif execution.acquisition_request is not None:
            self._schedule_acquisition(execution, report, envelope, step)

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

    def _validate_inputs(self) -> None:
        from trace_reference.generation import verify_reference_envelope

        if self.event_log.events:
            raise ValueError("Fresh Reference mission execution requires an empty event log")
        if len(self._reports) != len(self.scenario.observations.raw.reports):
            raise ValueError("Reference runtime report identifiers are not unique")
        if len(self._envelopes) != len(self.scenario.observations.delivery.envelopes):
            raise ValueError("Reference runtime envelope identifiers are not unique")
        if len(self._telemetry) != len(self.scenario.resources.public.telemetry):
            raise ValueError("Reference runtime telemetry identifiers are not unique")
        previous = "GENESIS"
        for sequence, event in enumerate(self.scenario.physical.events, start=1):
            if event.sequence != sequence or event.previous_event_digest != previous:
                raise ValueError("Reference physical event chain is not contiguous")
            if not verify_reference_event(event):
                raise ValueError("Reference physical event chain contains invalid content")
            previous = event.event_digest
        for envelope in self.scenario.observations.delivery.envelopes:
            report = self._reports[envelope.call_id]
            if not verify_reference_envelope(report, envelope):
                raise ValueError("Reference scenario contains an unauthenticated report envelope")
        for delivery in self.scenario.coordination.public.deliveries:
            source = self._coordination_source(delivery)
            if _content_digest(source.model_dump(mode="json")) != delivery.source_content_digest:
                raise ValueError("Reference scenario coordination source digest is invalid")

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
            and delivery.delivered_at_s == envelope.delivered_at_s
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
        within = scheduled_completion_s <= _EVALUATION_END_S
        outcome = build_service_outcome(
            ServiceOutcomeInput(
                outcome_id=outcome_id,
                commitment_id=commitment.commitment_id,
                status=(
                    "completed_within_window" if within else "active_at_scenario_censoring"
                ),
                scheduled_completion_s=scheduled_completion_s,
                observed_completion_s=scheduled_completion_s if within else None,
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
        self._active[belief.resource_id] = _ActiveCommitment(belief, outcome)
        heapq.heappush(
            self._pending_outcomes,
            _ScheduledInput(
                min(scheduled_completion_s, _EVALUATION_END_S),
                10,
                outcome_id,
                _InputKind.OUTCOME,
                _PendingOutcome(outcome, belief.resource_id),
            ),
        )

    def _schedule_acquisition(
        self,
        execution: ReferenceDecisionExecution,
        report: ReferenceRawReport,
        envelope: ReferenceReportEnvelope,
        reconciliation: ReferenceReconciliationStep,
    ) -> None:
        request = execution.acquisition_request
        if request is None:
            raise RuntimeError("Reference acquisition decision lacks its request")
        if request.expected_delivery_s > _EVALUATION_END_S:
            return
        heapq.heappush(
            self._pending_outcomes,
            _ScheduledInput(
                request.expected_delivery_s,
                10,
                request.request_id,
                _InputKind.PROVIDER,
                _PendingAcquisition(
                    request,
                    report,
                    envelope,
                    reconciliation,
                    execution.result,
                ),
            ),
        )

    def _complete_acquisition(self, value: object, at_s: int) -> None:
        if not isinstance(value, _PendingAcquisition):
            raise TypeError("Reference provider queue payload has the wrong type")
        receipt = build_reference_route_provider_receipt(
            ReferenceRouteProviderInput(
                request=value.request,
                report=value.report,
                route_service=self.engine.dependencies.route_service,
                resources=self.scenario.resources,
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
        if evidence is None:
            return
        self._validate_acquired_targets(value.request, evidence)
        self.event_log.append_public_artifact(
            at_s=at_s,
            event_type=ReferenceEventType.PHYSICAL_EVIDENCE_RECORDED,
            artifact_id=evidence.evidence_id,
            artifact_schema_version=evidence.schema_version,
            artifact=evidence.model_dump(mode="json"),
        )
        reassessment = self.engine.execute(
            ReferenceDecisionInput(
                report=value.report,
                envelope=value.envelope,
                controller_authority_id=value.original_decision.controller_authority_id,
                reconciliation=value.reconciliation,
                active_commitments=self._active_beliefs(),
                known_outcomes=tuple(self._known_outcomes),
                at_s=at_s,
                created_at=(
                    self.scenario.config.timeline.evaluation_start_iso8601
                    + self._seconds(at_s)
                ),
                reassessment_of_decision_id=value.original_decision.decision_id,
                acquisition_outcome=outcome,
                physical_evidence=evidence,
            )
        )
        self._decisions.append(reassessment.result)
        if reassessment.commitment is not None:
            self._schedule_outcome(reassessment)
        if reassessment.acquisition_request is not None:
            raise RuntimeError("Reference post-acquisition reassessment requested another acquisition")

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
        requested = tuple(zip(request.target_resource_ids, request.target_route_plan_ids, strict=True))
        observed = tuple(
            (item.requested_resource_id, item.requested_route_plan_id)
            for item in payload.observations
        )
        if observed != tuple(sorted(requested)):
            raise ValueError("Reference provider evidence does not cover the exact requested routes")

    def _record_outcome(self, value: object, at_s: int) -> None:
        if not isinstance(value, _PendingOutcome):
            raise TypeError("Reference outcome queue payload has the wrong type")
        active = self._active.get(value.resource_id)
        if active is None or active.scheduled_outcome != value.outcome:
            raise RuntimeError("Reference outcome does not bind one active commitment")
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
                observed_at_s=at_s,
            )
        )
        del self._active[value.resource_id]

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
            complete=through_s == _EVALUATION_END_S,
            decisions=tuple(self._decisions),
            outcomes=tuple(self._outcomes),
            reconciliations=reconciliations,
            event_prefix_digest=self.event_log.prefix_digest,
            trace_prefix_digest=dependencies.trace_repository.prefix_digest,
            evidence_prefix_digest=dependencies.evidence_ledger.prefix_digest,
            commitment_prefix_digest=dependencies.commitment_log.prefix_digest,
        )
