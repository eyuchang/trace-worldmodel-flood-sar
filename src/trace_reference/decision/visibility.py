"""Allowlist-only construction of immutable controller-visible snapshots."""

from __future__ import annotations

from dataclasses import dataclass

from trace_jepa.predictor import PredictorProvenance
from trace_reference.domain.coordination import (
    ReferencePublicCoordinationScenario,
    ReferenceResourceActivationEvent,
    ReferenceResourceActivationSchedule,
)
from trace_reference.domain.observations import ReferenceAuthorityId
from trace_reference.domain.resources import (
    ReferencePublicResourceCatalog,
    ReferencePublicResourceTelemetryScenario,
    ReferenceResourceTelemetry,
)

from .canonical import decision_digest
from .domain import (
    ControllerVisibleSnapshot,
    PublicAuthorityEvidence,
    PublicCommitmentBelief,
    PublicEnvironmentBelief,
    PublicOutcomeBelief,
    PublicResourceBelief,
)


@dataclass(frozen=True)
class SnapshotInput:
    mission_id: str
    decision_id: str
    controller_authority_id: ReferenceAuthorityId
    at_s: int
    delivered_coordination_ids: frozenset[str]
    evidence_prefix_digest: str
    trace_prefix_digest: str
    commitment_prefix_digest: str
    environment_beliefs: tuple[PublicEnvironmentBelief, ...]
    active_commitments: tuple[PublicCommitmentBelief, ...]
    known_outcomes: tuple[PublicOutcomeBelief, ...]
    prior_profile_id: str
    policy_version: str
    environment_contract_version: str
    delivered_activation_event_ids: frozenset[str] = frozenset()


def _controlling_resource_evidence(
    telemetry_item: ReferenceResourceTelemetry | None,
    activation_item: ReferenceResourceActivationEvent | None,
) -> tuple[str, int, str] | None:
    """Choose the public state source without letting placeholder telemetry undo activation."""

    if telemetry_item is None and activation_item is None:
        return None
    if activation_item is None:
        item = telemetry_item
        assert item is not None
        return item.reported_state.value, item.observed_at_s, item.telemetry_id
    if telemetry_item is None:
        return (
            activation_item.reported_state.value,
            activation_item.observed_at_s,
            activation_item.event_id,
        )
    adverse_states = {"crew-rest", "initial-outage"}
    telemetry_is_current_adverse = (
        telemetry_item.reported_state.value in adverse_states
        and telemetry_item.observed_at_s >= activation_item.observed_at_s
    )
    telemetry_is_current_post_activation = (
        activation_item.reported_state.value == "available-staged"
        and telemetry_item.reported_state.value != "awaiting-request"
        and telemetry_item.observed_at_s >= activation_item.observed_at_s
    )
    if telemetry_is_current_adverse or telemetry_is_current_post_activation:
        return (
            telemetry_item.reported_state.value,
            telemetry_item.observed_at_s,
            telemetry_item.telemetry_id,
        )
    return (
        activation_item.reported_state.value,
        activation_item.observed_at_s,
        activation_item.event_id,
    )


def _latest_resource_beliefs(
    telemetry: ReferencePublicResourceTelemetryScenario,
    resources: ReferencePublicResourceCatalog,
    activations: ReferenceResourceActivationSchedule | None,
    *,
    at_s: int,
    delivered_telemetry_ids: frozenset[str],
    delivered_activation_event_ids: frozenset[str],
) -> tuple[PublicResourceBelief, ...]:
    resource_by_id = {item.resource_id: item for item in resources.resources}
    latest_telemetry: dict[str, ReferenceResourceTelemetry] = {}
    for telemetry_item in telemetry.telemetry:
        if (
            telemetry_item.delivered_at_s <= at_s
            and telemetry_item.telemetry_id in delivered_telemetry_ids
        ):
            latest_telemetry[telemetry_item.resource_id] = telemetry_item
    latest_activation: dict[str, ReferenceResourceActivationEvent] = {}
    if activations is not None:
        for activation_item in activations.events:
            if (
                activation_item.delivered_at_s <= at_s
                and activation_item.event_id in delivered_activation_event_ids
            ):
                latest_activation[activation_item.resource_id] = activation_item
    beliefs = []
    for resource_id in sorted(set(latest_telemetry) | set(latest_activation)):
        public_resource = resource_by_id[resource_id]
        evidence = _controlling_resource_evidence(
            latest_telemetry.get(resource_id),
            latest_activation.get(resource_id),
        )
        if evidence is None:
            continue
        reported_state, observed_at_s, evidence_id = evidence
        beliefs.append(
            PublicResourceBelief(
                resource_id=resource_id,
                resource_class=public_resource.resource_class.value,
                capabilities=tuple(item.value for item in public_resource.capabilities),
                service_units=public_resource.service_units,
                reported_state=reported_state,
                owning_authority_id=public_resource.owning_authority_id,
                staged_node_id=public_resource.staged_node_id,
                observed_at_s=observed_at_s,
                availability_evidence_id=evidence_id,
            )
        )
    return tuple(sorted(beliefs, key=lambda item: item.resource_id))


