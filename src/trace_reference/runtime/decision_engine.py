"""One complete non-LEAP Reference decision through TRACE closure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trace_jepa.predictor import ActionPrefixPredictor
from trace_reference.decision import (
    AcquisitionOutcomeReceipt,
    AcquisitionRequestReceipt,
    BaseSelectionReceipt,
    CostDeltaInput,
    DecisionCostDelta,
    DecisionManifestInput,
    EligibilityReceipt,
    EvidenceAcquisitionExecutor,
    ReferenceCommitmentEnvelope,
    ReferenceDecisionManifest,
    ReferenceTraceAssessment,
    ResponseBundleCatalog,
    build_cost_delta,
    build_decision_manifest,
)
from trace_reference.decision.acquisition import (
    ReferencePhysicalEvidence,
    ReferenceRouteVerificationPayload,
)
from trace_reference.decision.canonical import decision_digest, verify_model_digest
from trace_reference.decision.domain import (
    BaseSelectionRequest,
    ControllerVisibleSnapshot,
    PhysicalActionProposal,
    ProposalRequest,
    ProposalSet,
    PublicCommitmentBelief,
    PublicEnvironmentBelief,
    PublicOutcomeBelief,
    ResponseBundleKind,
    SafeAlternativeProposal,
)
from trace_reference.decision.eligibility import (
    build_response_bundle_catalog,
    classify_reference_proposals,
)
from trace_reference.decision.evidence_binding import bind_predictor_evidence
from trace_reference.decision.proposals import propose_reference_actions
from trace_reference.decision.selector import BaseReferenceSelector
from trace_reference.decision.visibility import SnapshotInput, build_controller_visible_snapshot
from trace_reference.domain import (
    ReferenceDecisionExecution,
    ReferenceDecisionHandoffArtifact,
    ReferenceEventType,
    ReferenceMissionDecision,
    ReferenceRawReport,
    ReferenceReportEnvelope,
    ReferenceScenarioArtifacts,
)
from trace_reference.domain.observations import ReferenceAuthorityId
from trace_reference.domain.routing import ReferencePublicRouteCatalog, ReferencePublicRoutePlan
from trace_reference.reconciliation import ReferenceReconciliationStep

from .event_store import ReferenceEventLog
from .predictor_evidence import (
    ReferencePredictorEvidenceInput,
    ReferencePredictorEvidencePackage,
    build_reference_predictor_evidence,
)
from .routing import ReferenceRouteService
from .scenario_index import ReferenceScenarioIndex
from .trace_gateway import (
    ProposalAssessmentInput,
    ReferenceTraceGateway,
    SelectedCommitmentInput,
)
from .trace_storage import (
    ReferenceCommitmentLog,
    ReferenceEvidenceLedger,
    ReferenceTraceRepository,
)

ActionProposal = PhysicalActionProposal | SafeAlternativeProposal


def _action_proposals(
    physical: tuple[PhysicalActionProposal, ...],
    safe: tuple[SafeAlternativeProposal, ...],
) -> tuple[ActionProposal, ...]:
    return (*physical, *safe)


@dataclass(frozen=True)
class ReferenceDecisionEngineDependencies:
    scenario: ReferenceScenarioArtifacts
    index: ReferenceScenarioIndex
    route_service: ReferenceRouteService
    predictor: ActionPrefixPredictor
    event_log: ReferenceEventLog
    trace_gateway: ReferenceTraceGateway
    evidence_ledger: ReferenceEvidenceLedger
    trace_repository: ReferenceTraceRepository
    commitment_log: ReferenceCommitmentLog
    acquisition_executor: EvidenceAcquisitionExecutor
    policy_version: str
    environment_contract_version: str


@dataclass(frozen=True)
class ReferenceDecisionInput:
    report: ReferenceRawReport
    envelope: ReferenceReportEnvelope
    controller_authority_id: ReferenceAuthorityId
    reconciliation: ReferenceReconciliationStep
    active_commitments: tuple[PublicCommitmentBelief, ...]
    known_outcomes: tuple[PublicOutcomeBelief, ...]
    at_s: int
    created_at: datetime
    reassessment_of_decision_id: str | None = None
    acquisition_outcome: AcquisitionOutcomeReceipt | None = None
    physical_evidence: ReferencePhysicalEvidence | None = None
    coordination_latency_s: int | None = None


@dataclass(frozen=True)
class _DecisionHandoffInput:
    result: ReferenceMissionDecision
    snapshot: ControllerVisibleSnapshot
    proposals: ProposalSet
    assessments: tuple[ReferenceTraceAssessment, ...]
    eligibility: EligibilityReceipt
    catalog: ResponseBundleCatalog
    selection: BaseSelectionReceipt
    cost: DecisionCostDelta
    manifest: ReferenceDecisionManifest
    commitment: ReferenceCommitmentEnvelope | None
    acquisition_request: AcquisitionRequestReceipt | None


@dataclass(frozen=True)
class _AssessmentArtifacts:
    by_proposal_digest: dict[str, ReferenceTraceAssessment]
    by_action_digest: dict[str, ProposalAssessmentInput]


def _build_decision_handoff(values: _DecisionHandoffInput) -> ReferenceDecisionHandoffArtifact:
    body = {
        "schema_version": "delta-reference-decision-handoff-artifact-v1",
        "decision": values.result.model_dump(mode="json"),
        "public_snapshot": values.snapshot.model_dump(mode="json"),
        "proposals": values.proposals.model_dump(mode="json"),
        "assessments": [item.model_dump(mode="json") for item in values.assessments],
        "eligibility": values.eligibility.model_dump(mode="json"),
        "catalog": values.catalog.model_dump(mode="json"),
        "selection": values.selection.model_dump(mode="json"),
        "cost_delta": values.cost.model_dump(mode="json"),
        "manifest": values.manifest.model_dump(mode="json"),
        "commitment": (
            values.commitment.model_dump(mode="json") if values.commitment is not None else None
        ),
        "acquisition_request": (
            values.acquisition_request.model_dump(mode="json")
            if values.acquisition_request is not None
            else None
        ),
    }
    return ReferenceDecisionHandoffArtifact(
        **body,
        artifact_digest=decision_digest(body),
    )


class ReferenceDecisionEngine:
    """Execute the base selector path; it has no LEAP scoring or search behavior."""

    def __init__(self, dependencies: ReferenceDecisionEngineDependencies) -> None:
        self.dependencies = dependencies

    def execute(self, values: ReferenceDecisionInput) -> ReferenceDecisionExecution:
        self._validate_input(values)
        decision_id = self._decision_id(values)
        snapshot = build_controller_visible_snapshot(
            SnapshotInput(
                mission_id="reference-mission-development-v1",
                decision_id=decision_id,
                controller_authority_id=values.controller_authority_id,
                at_s=values.at_s,
                delivered_coordination_ids=self.dependencies.event_log.public_artifact_ids(
                    ReferenceEventType.COORDINATION_MESSAGE_DELIVERED
                ),
                delivered_activation_event_ids=(
                    self.dependencies.event_log.public_artifact_ids(
                        ReferenceEventType.RESOURCE_ACTIVATION_UPDATED
                    )
                ),
                evidence_prefix_digest=self.dependencies.evidence_ledger.prefix_digest,
                trace_prefix_digest=self.dependencies.trace_repository.prefix_digest,
                commitment_prefix_digest=self.dependencies.commitment_log.prefix_digest,
                environment_beliefs=self._environment_beliefs(values.at_s),
                active_commitments=values.active_commitments,
                known_outcomes=values.known_outcomes,
                prior_profile_id=self.dependencies.scenario.prior.profile_id,
                policy_version=self.dependencies.policy_version,
                environment_contract_version=self.dependencies.environment_contract_version,
            ),
            self.dependencies.scenario.resources.public,
            self.dependencies.scenario.resources.public_catalog,
            self.dependencies.scenario.coordination.public,
            self.dependencies.predictor.provenance(),
            self.dependencies.scenario.coordination.activations,
        )
        routes = self.dependencies.route_service.build_catalog(
            values.report,
            self.dependencies.scenario.resources.public_catalog,
            at_s=values.at_s,
        )
        if values.physical_evidence is not None:
            self._validate_physical_evidence(values, routes)
        request = ProposalRequest(
            schema_version="delta-reference-proposal-request-v2",
            decision_id=snapshot.decision_id,
            public_snapshot_digest=snapshot.snapshot_digest,
            target_public_incident_id=values.reconciliation.belief_cluster_id,
            public_taxonomy=values.report.taxonomy.value,
            route_catalog=routes,
            decision_deadline_s=min(345_600, values.at_s + 3_600),
            policy_version=self.dependencies.policy_version,
            proposal_namespace="reference-public-proposal-grammar-v1",
            acquisition_allowed=values.acquisition_outcome is None,
        )
        unbound = propose_reference_actions(request, snapshot)
        packages = self._predict(
            unbound.physical_actions,
            unbound.safe_alternatives,
            values,
            snapshot,
            routes,
        )
        proposals = bind_predictor_evidence(
            unbound,
            {action_digest: item.binding for action_digest, item in packages.items()},
        )
        proposal_by_action = {
            item.action.action_digest: item
            for item in _action_proposals(
                proposals.physical_actions,
                proposals.safe_alternatives,
            )
        }
        assessed = self._assess_proposals(packages, proposal_by_action, snapshot, values)
        assessments = assessed.by_proposal_digest
        assessment_inputs = assessed.by_action_digest
        eligibility = classify_reference_proposals(snapshot, proposals, assessments)
        catalog = build_response_bundle_catalog(snapshot, proposals, eligibility)
        selection = BaseReferenceSelector().select(
            BaseSelectionRequest(
                catalog_digest=catalog.catalog_digest,
                public_snapshot_digest=snapshot.snapshot_digest,
                trace_prefix_digest=catalog.trace_prefix_digest,
                at_s=values.at_s,
            ),
            catalog,
        )
        selected = next(
            (item for item in catalog.bundles if item.bundle_id == selection.selected_bundle_id),
            None,
        )
        commitment = None
        acquisition_request = None
        trace_record_id = None
        trace_record_version = None
        selected_resource_id = None
        reason = selection.reason
        disposition = "refused"
        if selected is not None and selected.kind == ResponseBundleKind.ACQUIRE_THEN_REASSESS:
            acquisition_request = self.dependencies.acquisition_executor.request(selected)
            disposition = "acquisition-requested"
            self.dependencies.event_log.append_public_artifact(
                at_s=values.at_s,
                event_type=ReferenceEventType.ACQUISITION_REQUESTED,
                artifact_id=acquisition_request.request_id,
                artifact_schema_version=acquisition_request.schema_version,
                artifact=acquisition_request.model_dump(mode="json"),
            )
        elif selected is not None:
            proposal = next(
                item
                for item in _action_proposals(
                    proposals.physical_actions,
                    proposals.safe_alternatives,
                )
                if item.proposal_digest == selected.proposal_digest
            )
            closure = self.dependencies.trace_gateway.commit_selected(
                SelectedCommitmentInput(
                    bundle=selected,
                    catalog=catalog,
                    selection=selection,
                    proposal=proposal,
                    assessment_input=assessment_inputs[proposal.action.action_digest],
                    consumer_action_id=f"reference-consumer-{snapshot.decision_id}",
                )
            )
            trace_record_id = closure.consumed_record.record_id
            trace_record_version = closure.consumed_record.record_version
            commitment = closure.commitment_envelope
            if commitment is not None:
                disposition = "allocated"
                selected_resource_id = proposal.action.actor_resource_id
            else:
                reason = "Post-selection TRACE reassessment did not authorize commitment."
        cost = build_cost_delta(
            CostDeltaInput(
                receipt_id=f"cost-{snapshot.decision_id}",
                predictor_inference_count=len(packages),
                planning_transition_count=5,
                primitive_operation_count=(
                    len(proposals.physical_actions)
                    + len(proposals.acquisition_offers)
                    + len(proposals.safe_alternatives)
                ),
                decision_latency_s=selection.simulated_compute_latency_s,
            )
        )
        manifest = build_decision_manifest(
            DecisionManifestInput(
                decision_id=snapshot.decision_id,
                public_snapshot_digest=snapshot.snapshot_digest,
                proposal_set_digest=proposals.proposal_set_digest,
                eligibility_receipt_digest=eligibility.eligibility_receipt_digest,
                catalog_digest=catalog.catalog_digest,
                selection_digest=selection.selection_digest,
                cost_delta_digest=cost.cost_delta_digest,
                acquisition_request_digest=(
                    acquisition_request.request_digest if acquisition_request is not None else None
                ),
                acquisition_outcome_digest=(
                    values.acquisition_outcome.outcome_digest
                    if values.acquisition_outcome is not None
                    else None
                ),
                post_delay_trace_record_id=trace_record_id,
                post_delay_trace_record_version=trace_record_version,
                commitment_envelope_digest=(
                    commitment.envelope_digest if commitment is not None else None
                ),
            )
        )
        body = {
            "schema_version": "delta-reference-mission-decision-v2",
            "decision_id": snapshot.decision_id,
            "call_id": values.report.call_id,
            "controller_authority_id": values.controller_authority_id,
            "belief_cluster_id": values.reconciliation.belief_cluster_id,
            "decided_at_s": values.at_s,
            "disposition": disposition,
            "selected_bundle_id": selection.selected_bundle_id,
            "selected_resource_id": selected_resource_id,
            "trace_record_id": trace_record_id,
            "trace_record_version": trace_record_version,
            "commitment_id": commitment.commitment_id if commitment is not None else None,
            "acquisition_request_id": (
                acquisition_request.request_id if acquisition_request is not None else None
            ),
            "reason": reason,
            "manifest_digest": manifest.manifest_digest,
            "reassessment_of_decision_id": values.reassessment_of_decision_id,
        }
        result = ReferenceMissionDecision(**body, decision_digest=decision_digest(body))
        assessments_ordered = tuple(assessments[key] for key in sorted(assessments))
        handoff = _build_decision_handoff(
            _DecisionHandoffInput(
                result,
                snapshot,
                proposals,
                assessments_ordered,
                eligibility,
                catalog,
                selection,
                cost,
                manifest,
                commitment,
                acquisition_request,
            )
        )
        self.dependencies.event_log.append_public_artifact(
            at_s=values.at_s,
            event_type=ReferenceEventType.DECISION_MANIFEST_RECORDED,
            artifact_id=result.decision_id,
            artifact_schema_version=handoff.schema_version,
            artifact=handoff.model_dump(mode="json"),
        )
        return ReferenceDecisionExecution(
            result=result,
            reconciliation=values.reconciliation,
            proposals=proposals,
            assessments=assessments_ordered,
            eligibility=eligibility,
            catalog=catalog,
            selection=selection,
            commitment=commitment,
            acquisition_request=acquisition_request,
            manifest=manifest,
            public_snapshot=snapshot,
            cost_delta=cost,
            handoff_artifact=handoff,
        )

    @staticmethod
    def _decision_id(values: ReferenceDecisionInput) -> str:
        if values.physical_evidence is not None:
            return f"reference-reassessment-{values.physical_evidence.evidence_id}"
        if values.acquisition_outcome is not None:
            return (
                f"reference-reassessment-outcome-{values.acquisition_outcome.outcome_digest[:20]}"
            )
        return f"reference-decision-{values.envelope.envelope_id}"

    def _assess_proposals(
        self,
        packages: dict[str, ReferencePredictorEvidencePackage],
        proposal_by_action: dict[str, ActionProposal],
        snapshot: ControllerVisibleSnapshot,
        values: ReferenceDecisionInput,
    ) -> _AssessmentArtifacts:
        assessments: dict[str, ReferenceTraceAssessment] = {}
        inputs: dict[str, ProposalAssessmentInput] = {}
        for action_digest, package in packages.items():
            proposal = proposal_by_action[action_digest]
            assessment_input = ProposalAssessmentInput(
                proposal=proposal,
                snapshot=snapshot,
                predictor_request=package.request,
                evidence=package.evidence,
                claim=package.claim,
                at_s=values.at_s,
                created_at=values.created_at,
                lineage_key=f"reference-decision|{snapshot.decision_id}|{action_digest}",
            )
            assessed = self.dependencies.trace_gateway.assess(assessment_input)
            assessments[proposal.proposal_digest] = assessed.assessment
            inputs[action_digest] = assessment_input
        return _AssessmentArtifacts(assessments, inputs)

    def _predict(
        self,
        physical: tuple[PhysicalActionProposal, ...],
        safe: tuple[SafeAlternativeProposal, ...],
        values: ReferenceDecisionInput,
        snapshot: ControllerVisibleSnapshot,
        routes: ReferencePublicRouteCatalog,
    ) -> dict[str, ReferencePredictorEvidencePackage]:
        coordination_latency = self._coordination_latency(values)
        packages = {}
        for proposal in _action_proposals(physical, safe):
            package = build_reference_predictor_evidence(
                ReferencePredictorEvidenceInput(
                    proposal=proposal,
                    snapshot=snapshot,
                    report=values.report,
                    route_catalog=routes,
                    resource_catalog=self.dependencies.scenario.resources.public_catalog,
                    prior=self.dependencies.scenario.prior,
                    index=self.dependencies.index,
                    predictor=self.dependencies.predictor,
                    at_s=values.at_s,
                    coordination_latency_s=coordination_latency,
                    created_at=values.created_at,
                    physical_evidence=values.physical_evidence,
                )
            )
            packages[proposal.action.action_digest] = package
        return packages

    def _coordination_latency(self, values: ReferenceDecisionInput) -> int:
        if values.coordination_latency_s is not None:
            return values.coordination_latency_s
        delivery = next(
            item
            for item in self.dependencies.scenario.coordination.public.deliveries
            if item.evidence_id == values.envelope.envelope_id
            and item.recipient_authority_id == values.controller_authority_id
            and item.delivered_at_s <= values.at_s
        )
        return delivery.delivered_at_s - delivery.source_available_at_s

    def _environment_beliefs(self, at_s: int) -> tuple[PublicEnvironmentBelief, ...]:
        sample = self.dependencies.index.physical_at(at_s)
        evidence_id = f"reference-environment-{decision_digest({'at_s': sample.at_s})[:20]}"
        values = [
            PublicEnvironmentBelief(
                belief_id=f"belief-weather-{sample.at_s}",
                kind="weather",
                entity_id="reference-weather",
                value=(
                    f"rain={sample.weather.effective_rain_milli_in_per_hour};"
                    f"wind={sample.weather.wind_milli_knots};"
                    f"air={sample.weather.air_operability}"
                ),
                observed_at_s=sample.at_s,
                evidence_id=evidence_id,
            )
        ]
        values.extend(
            PublicEnvironmentBelief(
                belief_id=f"belief-gauge-{item.gauge_id}-{sample.at_s}",
                kind="gauge",
                entity_id=item.gauge_id,
                value=f"stage_millifeet={item.stage_milli_ft};threshold={item.threshold_status}",
                observed_at_s=sample.at_s,
                evidence_id=evidence_id,
            )
            for item in sample.gauges
        )
        values.extend(
            PublicEnvironmentBelief(
                belief_id=f"belief-crossing-{item.crossing_id}-{sample.at_s}",
                kind="crossing",
                entity_id=item.crossing_id,
                value=item.status,
                observed_at_s=sample.at_s,
                evidence_id=evidence_id,
            )
            for item in sample.crossings
        )
        return tuple(sorted(values, key=lambda item: item.belief_id))

    def _validate_input(self, values: ReferenceDecisionInput) -> None:
        from trace_reference.generation import verify_reference_envelope

        reassessing = values.acquisition_outcome is not None
        self._validate_delivery_time(values, reassessing=reassessing)
        if values.at_s < 0:
            raise ValueError("Reference response decisions begin at evaluation T0")
        if values.report.call_id != values.envelope.call_id:
            raise ValueError("Reference report and envelope identifiers disagree")
        expected_authority = (
            "AUTH-01"
            if self.dependencies.scenario.coordination.public.phi == 1
            else values.envelope.initial_authority_id
        )
        if expected_authority != values.controller_authority_id:
            raise ValueError("Reference initial decision authority disagrees with coordination")
        if values.reconciliation.call_id != values.report.call_id:
            raise ValueError("Reference reconciliation step names another public report")
        if values.reconciliation.controller_authority_id != values.controller_authority_id:
            raise ValueError("Reference reconciliation authority disagrees with decision authority")
        if not verify_reference_envelope(values.report, values.envelope):
            raise ValueError("Reference report envelope authentication failed")
        if values.physical_evidence is not None and not reassessing:
            raise ValueError("Reference physical evidence requires an exact acquisition outcome")
        if reassessing != (values.reassessment_of_decision_id is not None):
            raise ValueError("Reference acquisition reassessment requires its prior decision")
        if values.acquisition_outcome is not None:
            self._validate_acquisition_outcome(values)
        if (
            values.physical_evidence is not None
            and values.physical_evidence.delivered_at_s != values.at_s
        ):
            raise ValueError("Reference acquisition reassessment must occur at evidence delivery")

    @staticmethod
    def _validate_acquisition_outcome(values: ReferenceDecisionInput) -> None:
        outcome = values.acquisition_outcome
        if outcome is None:
            raise RuntimeError("Reference acquisition reassessment lacks its outcome")
        if not verify_model_digest(outcome, digest_field="outcome_digest"):
            raise ValueError("Reference acquisition outcome digest is invalid")
        if outcome.delivered_at_s != values.at_s or outcome.ingested_at_s != values.at_s:
            raise ValueError("Reference acquisition reassessment must occur at outcome ingestion")
        if values.physical_evidence is None and (
            outcome.evidence_id is not None or outcome.outcome_status == "evidence-accepted"
        ):
            raise ValueError("Reference accepted evidence outcome lacks physical evidence")

    @staticmethod
    def _validate_delivery_time(
        values: ReferenceDecisionInput,
        *,
        reassessing: bool,
    ) -> None:
        if reassessing:
            return
        observed_latency_s = values.at_s - values.envelope.delivered_at_s
        if observed_latency_s < 0:
            raise ValueError("Reference initial decision cannot precede report delivery")
        if (
            values.coordination_latency_s is not None
            and values.coordination_latency_s != observed_latency_s
        ):
            raise ValueError("Reference initial decision has inconsistent delivery latency")

    def _validate_physical_evidence(
        self,
        values: ReferenceDecisionInput,
        routes: ReferencePublicRouteCatalog,
    ) -> None:
        evidence = values.physical_evidence
        outcome = values.acquisition_outcome
        if evidence is None or outcome is None:
            raise RuntimeError("Reference physical evidence closure is incomplete")
        if not verify_model_digest(evidence, digest_field="evidence_digest"):
            raise ValueError("Reference physical evidence digest is invalid")
        if not verify_model_digest(outcome, digest_field="outcome_digest"):
            raise ValueError("Reference acquisition outcome digest is invalid")
        if outcome.evidence_id != evidence.evidence_id:
            raise ValueError("Reference acquisition outcome names another evidence item")
        payload = ReferenceRouteVerificationPayload.model_validate_json(evidence.payload_json)
        if payload.request_id != evidence.request_id or payload.call_id != values.report.call_id:
            raise ValueError("Reference route evidence names another request or public report")
        current_resource_ids = {item.resource_id for item in routes.routes}
        observed_catalogs: dict[int, ReferencePublicRouteCatalog] = {}
        for observation in payload.observations:
            if observation.requested_resource_id not in current_resource_ids:
                raise ValueError("Reference route evidence names an absent public resource")
            route = self._route_at_observation_time(
                values.report,
                observation.requested_resource_id,
                observation.observed_at_s,
                observed_catalogs,
            )
            if route.route_plan_id != observation.observed_route_plan_id:
                raise ValueError("Reference route evidence names another observed route")
            if route.route_plan_digest != observation.observed_route_plan_digest:
                raise ValueError("Reference route evidence route digest is invalid")
            if route.status.value != observation.observed_status:
                raise ValueError("Reference route evidence status disagrees with public state")

    def _route_at_observation_time(
        self,
        report: ReferenceRawReport,
        resource_id: str,
        observed_at_s: int,
        catalog_cache: dict[int, ReferencePublicRouteCatalog],
    ) -> ReferencePublicRoutePlan:
        catalog = catalog_cache.get(observed_at_s)
        if catalog is None:
            catalog = self.dependencies.route_service.build_catalog(
                report,
                self.dependencies.scenario.resources.public_catalog,
                at_s=observed_at_s,
            )
            catalog_cache[observed_at_s] = catalog
        route = next((item for item in catalog.routes if item.resource_id == resource_id), None)
        if route is None:
            raise ValueError("Reference route evidence names an absent public resource")
        return route
