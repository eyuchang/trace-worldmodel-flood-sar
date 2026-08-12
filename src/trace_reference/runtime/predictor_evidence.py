"""Build complete predictor requests from controller-visible Reference evidence."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from trace_jepa.contracts import (
    Claim,
    ClaimLayer,
    PlanCandidate,
    PlanPrediction,
    WorldModelEvidence,
)
from trace_jepa.experimental import build_experimental_profile
from trace_jepa.predictor import (
    ActionPrefixPredictor,
    PredictorContext,
    PredictorObservation,
    PredictorPriorProfile,
    PredictorRequest,
    PredictorResourceTelemetry,
    PredictorRouteObservation,
)
from trace_jepa.support import canonical_json_bytes
from trace_reference.decision.acquisition import ReferencePhysicalEvidence
from trace_reference.decision.canonical import verify_model_digest
from trace_reference.decision.domain import (
    ControllerVisibleSnapshot,
    PhysicalActionProposal,
    SafeAlternativeProposal,
)
from trace_reference.decision.evidence_binding import PredictorEvidenceBinding
from trace_reference.domain.observations import ReferenceRawReport
from trace_reference.domain.resources import ReferencePublicResourceCatalog
from trace_reference.domain.routing import ReferencePublicRouteCatalog, ReferenceRouteStatus
from trace_reference.domain.scenario import ReferencePriorProfile

from .scenario_index import ReferenceScenarioIndex
from .trace_gateway import core_action_from_proposal

ActionProposal = PhysicalActionProposal | SafeAlternativeProposal


@dataclass(frozen=True)
class ReferencePredictorEvidenceInput:
    proposal: ActionProposal
    snapshot: ControllerVisibleSnapshot
    report: ReferenceRawReport
    route_catalog: ReferencePublicRouteCatalog
    resource_catalog: ReferencePublicResourceCatalog
    prior: ReferencePriorProfile
    index: ReferenceScenarioIndex
    predictor: ActionPrefixPredictor
    at_s: int
    coordination_latency_s: int
    created_at: datetime
    physical_evidence: ReferencePhysicalEvidence | None = None


@dataclass(frozen=True)
class ReferencePredictorEvidencePackage:
    request: PredictorRequest
    prediction: PlanPrediction
    evidence: WorldModelEvidence
    claim: Claim
    binding: PredictorEvidenceBinding


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _resource_telemetry(
    values: ReferencePredictorEvidenceInput,
    required_capability: str,
) -> tuple[PredictorResourceTelemetry, ...]:
    routes = {item.resource_id: item for item in values.route_catalog.routes}
    roster = {item.resource_id: item for item in values.resource_catalog.resources}
    busy_until = {
        item.resource_id: item.active_until_s for item in values.snapshot.active_commitments
    }
    telemetry = []
    for belief in values.snapshot.resource_beliefs:
        if required_capability not in belief.capabilities:
            continue
        route = routes[belief.resource_id]
        resource = roster[belief.resource_id]
        busy = max(0, busy_until.get(belief.resource_id, 0))
        available = (
            belief.reported_state == "available-staged"
            and busy <= values.at_s
            and route.status != ReferenceRouteStatus.UNAVAILABLE
        )
        telemetry.append(
            PredictorResourceTelemetry(
                resource_id=belief.resource_id,
                resource_class=belief.resource_class,
                capabilities=belief.capabilities,
                service_units=belief.service_units,
                availability_mode=belief.reported_state,
                origin_base_id=resource.home_base_id,
                staged_base_id=belief.staged_node_id,
                route_id=route.route_plan_id,
                scheduled_available_s=0,
                busy_until_s=busy,
                currently_available=available,
                route_reachable=route.status == ReferenceRouteStatus.OPEN,
                routed_travel_s=route.estimated_travel_s,
            )
        )
    return tuple(sorted(telemetry, key=lambda item: item.resource_id))


def build_reference_predictor_evidence(
    values: ReferencePredictorEvidenceInput,
) -> ReferencePredictorEvidencePackage:
    """Bind a proposal to complete public route, weather, gauge, and resource evidence."""

    if values.at_s < 0:
        raise ValueError("Reference response decisions begin at evaluation T0")
    if values.coordination_latency_s < 0:
        raise ValueError("Reference coordination latency cannot be negative")
    if not verify_model_digest(values.proposal, digest_field="proposal_digest"):
        raise ValueError("Reference predictor proposal digest is invalid")
    if not verify_model_digest(values.route_catalog, digest_field="route_catalog_digest"):
        raise ValueError("Reference predictor route catalog digest is invalid")
    if values.route_catalog.call_id != values.report.call_id:
        raise ValueError("Reference route catalog names another report")
    route = next(
        (
            item
            for item in values.route_catalog.routes
            if item.route_plan_id == values.proposal.action.route_id
        ),
        None,
    )
    if route is None or route.route_plan_digest != values.proposal.action.route_plan_digest:
        raise ValueError("Reference action does not bind an exact public route plan")
    if route.status == ReferenceRouteStatus.UNAVAILABLE or route.estimated_travel_s is None:
        raise ValueError("Reference predictor cannot assess an unroutable physical action")

    physical = values.index.physical_at(values.at_s)
    if physical.at_s != route.sample_time_s:
        raise ValueError("Reference route and predictor physical samples disagree")
    gauge = next(item for item in physical.gauges if item.gauge_id == route.gauge_id)
    call_age = values.at_s - values.report.observed_at_s
    route_age = values.at_s - route.sample_time_s
    if call_age < 0 or route_age < 0:
        raise ValueError("Reference predictor evidence cannot come from the future")
    observation_age = max(call_age, route_age, values.coordination_latency_s)
    compatible = _resource_telemetry(values, values.proposal.action.required_capability)
    available_units = sum(item.service_units for item in compatible if item.currently_available)
    action = core_action_from_proposal(values.proposal)
    plan = PlanCandidate(
        plan_id=f"reference-plan-{values.proposal.action.action_digest[:20]}",
        name="WF-DFLD-01 Reference response action",
        actions=(action,),
        utility=1.0,
        reversible_first_action=values.proposal.reversible,
        requires_authority=values.proposal.authority_requirement is not None,
        metadata={
            "public_snapshot_digest": values.snapshot.snapshot_digest,
            "route_catalog_digest": values.route_catalog.route_catalog_digest,
            "physical_evidence_digest": (
                values.physical_evidence.evidence_digest
                if values.physical_evidence is not None
                else None
            ),
        },
    )
    request = PredictorRequest(
        plan=plan,
        observation=PredictorObservation(
            routes=[
                PredictorRouteObservation(
                    route_id=route.route_plan_id,
                    report=(
                        "unknown"
                        if route.status == ReferenceRouteStatus.UNKNOWN
                        else route.status.value
                    ),
                    nominal_travel_s=route.estimated_travel_s,
                    confidence=(0.95 if route.status != ReferenceRouteStatus.UNKNOWN else 0.50),
                    observation_age_s=route_age,
                    stage_millifeet=gauge.stage_milli_ft,
                    crossing_sample_time_s=physical.at_s,
                    gauge_id=gauge.gauge_id,
                    gauge_sample_time_s=physical.at_s,
                    gauge_threshold_status=gauge.threshold_status,
                )
            ],
            context=PredictorContext(
                simulation_time_s=values.at_s,
                rain_milli_inches_per_hour=physical.weather.effective_rain_milli_in_per_hour,
                wind_milli_knots=physical.weather.wind_milli_knots,
                available_resource_units=available_units,
                call_observation_age_s=call_age,
                coordination_latency_s=values.coordination_latency_s,
                compatible_resources=compatible,
                source_call_sha256=_digest(values.report.model_dump(mode="json")),
                prior_profile=PredictorPriorProfile(
                    profile_id=values.prior.profile_id,
                    calibration_version=values.prior.calibration_version,
                    prior_accuracy_milli=values.prior.prior_accuracy_milli,
                ),
            ),
        ),
    )
    prediction = values.predictor.predict(request)
    provenance = values.predictor.provenance()
    request_digest = _digest(request.model_dump(mode="json"))
    profile = build_experimental_profile(
        predictor_version=provenance.predictor_version,
        calibration_version=provenance.calibration_version,
        claim_family=action.action_type,
        adequacy_status=provenance.adequacy_status,
        prediction_timestamp=values.created_at,
        model_hash=provenance.model_hash,
        calibration_hash=provenance.calibration_hash,
    ).model_copy(update={"profile_id": f"profile-{values.proposal.action.action_digest[:20]}"})
    evidence_identity = _digest(
        {
            "action_digest": values.proposal.action.action_digest,
            "predictor_request_digest": request_digest,
        }
    )
    evidence_id = f"reference-evidence-{evidence_identity[:20]}"
    evidence = WorldModelEvidence(
        evidence_id=evidence_id,
        rollout_id=f"reference-rollout-{evidence_identity[20:40]}",
        encoder_version="reference-symbolic-observation-v1",
        fusion_version="reference-controller-context-v1",
        predictor_version=provenance.predictor_version,
        semantic_probe_versions=(
            "reference-route-resource-probe-v1",
            *(
                ("reference-direct-route-observation-v1",)
                if values.physical_evidence is not None
                else ()
            ),
        ),
        training_snapshot=provenance.training_snapshot,
        observation_window_hash=request_digest,
        fleet_state_hash=_digest(
            {
                "resources": [item.model_dump(mode="json") for item in compatible],
                "active_commitments": [
                    item.model_dump(mode="json") for item in values.snapshot.active_commitments
                ],
            }
        ),
        candidate_plan_id=plan.plan_id,
        action_schema_version=provenance.action_schema_version,
        rollout_horizon=prediction.rollout_horizon,
        predicted_claims=("registered compatible capacity can execute the proposed route",),
        uncertainty=prediction.uncertainty,
        model_support=prediction.model_support,
        out_of_distribution_score=prediction.out_of_distribution_score,
        rollout_consistency=1.0 - prediction.uncertainty,
        reachability_evidence={
            "route_plan_id": route.route_plan_id,
            "route_plan_digest": route.route_plan_digest,
            "route_status": route.status.value,
            "crossing_ids": route.crossing_ids,
            "focal_crossing_id": route.focal_crossing_id,
            "route_sample_time_s": route.sample_time_s,
            "gauge_id": gauge.gauge_id,
            "stage_millifeet": gauge.stage_milli_ft,
            "gauge_sample_time_s": physical.at_s,
            "gauge_threshold_status": gauge.threshold_status,
            "physical_evidence_digest": (
                values.physical_evidence.evidence_digest
                if values.physical_evidence is not None
                else None
            ),
        },
        calibration_version=provenance.calibration_version,
        assumptions=prediction.assumptions,
        observation_age_s=observation_age,
        decisively_contradicted=route.status == ReferenceRouteStatus.BLOCKED,
        created_at=values.created_at,
        experimental_profile=profile,
    )
    claim = Claim(
        claim_id=f"claim-{values.proposal.action.destination_public_id}",
        layer=ClaimLayer.PREDICTIVE,
        text="Registered compatible capacity can execute the proposed public route.",
        grounding={
            "public_incident_id": values.proposal.action.destination_public_id,
            "action_digest": values.proposal.action.action_digest,
            "route_plan_digest": route.route_plan_digest,
        },
        confidence=prediction.success_probability,
        confidence_semantics="action-prefix predictor probability under declared public inputs",
        created_at=values.created_at,
    )
    evidence_digest = _digest(evidence.model_dump(mode="json"))
    return ReferencePredictorEvidencePackage(
        request=request,
        prediction=prediction,
        evidence=evidence,
        claim=claim,
        binding=PredictorEvidenceBinding(
            action_digest=values.proposal.action.action_digest,
            predictor_request_digest=request_digest,
            predictor_evidence_digest=evidence_digest,
        ),
    )
