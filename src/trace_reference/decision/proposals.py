"""Deterministic complete proposal enumeration for the declared public grammar."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from trace_reference.domain.routing import ReferencePublicRoutePlan, ReferenceRouteStatus

from .canonical import decision_digest, verify_model_digest
from .domain import (
    ControllerVisibleSnapshot,
    CostAmount,
    EvidenceAcquisitionOffer,
    PhysicalActionProposal,
    ProposalEnumerationReceipt,
    ProposalRequest,
    ProposalSet,
    PublicResourceBelief,
    ReferenceActionSpec,
    SafeAlternativeProposal,
)

_ACTION_BY_TAXONOMY = {
    "C-STR": ("dispatch_rescue_boat", "water-rescue", "high", False),
    "C-VEH": ("deploy_ground_team", "road-rescue", "high", False),
    "C-LEV": ("inspect_levee", "levee-inspection", "moderate", True),
    "C-MED": ("deploy_ground_team", "medical-transport", "high", False),
    "C-WEL": ("perform_welfare_check", "welfare-check", "moderate", True),
    "C-MIS": ("perform_welfare_check", "missing-person-search", "high", False),
    "C-ANI": ("dispatch_rescue_boat", "animal-rescue", "moderate", True),
    "C-INF": ("perform_welfare_check", "public-information", "low", True),
    "C-HAZ": ("inspect_levee", "hazard-control", "moderate", True),
}


@dataclass(frozen=True)
class _ActionParts:
    resource_id: str | None
    crew_id: str | None
    origin: str | None
    action_class: str
    capability: str
    service_duration_s: int
    suffix: str


def _id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256("|".join(str(item) for item in parts).encode()).hexdigest()
    return f"{prefix}-{digest[:20]}"


def _action(
    request: ProposalRequest,
    *,
    parts: _ActionParts,
    route: ReferencePublicRoutePlan,
) -> ReferenceActionSpec:
    body = {
        "action_id": _id("reference-action", request.decision_id, parts.suffix),
        "action_class": parts.action_class,
        "actor_resource_id": parts.resource_id,
        "actor_crew_id": parts.crew_id,
        "origin_node_id": parts.origin,
        "destination_public_id": request.target_public_incident_id,
        "route_id": route.route_plan_id,
        "route_plan_digest": route.route_plan_digest,
        "route_crossing_ids": route.crossing_ids,
        "focal_crossing_id": route.focal_crossing_id,
        "route_gauge_id": route.gauge_id,
        "routed_travel_s": route.estimated_travel_s,
        "route_status_at_proposal": route.status.value,
        "required_capability": parts.capability,
        "execution_not_before_s": max(-172_800, request.decision_deadline_s - 900),
        "execution_not_after_s": request.decision_deadline_s,
        "commitment_horizon_end_s": (
            request.decision_deadline_s + (route.estimated_travel_s or 0) + parts.service_duration_s
        ),
        "deterministic_service_duration_s": parts.service_duration_s,
    }
    return ReferenceActionSpec(**body, action_digest=decision_digest(body))


def _physical_proposals(
    request: ProposalRequest,
    snapshot: ControllerVisibleSnapshot,
) -> tuple[PhysicalActionProposal, ...]:
    if request.public_taxonomy not in _ACTION_BY_TAXONOMY:
        return ()
    action_class, capability, consequence, reversible = _ACTION_BY_TAXONOMY[request.public_taxonomy]
    route_by_resource = {item.resource_id: item for item in request.route_catalog.routes}
    active_resource_ids = {item.resource_id for item in snapshot.active_commitments}
    capability_compatible = [
        item
        for item in snapshot.resource_beliefs
        if capability in item.capabilities
        and item.reported_state == "available-staged"
        and item.resource_id not in active_resource_ids
    ]
    compatible = [
        item
        for item in capability_compatible
        if route_by_resource[item.resource_id].status != ReferenceRouteStatus.UNAVAILABLE
    ]
    canonical_by_equivalence: dict[tuple[str, str, int], PublicResourceBelief] = {}
    for item in compatible:
        key = (item.resource_class, item.staged_node_id, item.service_units)
        canonical_by_equivalence.setdefault(key, item)
    proposals = []
    for item in canonical_by_equivalence.values():
        route = route_by_resource[item.resource_id]
        authority_evidence = next(
            (
                evidence.coordination_delivery_ids
                for evidence in snapshot.authority_evidence
                if evidence.authority_id == item.owning_authority_id
            ),
            (),
        )
        action = _action(
            request,
            parts=_ActionParts(
                item.resource_id,
                f"public-crew-for-{item.resource_id}",
                item.staged_node_id,
                action_class,
                capability,
                3_600,
                item.resource_id,
            ),
            route=route,
        )
        request_digest = decision_digest(
            {"snapshot": snapshot.snapshot_digest, "action": action.action_digest}
        )
        body = {
            "proposal_id": _id("proposal", request.decision_id, action.action_id),
            "proposal_kind": "physical-action",
            "action": action.model_dump(mode="json"),
            "consequence_class": consequence,
            "reversible": reversible,
            "authority_requirement": item.owning_authority_id,
            "current_authority_evidence_ids": authority_evidence,
            "required_claim_ids": (f"claim-{request.target_public_incident_id}",),
            "dependency_ids": (),
            "predictor_request_digest": request_digest,
            "predictor_evidence_digest": decision_digest(
                {"request": request_digest, "role": "pre-assessment-placeholder"}
            ),
        }
        proposals.append(PhysicalActionProposal(**body, proposal_digest=decision_digest(body)))
    return tuple(sorted(proposals, key=lambda item: item.proposal_id))


def _safe_alternatives(
    request: ProposalRequest,
    snapshot: ControllerVisibleSnapshot,
) -> tuple[SafeAlternativeProposal, ...]:
    route_by_resource = {item.resource_id: item for item in request.route_catalog.routes}
    active_resource_ids = {item.resource_id for item in snapshot.active_commitments}
    candidate = next(
        (
            item
            for item in snapshot.resource_beliefs
            if "public-information" in item.capabilities
            and item.reported_state == "available-staged"
            and item.resource_id not in active_resource_ids
            and route_by_resource[item.resource_id].status != ReferenceRouteStatus.UNAVAILABLE
        ),
        None,
    )
    if candidate is None:
        return ()
    authority_evidence = next(
        (
            evidence.coordination_delivery_ids
            for evidence in snapshot.authority_evidence
            if evidence.authority_id == candidate.owning_authority_id
        ),
        (),
    )
    action = _action(
        request,
        parts=_ActionParts(
            candidate.resource_id,
            f"public-crew-for-{candidate.resource_id}",
            candidate.staged_node_id,
            "perform_welfare_check",
            "public-information",
            1_800,
            "safe-alternative",
        ),
        route=route_by_resource[candidate.resource_id],
    )
    request_digest = decision_digest(
        {"snapshot": snapshot.snapshot_digest, "action": action.action_digest}
    )
    body = {
        "proposal_id": _id("proposal-safe", request.decision_id),
        "proposal_kind": "safe-alternative",
        "action": action.model_dump(mode="json"),
        "consequence_class": "low",
        "reversible": True,
        "authority_requirement": candidate.owning_authority_id,
        "current_authority_evidence_ids": authority_evidence,
        "required_claim_ids": (f"claim-{request.target_public_incident_id}",),
        "dependency_ids": (),
        "predictor_request_digest": request_digest,
        "predictor_evidence_digest": decision_digest(
            {"request": request_digest, "role": "safe-alternative-pre-assessment"}
        ),
    }
    return (SafeAlternativeProposal(**body, proposal_digest=decision_digest(body)),)


def _acquisition_offers(
    request: ProposalRequest,
    snapshot: ControllerVisibleSnapshot,
) -> tuple[EvidenceAcquisitionOffer, ...]:
    uncertain_routes = tuple(
        item for item in request.route_catalog.routes if item.status == ReferenceRouteStatus.UNKNOWN
    )
    if not uncertain_routes:
        return ()
    provider_available = any(
        "reconnaissance" in item.capabilities and item.reported_state == "available-staged"
        for item in snapshot.resource_beliefs
    )
    cost = CostAmount(
        cost_id=_id("cost", request.decision_id, "route-verification"),
        quantity_microunits=120_000,
        unit="reference-decision-cost-microunits",
        schedule_version="reference-decision-cost-schedule-v1",
    )
    provenance = decision_digest(
        {
            "channel": "reference-physical-route-verification-v1",
            "cost": cost.model_dump(mode="json"),
            "snapshot": snapshot.snapshot_digest,
            "route_catalog": request.route_catalog.route_catalog_digest,
        }
    )
    body = {
        "schema_version": "delta-reference-evidence-acquisition-offer-v2",
        "proposal_id": _id("proposal-acquire", request.decision_id),
        "proposal_kind": "evidence-acquisition",
        "offer_id": _id("offer", request.decision_id, "route-verification"),
        "channel_id": "reference-physical-route-verification-v1",
        "target_claim_ids": (f"claim-{request.target_public_incident_id}",),
        "target_call_id": request.route_catalog.call_id,
        "target_resource_ids": tuple(item.resource_id for item in uncertain_routes),
        "target_route_plan_ids": tuple(item.route_plan_id for item in uncertain_routes),
        "route_catalog_digest": request.route_catalog.route_catalog_digest,
        "evidence_schema_version": "reference-route-evidence-v1",
        "clear_probability_micros": 780_000,
        "required_clear_probability_micros": 700_000,
        "value_of_information_microunits": 260_000,
        "physical_cost": cost.model_dump(mode="json"),
        "requested_at_s": snapshot.at_s,
        "expected_latency_s": 600,
        "latest_useful_delivery_s": request.decision_deadline_s,
        "provider_id": "reference-route-verification-provider-v1",
        "provider_available": provider_available,
        "authority_present": bool(snapshot.delivered_coordination_ids),
        "minimum_interval_clear": True,
        "no_pending_request": request.acquisition_allowed,
        "provenance_digest": provenance,
    }
    return (EvidenceAcquisitionOffer(**body, proposal_digest=decision_digest(body)),)


def propose_reference_actions(
    request: ProposalRequest,
    snapshot: ControllerVisibleSnapshot,
) -> ProposalSet:
    """Enumerate the complete finite grammar, with policy-independent deduplication."""

    if request.public_snapshot_digest != snapshot.snapshot_digest:
        raise ValueError("Reference proposal request does not bind the supplied snapshot")
    if not verify_model_digest(snapshot, digest_field="snapshot_digest"):
        raise ValueError("Reference public snapshot digest is invalid")
    if not verify_model_digest(request.route_catalog, digest_field="route_catalog_digest"):
        raise ValueError("Reference route catalog digest is invalid")
    snapshot_resource_ids = {item.resource_id for item in snapshot.resource_beliefs}
    route_resource_ids = {item.resource_id for item in request.route_catalog.routes}
    if not snapshot_resource_ids.issubset(route_resource_ids):
        raise ValueError("Reference route catalog omits a visible resource")
    physical = _physical_proposals(request, snapshot)
    acquisitions = _acquisition_offers(request, snapshot)
    safe = _safe_alternatives(request, snapshot)
    total = len(physical) + len(acquisitions) + len(safe)
    unsupported = total > 256
    capability = _ACTION_BY_TAXONOMY.get(request.public_taxonomy, (None, None, None, None))[1]
    capability_compatible_count = (
        sum(
            capability in item.capabilities and item.reported_state == "available-staged"
            for item in snapshot.resource_beliefs
        )
        if capability is not None
        else 0
    )
    route_by_resource = {item.resource_id: item for item in request.route_catalog.routes}
    route_unavailable_count = (
        sum(
            capability in item.capabilities
            and item.reported_state == "available-staged"
            and route_by_resource[item.resource_id].status == ReferenceRouteStatus.UNAVAILABLE
            for item in snapshot.resource_beliefs
        )
        if capability is not None
        else 0
    )
    request_digest = decision_digest(request.model_dump(mode="json"))
    receipt_body = {
        "grammar_version": request.proposal_namespace,
        "request_digest": request_digest,
        "public_snapshot_digest": snapshot.snapshot_digest,
        "generated_count": total,
        "capability_compatible_count": capability_compatible_count,
        "route_unavailable_count": route_unavailable_count,
        "semantic_deduplication_count": (
            capability_compatible_count - route_unavailable_count - len(physical)
        ),
        "complete_for_declared_grammar": not unsupported,
        "unsupported_cardinality": unsupported,
    }
    receipt = ProposalEnumerationReceipt(
        **receipt_body, receipt_digest=decision_digest(receipt_body)
    )
    body = {
        "schema_version": "delta-reference-proposal-set-v1",
        "decision_id": request.decision_id,
        "physical_actions": [item.model_dump(mode="json") for item in physical],
        "acquisition_offers": [item.model_dump(mode="json") for item in acquisitions],
        "safe_alternatives": [item.model_dump(mode="json") for item in safe],
        "enumeration_receipt": receipt.model_dump(mode="json"),
    }
    return ProposalSet(**body, proposal_set_digest=decision_digest(body))
