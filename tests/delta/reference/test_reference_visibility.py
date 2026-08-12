from __future__ import annotations

from trace_jepa.predictor import ToyActionPrefixPredictor
from trace_reference.decision.visibility import (
    SnapshotInput,
    build_controller_visible_snapshot,
)
from trace_reference.domain.coordination import (
    ReferenceCoordinationDelivery,
    ReferencePublicCoordinationScenario,
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


def _snapshot(*, delivered_ids: frozenset[str]):
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
            at_s=1_000,
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
        ),
        telemetry,
        catalog,
        coordination,
        ToyActionPrefixPredictor().provenance(),
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
