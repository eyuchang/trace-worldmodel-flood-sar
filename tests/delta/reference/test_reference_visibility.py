from __future__ import annotations

import hashlib

from trace_jepa.predictor import ToyActionPrefixPredictor
from trace_jepa.support import canonical_json_bytes
from trace_reference.decision.visibility import (
    SnapshotInput,
    build_controller_visible_snapshot,
)
from trace_reference.domain.coordination import (
    ReferenceCoordinationDelivery,
    ReferencePublicCoordinationScenario,
    ReferenceResourceActivationEvent,
    ReferenceResourceActivationPhase,
    ReferenceResourceActivationSchedule,
)
from trace_reference.domain.resources import (
    ReferenceMutualAidTier,
    ReferencePublicResourceCatalog,
    ReferencePublicResourceDefinition,
    ReferencePublicResourceTelemetryScenario,
    ReferenceResourceCapability,
    ReferenceResourceClass,
    ReferenceResourceState,
    ReferenceResourceTelemetry,
)


def _activation_schedule(resource_id: str) -> ReferenceResourceActivationSchedule:
    phases = tuple(ReferenceResourceActivationPhase)
    events = []
    predecessor = None
    for index, phase in enumerate(phases, start=1):
        event_body = {
            "schema_version": "delta-reference-resource-activation-event-v1",
            "event_id": f"RME-{index:016x}",
            "activation_id": "RMA-0000000000000001",
            "resource_id": resource_id,
            "tier": "T0-local",
            "phase": phase.value,
            "observed_at_s": 890 + index * 10,
            "delivered_at_s": 890 + index * 10,
            "requesting_authority_id": "AUTH-01",
            "approving_authority_id": "AUTH-01",
            "recipient_authority_id": "AUTH-01",
            "reported_state": (
                "awaiting-request",
                "activation-approved",
                "mobilizing",
                "in-transit",
                "arrived-awaiting-availability",
                "available-staged",
            )[index - 1],
            "predecessor_event_id": predecessor,
        }
        event = ReferenceResourceActivationEvent(
            **event_body,
            event_digest=hashlib.sha256(canonical_json_bytes(event_body)).hexdigest(),
        )
        events.append(event)
        predecessor = event.event_id
    schedule_body = {
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "schema_version": "delta-reference-resource-activation-schedule-v1",
        "parameter_version": "delta-reference-activation-parameters-v1",
        "scientific_status": ("development-synthetic-role-workflow-not-legal-or-operational-claim"),
        "resource_catalog_digest": "1" * 64,
        "seed": 1,
        "phi": 1,
        "events": [item.model_dump(mode="json") for item in events],
    }
    return ReferenceResourceActivationSchedule(
        **schedule_body,
        schedule_digest=hashlib.sha256(canonical_json_bytes(schedule_body)).hexdigest(),
    )


