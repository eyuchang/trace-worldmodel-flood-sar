"""One complete non-LEAP Reference decision through TRACE closure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trace_jepa.predictor import ActionPrefixPredictor
from trace_reference.decision import (
    CostDeltaInput,
    DecisionManifestInput,
    EvidenceAcquisitionExecutor,
    build_cost_delta,
    build_decision_manifest,
)
from trace_reference.decision.canonical import decision_digest
from trace_reference.decision.domain import (
    BaseSelectionRequest,
    ControllerVisibleSnapshot,
    PhysicalActionProposal,
    ProposalRequest,
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
    ReferenceEventType,
    ReferenceMissionDecision,
    ReferenceRawReport,
    ReferenceReportEnvelope,
    ReferenceScenarioArtifacts,
)
from trace_reference.domain.observations import ReferenceAuthorityId
from trace_reference.domain.routing import ReferencePublicRouteCatalog
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


class ReferenceDecisionEngine:
    """Execute the base selector path; it has no LEAP scoring or search behavior."""

    def __init__(self, dependencies: ReferenceDecisionEngineDependencies) -> None:
        self.dependencies = dependencies

    def execute(self, values: ReferenceDecisionInput) -> ReferenceDecisionExecution:
        self._validate_input(values)
        snapshot = build_controller_visible_snapshot(
            SnapshotInput(
                mission_id="reference-mission-development-v1",
                decision_id=f"reference-decision-{values.envelope.envelope_id}",
                controller_authority_id=values.controller_authority_id,
                at_s=values.at_s,
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
        )
        routes = self.dependencies.route_service.build_catalog(
            values.report,
            self.dependencies.scenario.resources.public_catalog,
            at_s=values.at_s,
        )
        request = ProposalRequest(
            schema_version="delta-reference-proposal-request-v1",
            decision_id=snapshot.decision_id,
            public_snapshot_digest=snapshot.snapshot_digest,
            target_public_incident_id=values.reconciliation.belief_cluster_id,
            public_taxonomy=values.report.taxonomy.value,
            route_catalog=routes,
            decision_deadline_s=min(345_600, values.at_s + 3_600),
            policy_version=self.dependencies.policy_version,
            proposal_namespace="reference-public-proposal-grammar-v1",
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
        assessments = {}
        assessment_inputs = {}
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
            assessment_inputs[action_digest] = assessment_input
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
                post_delay_trace_record_id=trace_record_id,
                post_delay_trace_record_version=trace_record_version,
                commitment_envelope_digest=(
                    commitment.envelope_digest if commitment is not None else None
                ),
            )
        )
        body = {
            "schema_version": "delta-reference-mission-decision-v1",
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
        }
        result = ReferenceMissionDecision(**body, decision_digest=decision_digest(body))
        self.dependencies.event_log.append_public_artifact(
            at_s=values.at_s,
            event_type=ReferenceEventType.DECISION_MANIFEST_RECORDED,
            artifact_id=result.decision_id,
            artifact_schema_version=result.schema_version,
            artifact={
                "decision": result.model_dump(mode="json"),
                "manifest": manifest.model_dump(mode="json"),
            },
        )
        return ReferenceDecisionExecution(
            result=result,
            reconciliation=values.reconciliation,
            proposals=proposals,
            assessments=tuple(assessments[key] for key in sorted(assessments)),
            eligibility=eligibility,
            catalog=catalog,
            selection=selection,
            commitment=commitment,
            acquisition_request=acquisition_request,
            manifest=manifest,
        )

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
                )
            )
            packages[proposal.action.action_digest] = package
        return packages

    def _coordination_latency(self, values: ReferenceDecisionInput) -> int:
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

        if values.at_s != values.envelope.delivered_at_s:
            raise ValueError("Reference initial decision must occur at authenticated delivery")
        if values.at_s < 0:
            raise ValueError("Reference response decisions begin at evaluation T0")
        if values.report.call_id != values.envelope.call_id:
            raise ValueError("Reference report and envelope identifiers disagree")
        if values.envelope.initial_authority_id != values.controller_authority_id:
            raise ValueError("Reference initial decision authority disagrees with envelope")
        if values.reconciliation.call_id != values.report.call_id:
            raise ValueError("Reference reconciliation step names another public report")
        if values.reconciliation.controller_authority_id != values.controller_authority_id:
            raise ValueError("Reference reconciliation authority disagrees with decision authority")
        if not verify_reference_envelope(values.report, values.envelope):
            raise ValueError("Reference report envelope authentication failed")
