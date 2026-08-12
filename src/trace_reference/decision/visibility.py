"""Allowlist-only construction of immutable controller-visible snapshots."""

from __future__ import annotations

from dataclasses import dataclass

from trace_jepa.predictor import PredictorProvenance
from trace_reference.domain.coordination import ReferencePublicCoordinationScenario
from trace_reference.domain.resources import (
    ReferencePublicResourceTelemetryScenario,
    ReferenceResourceTruth,
)

from .canonical import decision_digest
from .domain import (
    ControllerVisibleSnapshot,
    PublicCommitmentBelief,
    PublicEnvironmentBelief,
    PublicOutcomeBelief,
    PublicResourceBelief,
)


@dataclass(frozen=True)
class SnapshotInput:
    mission_id: str
    decision_id: str
    at_s: int
    evidence_prefix_digest: str
    trace_prefix_digest: str
    commitment_prefix_digest: str
    environment_beliefs: tuple[PublicEnvironmentBelief, ...]
    active_commitments: tuple[PublicCommitmentBelief, ...]
    known_outcomes: tuple[PublicOutcomeBelief, ...]
    prior_profile_id: str
    policy_version: str
    environment_contract_version: str


def _latest_resource_beliefs(
    telemetry: ReferencePublicResourceTelemetryScenario,
    resources: tuple[ReferenceResourceTruth, ...],
    *,
    at_s: int,
) -> tuple[PublicResourceBelief, ...]:
    resource_by_id = {item.resource_id: item for item in resources}
    latest = {}
    for item in telemetry.telemetry:
        if item.delivered_at_s <= at_s:
            latest[item.resource_id] = item
    beliefs = (
        PublicResourceBelief(
            resource_id=resource_id,
            resource_class=resource_by_id[resource_id].resource_class.value,
            capabilities=tuple(item.value for item in resource_by_id[resource_id].capabilities),
            service_units=resource_by_id[resource_id].service_units,
            reported_state=item.reported_state.value,
            owning_authority_id=item.owning_authority_id,
            staged_node_id=resource_by_id[resource_id].staged_node_id,
            observed_at_s=item.observed_at_s,
            telemetry_id=item.telemetry_id,
        )
        for resource_id, item in latest.items()
    )
    return tuple(sorted(beliefs, key=lambda item: item.resource_id))


def build_controller_visible_snapshot(
    request: SnapshotInput,
    telemetry: ReferencePublicResourceTelemetryScenario,
    resources: tuple[ReferenceResourceTruth, ...],
    coordination: ReferencePublicCoordinationScenario,
    predictor: PredictorProvenance,
) -> ControllerVisibleSnapshot:
    """Project only explicitly declared public inputs; no hidden object is accepted."""

    qualification_digest = predictor.qualification_artifact_sha256
    if qualification_digest is None:
        qualification_digest = "0" * 64
    body = {
        "schema_version": "delta-reference-public-snapshot-v1",
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
            for item in _latest_resource_beliefs(telemetry, resources, at_s=request.at_s)
        ],
        "delivered_coordination_ids": sorted(
            item.delivery_id
            for item in coordination.deliveries
            if item.delivered_at_s <= request.at_s
        ),
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