def _snapshot(
    *,
    delivered_ids: frozenset[str],
    delivered_activation_ids: frozenset[str] = frozenset(),
    at_s: int = 1_000,
):
    resource = ReferencePublicResourceDefinition(
        resource_id="RR-0000000000000001",
        resource_class=ReferenceResourceClass.TYPE_I_ENGINE,
        capabilities=(ReferenceResourceCapability.WELFARE_CHECK,),
        service_units=2,
        physical_capacity=0,
        home_base_id="BASE-TEST",
        staged_node_id="ISL-01",
        owning_authority_id="AUTH-01",
        tier=ReferenceMutualAidTier.T0_LOCAL,
        nominal_travel_s=600,
        constraints=("road-route-required",),
    )
    catalog = ReferencePublicResourceCatalog(
        scenario_id="WF-DFLD-01-REFERENCE",
        schema_version="delta-reference-resource-catalog-v1",
        scientific_status="synthetic-planning-roster-not-current-inventory-claim",
        resources=(resource,),
        resource_catalog_digest="1" * 64,
    )
    telemetry_item = ReferenceResourceTelemetry(
        telemetry_id="RT-0000000000000001",
        resource_id=resource.resource_id,
        observed_at_s=900,
        delivered_at_s=900,
        owning_authority_id="AUTH-01",
        reported_state=ReferenceResourceState.AVAILABLE_STAGED,
        reported_crew_fatigue_band="low",
        reported_fuel_or_charge_band="full",
    )
    telemetry = ReferencePublicResourceTelemetryScenario(
        scenario_id="WF-DFLD-01-REFERENCE",
        schema_version="delta-reference-resource-telemetry-v1",
        seed=1,
        iota_micros=700_000,
        telemetry=(telemetry_item,),
        telemetry_digest="2" * 64,
    )
    delivery = ReferenceCoordinationDelivery(
        delivery_id="CD-0000000000000001",
        evidence_kind="resource-telemetry",
        evidence_id=telemetry_item.telemetry_id,
        source_authority_id="AUTH-01",
        recipient_authority_id="AUTH-01",
        recipient_partition_id="AUTH-01-P01",
        source_available_at_s=900,
        delivered_at_s=900,
        source_content_digest="3" * 64,
    )
    coordination = ReferencePublicCoordinationScenario(
        scenario_id="WF-DFLD-01-REFERENCE",
        schema_version="delta-reference-coordination-v1",
        seed=1,
        phi=4,
        authority_registry_version="delta-reference-governance-v1",
        deliveries=(delivery,),
        public_coordination_digest="4" * 64,
    )
    return build_controller_visible_snapshot(
        SnapshotInput(
            mission_id="reference-visibility-test",
            decision_id="reference-visibility-decision",
            controller_authority_id="AUTH-01",
            at_s=at_s,
            delivered_coordination_ids=delivered_ids,
            evidence_prefix_digest="GENESIS",
            trace_prefix_digest="GENESIS",
            commitment_prefix_digest="GENESIS",
            environment_beliefs=(),
            active_commitments=(),
            known_outcomes=(),
            prior_profile_id="reference-prior-pi-v1",
            policy_version="reference-visibility-policy-v1",
            environment_contract_version="reference-development-environment-v1",
            delivered_activation_event_ids=delivered_activation_ids,
        ),
        telemetry,
        catalog,
        coordination,
        ToyActionPrefixPredictor().provenance(),
        _activation_schedule(resource.resource_id),
    )


def test_snapshot_uses_durable_inbox_not_planned_delivery_schedule() -> None:
    before_acceptance = _snapshot(delivered_ids=frozenset())
    after_acceptance = _snapshot(delivered_ids=frozenset({"CD-0000000000000001"}))

    assert before_acceptance.delivered_coordination_ids == ()
    assert before_acceptance.resource_beliefs == ()
    assert after_acceptance.delivered_coordination_ids == ("CD-0000000000000001",)
    assert tuple(item.resource_id for item in after_acceptance.resource_beliefs) == (
        "RR-0000000000000001",
    )


def test_snapshot_uses_only_durably_delivered_activation_phase() -> None:
    telemetry_only = _snapshot(
        delivered_ids=frozenset({"CD-0000000000000001"}),
        at_s=925,
    )
    through_mobilized = _snapshot(
        delivered_ids=frozenset({"CD-0000000000000001"}),
        delivered_activation_ids=frozenset(
            {
                "RME-0000000000000001",
                "RME-0000000000000002",
                "RME-0000000000000003",
            }
        ),
        at_s=925,
    )

    assert telemetry_only.resource_beliefs[0].reported_state == "available-staged"
    activation_belief = through_mobilized.resource_beliefs[0]
    assert activation_belief.reported_state == "mobilizing"
    assert activation_belief.availability_evidence_id == "RME-0000000000000003"


def test_authority_evidence_is_latest_bounded_delivery() -> None:
    snapshot = _snapshot(delivered_ids=frozenset({"CD-0000000000000001"}))

    assert len(snapshot.authority_evidence) == 1
    assert snapshot.authority_evidence[0].coordination_delivery_ids == ("CD-0000000000000001",)