def build_controller_visible_snapshot(
    request: SnapshotInput,
    telemetry: ReferencePublicResourceTelemetryScenario,
    resources: ReferencePublicResourceCatalog,
    coordination: ReferencePublicCoordinationScenario,
    predictor: PredictorProvenance,
    activations: ReferenceResourceActivationSchedule | None = None,
) -> ControllerVisibleSnapshot:
    """Project only explicitly declared public inputs; no hidden object is accepted."""

    qualification_digest = predictor.qualification_artifact_sha256
    if qualification_digest is None:
        qualification_digest = "0" * 64
    delivered = tuple(
        item
        for item in coordination.deliveries
        if item.delivery_id in request.delivered_coordination_ids
        if item.recipient_authority_id == request.controller_authority_id
        and item.delivered_at_s <= request.at_s
    )
    delivered_telemetry_ids = frozenset(
        item.evidence_id for item in delivered if item.evidence_kind == "resource-telemetry"
    )
    by_source_authority: dict[str, list[str]] = {}
    for item in delivered:
        by_source_authority.setdefault(item.source_authority_id, []).append(item.delivery_id)
    body = {
        "schema_version": "delta-reference-public-snapshot-v2",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "mission_id": request.mission_id,
        "decision_id": request.decision_id,
        "at_s": request.at_s,
        "evidence_prefix_digest": request.evidence_prefix_digest,
        "trace_prefix_digest": request.trace_prefix_digest,
        "commitment_prefix_digest": request.commitment_prefix_digest,
        "environment_beliefs": [
            item.model_dump(mode="json")
            for item in sorted(request.environment_beliefs, key=lambda item: item.belief_id)
        ],
        "resource_beliefs": [
            item.model_dump(mode="json")
            for item in _latest_resource_beliefs(
                telemetry,
                resources,
                activations,
                at_s=request.at_s,
                delivered_telemetry_ids=delivered_telemetry_ids,
                delivered_activation_event_ids=request.delivered_activation_event_ids,
            )
        ],
        "delivered_coordination_ids": sorted(item.delivery_id for item in delivered),
        "authority_evidence": [
            PublicAuthorityEvidence(
                authority_id=authority_id,
                coordination_delivery_ids=tuple(sorted(delivery_ids)),
            ).model_dump(mode="json")
            for authority_id, delivery_ids in sorted(by_source_authority.items())
        ],
        "active_commitments": [
            item.model_dump(mode="json")
            for item in sorted(request.active_commitments, key=lambda item: item.commitment_id)
        ],
        "known_outcomes": [
            item.model_dump(mode="json")
            for item in sorted(request.known_outcomes, key=lambda item: item.outcome_id)
        ],
        "predictor_version": predictor.predictor_version,
        "predictor_model_hash": predictor.model_hash,
        "calibration_version": predictor.calibration_version,
        "calibration_hash": predictor.calibration_hash,
        "qualification_digest": qualification_digest,
        "prior_profile_id": request.prior_profile_id,
        "policy_version": request.policy_version,
        "environment_contract_version": request.environment_contract_version,
        "decision_extension_id": None,
    }
    return ControllerVisibleSnapshot(**body, snapshot_digest=decision_digest(body))
