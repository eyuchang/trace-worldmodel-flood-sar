"""Deterministic resource roster construction for Delta Small."""

from __future__ import annotations

from dataclasses import dataclass

from trace_jepa.scenario.delta.domain import (
    DeltaScenarioConfig,
    ResourceArtifact,
    ResourceUnit,
)


@dataclass(frozen=True)
class ResourceTemplate:
    """Readable immutable source definition for one physical resource."""

    resource_id: str
    resource_class: str
    capabilities: tuple[str, ...]
    route_id: str
    passenger_capacity: int
    activation_s: int
    transit_s: int
    staging_s: int
    travel_s: int
    service_duration_s: int
    service_units: int
    availability_mode: str
    origin_base_id: str | None
    source_record_ids: tuple[str, ...]


def _local_templates(boat_count: int, engine_count: int) -> list[ResourceTemplate]:
    templates = [
        ResourceTemplate(
            resource_id=f"RES-BOAT-{index + 1:02d}",
            resource_class="flat_bottom_rescue_boat",
            capabilities=("water_rescue", "missing_person_search"),
            route_id="XNG-04",
            passenger_capacity=6,
            activation_s=index * 240,
            transit_s=0,
            staging_s=180,
            travel_s=900,
            service_duration_s=2_700,
            service_units=2,
            availability_mode="local-from-scenario-start",
            origin_base_id="FAC-FIRE-01",
            source_record_ids=("isleton-fire-department-2026-08-05",),
        )
        for index in range(boat_count)
    ]
    templates.extend(
        ResourceTemplate(
            resource_id=f"RES-ENGINE-{index + 1:02d}",
            resource_class="type_i_engine",
            capabilities=(
                "medical_first_response",
                "road_rescue",
                "welfare_check",
                "levee_inspection",
            ),
            route_id="XNG-04",
            passenger_capacity=0,
            activation_s=180 + index * 180,
            transit_s=0,
            staging_s=120,
            travel_s=720,
            service_duration_s=2_700,
            service_units=2,
            availability_mode="local-from-scenario-start",
            origin_base_id="FAC-FIRE-01",
            source_record_ids=("isleton-fire-department-2026-08-05",),
        )
        for index in range(engine_count)
    )
    return templates


def _automatic_aid_templates(count: int) -> list[ResourceTemplate]:
    templates = [
        ResourceTemplate(
            resource_id=f"RES-RV-BOAT-55-{index + 1:02d}",
            resource_class="zodiac_rescue_boat",
            capabilities=("water_rescue", "missing_person_search"),
            route_id="XNG-04",
            passenger_capacity=6,
            activation_s=2_700 + index * 240,
            transit_s=2_100,
            staging_s=600,
            travel_s=900,
            service_duration_s=2_700,
            service_units=2,
            availability_mode="preauthorized-automatic-aid-fixed-staging",
            origin_base_id="FAC-RIO-VISTA-55",
            source_record_ids=("rio-vista-fire-source-extract-v1",),
        )
        for index in range(count)
    ]
    templates.extend(
        ResourceTemplate(
            resource_id=f"RES-RV-ENGINE-55-{index + 1:02d}",
            resource_class="type_i_engine",
            capabilities=(
                "medical_first_response",
                "road_rescue",
                "welfare_check",
                "levee_inspection",
            ),
            route_id="XNG-04",
            passenger_capacity=0,
            activation_s=2_700 + index * 180,
            transit_s=1_200,
            staging_s=1_500,
            travel_s=720,
            service_duration_s=2_700,
            service_units=2,
            availability_mode="preauthorized-automatic-aid-fixed-staging",
            origin_base_id="FAC-RIO-VISTA-55",
            source_record_ids=("rio-vista-fire-source-extract-v1",),
        )
        for index in range(count)
    )
    return templates


def _resource_unit(
    template: ResourceTemplate,
    *,
    inventory_index: int,
    config: DeltaScenarioConfig,
) -> ResourceUnit:
    friction = config.axes.mu
    return ResourceUnit(
        resource_id=template.resource_id,
        resource_class=template.resource_class,
        base_id="FAC-FIRE-01",
        capabilities=template.capabilities,
        route_id=template.route_id,
        passenger_capacity=template.passenger_capacity,
        activation_time_s=round(template.activation_s * friction),
        transit_time_s=round(template.transit_s * friction),
        staging_time_s=round(template.staging_s * friction),
        nominal_travel_time_s=round(template.travel_s * friction),
        available_from_s=round(
            (template.activation_s + template.transit_s + template.staging_s) * friction
        ),
        service_duration_s=template.service_duration_s,
        service_units=template.service_units,
        is_available=config.axes.delta < max(0.08, 0.56 - 0.08 * inventory_index),
        availability_mode=template.availability_mode,
        origin_base_id=template.origin_base_id,
        source_record_ids=template.source_record_ids,
    )


def generate_resources(config: DeltaScenarioConfig) -> ResourceArtifact:
    """Generate inventory; kappa changes count and mu changes timing only."""

    boat_count = max(1, round(2 * config.axes.kappa))
    engine_count = max(1, round(2 * config.axes.kappa))
    templates = _local_templates(boat_count, engine_count)
    if config.generator_version in {
        "delta-small-generator-v6",
        "delta-small-generator-v7",
        "delta-small-generator-v8",
    }:
        templates.extend(_automatic_aid_templates(max(0, round(2 * config.axes.kappa))))
    units = [
        _resource_unit(template, inventory_index=index, config=config)
        for index, template in enumerate(templates)
    ]
    return ResourceArtifact(
        schema_version=(
            "delta-resources-v3"
            if config.generator_version
            in {
                "delta-small-generator-v6",
                "delta-small-generator-v7",
                "delta-small-generator-v8",
            }
            else "delta-resources-v2"
        ),
        capability_schema_version="delta-incident-resource-capabilities-v1",
        coordination_domain=(
            "delta-small-resource-inventory-v3"
            if config.generator_version in {"delta-small-generator-v7", "delta-small-generator-v8"}
            else f"delta-small-logical-authorities-{config.axes.phi}"
        ),
        resource_profile_id=config.resource_profile_id,
        units=units,
    )
