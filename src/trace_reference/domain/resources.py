"""Synthetic resource, crew, and controller-telemetry contracts for Reference."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel


class ReferenceResourceClass(str, Enum):
    RESCUE_BOAT = "rescue-boat"
    AIRBOAT = "airboat"
    HIGH_WATER_VEHICLE = "high-water-vehicle"
    TYPE_I_ENGINE = "type-i-engine"
    ROTARY_HOIST = "rotary-hoist"
    ROTARY_RECON = "rotary-recon"
    SMALL_UAS = "small-uas"
    AMBULANCE = "ambulance"
    LAW_ENFORCEMENT = "law-enforcement"
    SWIFTWATER_TEAM = "swiftwater-team"
    FLOOD_FIGHT_CREW = "flood-fight-crew"


class ReferenceResourceCapability(str, Enum):
    WATER_RESCUE = "water-rescue"
    ROAD_RESCUE = "road-rescue"
    LEVEE_INSPECTION = "levee-inspection"
    MEDICAL_TRANSPORT = "medical-transport"
    WELFARE_CHECK = "welfare-check"
    MISSING_PERSON_SEARCH = "missing-person-search"
    ANIMAL_RESCUE = "animal-rescue"
    PUBLIC_INFORMATION = "public-information"
    HAZARD_CONTROL = "hazard-control"
    RECONNAISSANCE = "reconnaissance"


class ReferenceMutualAidTier(str, Enum):
    T0_LOCAL = "T0-local"
    T1_COUNTY = "T1-county"
    T2_REGIONAL = "T2-regional"
    T3_STATE = "T3-state"
    T4_FEDERAL = "T4-federal"


class ReferenceResourceState(str, Enum):
    AVAILABLE_STAGED = "available-staged"
    AWAITING_REQUEST = "awaiting-request"
    INITIAL_OUTAGE = "initial-outage"
    CREW_REST = "crew-rest"


class ReferenceResourceClassProfile(DeltaModel):
    resource_class: ReferenceResourceClass
    capabilities: tuple[ReferenceResourceCapability, ...] = Field(min_length=1)
    service_units: int = Field(ge=1, le=8)
    physical_capacity: int = Field(ge=0, le=24)
    crew_size: int = Field(ge=1, le=24)
    duty_limit_s: int = Field(ge=2_700, le=86_400)
    rest_requirement_s: int = Field(ge=1_800, le=43_200)
    turn_around_s: int = Field(ge=0, le=14_400)
    constraints: tuple[str, ...] = Field(min_length=1)


class ReferenceResourceHolding(DeltaModel):
    holding_id: str = Field(pattern=r"^HLD-[0-9]{2}$")
    base_id: str = Field(pattern=r"^BASE-[A-Z0-9-]+$")
    base_label: str = Field(min_length=3)
    staging_node_id: str = Field(pattern=r"^(ISL-0[1-8]|BND-[A-Z0-9-]+)$")
    owning_authority_id: Literal["AUTH-01", "AUTH-02", "AUTH-03", "AUTH-04"]
    tier: ReferenceMutualAidTier
    resource_class: ReferenceResourceClass
    baseline_count: int = Field(ge=1, le=20)
    maximum_count: int = Field(ge=1, le=40)
    nominal_travel_s: int = Field(ge=0, le=14_400)
    nominal_staging_s: int = Field(ge=0, le=7_200)
    fixture_semantics: Literal[
        "synthetic-planning-fixture-from-source-sketch-not-current-inventory-claim"
    ]

    @model_validator(mode="after")
    def validate_counts(self) -> ReferenceResourceHolding:
        if self.maximum_count < self.baseline_count:
            raise ValueError("Reference maximum resource count cannot be below baseline")
        return self


class ReferenceResourceParameters(DeltaModel):
    parameter_version: Literal["delta-reference-resource-parameters-v1"]
    scientific_status: Literal[
        "development-synthetic-roster-not-operational-inventory-or-availability"
    ]
    randomness_namespace: Literal["delta-reference-randomness-v1"]
    telemetry_interval_s: int = Field(ge=3_600, le=43_200)
    class_profiles: tuple[ReferenceResourceClassProfile, ...] = Field(min_length=11, max_length=11)
    holdings: tuple[ReferenceResourceHolding, ...] = Field(min_length=10)
    tier_activation_midpoint_s: dict[ReferenceMutualAidTier, int]
    limitations: tuple[str, ...] = Field(min_length=4)

    @model_validator(mode="after")
    def validate_registry(self) -> ReferenceResourceParameters:
        classes = tuple(item.resource_class for item in self.class_profiles)
        if len(set(classes)) != len(classes):
            raise ValueError("Reference resource class profiles must be unique")
        if set(classes) != set(ReferenceResourceClass):
            raise ValueError("Reference resource class profiles are incomplete")
        holding_ids = tuple(item.holding_id for item in self.holdings)
        if holding_ids != tuple(f"HLD-{index:02d}" for index in range(1, len(self.holdings) + 1)):
            raise ValueError("Reference holdings must be contiguous and canonically ordered")
        if any(item.resource_class not in classes for item in self.holdings):
            raise ValueError("Reference holding names an unknown resource class")
        if set(self.tier_activation_midpoint_s) != set(ReferenceMutualAidTier):
            raise ValueError("Reference activation table must cover T0 through T4")
        return self


class ReferenceCrewTruth(DeltaModel):
    crew_id: str = Field(pattern=r"^CREW-[0-9a-f]{16}$")
    resource_id: str = Field(pattern=r"^RR-[0-9a-f]{16}$")
    synthetic_people: int = Field(ge=1, le=24)
    qualification: ReferenceResourceClass
    duty_limit_s: int = Field(ge=2_700, le=86_400)
    rest_requirement_s: int = Field(ge=1_800, le=43_200)
    cycle_offset_s: int = Field(ge=0, le=129_600)
    initial_fatigue_micros: int = Field(ge=0, le=1_000_000)


class ReferenceResourceTruth(DeltaModel):
    resource_id: str = Field(pattern=r"^RR-[0-9a-f]{16}$")
    holding_id: str = Field(pattern=r"^HLD-[0-9]{2}$")
    resource_class: ReferenceResourceClass
    capabilities: tuple[ReferenceResourceCapability, ...] = Field(min_length=1)
    service_units: int = Field(ge=1, le=8)
    physical_capacity: int = Field(ge=0, le=24)
    home_base_id: str = Field(pattern=r"^BASE-[A-Z0-9-]+$")
    staged_node_id: str = Field(pattern=r"^(ISL-0[1-8]|BND-[A-Z0-9-]+)$")
    owning_authority_id: Literal["AUTH-01", "AUTH-02", "AUTH-03", "AUTH-04"]
    tier: ReferenceMutualAidTier
    crew_id: str = Field(pattern=r"^CREW-[0-9a-f]{16}$")
    inclusion_threshold_micros: int = Field(ge=250_000, le=2_000_000)
    activation_delay_s: int = Field(ge=0, le=172_800)
    nominal_travel_s: int = Field(ge=0, le=43_200)
    staging_delay_s: int = Field(ge=0, le=43_200)
    initial_outage_until_s: int | None = Field(default=None, ge=-172_800, le=86_400)
    turn_around_s: int = Field(ge=0, le=14_400)
    constraints: tuple[str, ...] = Field(min_length=1)


class ReferenceResourceStateSample(DeltaModel):
    resource_id: str = Field(pattern=r"^RR-[0-9a-f]{16}$")
    at_s: int = Field(ge=-172_800, lt=345_600)
    state: ReferenceResourceState
    crew_on_duty: bool
    crew_fatigue_micros: int = Field(ge=0, le=1_000_000)
    fuel_or_charge_micros: int = Field(ge=0, le=1_000_000)


class ReferenceHiddenResourceScenario(DeltaModel):
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    schema_version: Literal["delta-reference-resource-truth-v1"]
    parameter_version: Literal["delta-reference-resource-parameters-v1"]
    scientific_status: Literal[
        "development-synthetic-roster-not-operational-inventory-or-availability"
    ]
    seed: int = Field(ge=0)
    kappa_micros: int = Field(ge=250_000, le=2_000_000)
    mu_micros: int = Field(ge=500_000, le=2_000_000)
    delta_micros: int = Field(ge=0, le=1_000_000)
    resources: tuple[ReferenceResourceTruth, ...]
    crews: tuple[ReferenceCrewTruth, ...]
    state_samples: tuple[ReferenceResourceStateSample, ...]
    hidden_resource_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_hidden_resources(self) -> ReferenceHiddenResourceScenario:
        resource_ids = tuple(item.resource_id for item in self.resources)
        crew_ids = tuple(item.crew_id for item in self.crews)
        if len(set(resource_ids)) != len(resource_ids):
            raise ValueError("Reference resource identifiers must be unique")
        if len(set(crew_ids)) != len(crew_ids):
            raise ValueError("Reference crew identifiers must be unique")
        if set(crew_ids) != {item.crew_id for item in self.resources}:
            raise ValueError("Reference resources and crews must join exactly")
        if {item.resource_id for item in self.state_samples} != set(resource_ids):
            raise ValueError("Reference state samples must cover every selected resource")
        ordered = tuple(sorted(self.state_samples, key=lambda item: (item.at_s, item.resource_id)))
        if self.state_samples != ordered:
            raise ValueError("Reference resource states must use canonical time/resource order")
        return self


class ReferenceResourceTelemetry(DeltaModel):
    telemetry_id: str = Field(pattern=r"^RT-[0-9a-f]{16}$")
    resource_id: str = Field(pattern=r"^RR-[0-9a-f]{16}$")
    observed_at_s: int = Field(ge=-172_800, lt=345_600)
    delivered_at_s: int = Field(ge=-172_800, le=352_800)
    owning_authority_id: Literal["AUTH-01", "AUTH-02", "AUTH-03", "AUTH-04"]
    reported_state: ReferenceResourceState
    reported_crew_fatigue_band: Literal["low", "moderate", "high", "unknown"]
    reported_fuel_or_charge_band: Literal["full", "usable", "low", "unknown"]


class ReferencePublicResourceDefinition(DeltaModel):
    """Controller-known roster facts, separated from outages, fatigue, and true state."""

    resource_id: str = Field(pattern=r"^RR-[0-9a-f]{16}$")
    resource_class: ReferenceResourceClass
    capabilities: tuple[ReferenceResourceCapability, ...] = Field(min_length=1)
    service_units: int = Field(ge=1, le=8)
    physical_capacity: int = Field(ge=0, le=24)
    home_base_id: str = Field(pattern=r"^BASE-[A-Z0-9-]+$")
    staged_node_id: str = Field(pattern=r"^(ISL-0[1-8]|BND-[A-Z0-9-]+)$")
    owning_authority_id: Literal["AUTH-01", "AUTH-02", "AUTH-03", "AUTH-04"]
    tier: ReferenceMutualAidTier
    nominal_travel_s: int = Field(ge=0, le=43_200)
    constraints: tuple[str, ...] = Field(min_length=1)


class ReferencePublicResourceCatalog(DeltaModel):
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    schema_version: Literal["delta-reference-resource-catalog-v1"]
    scientific_status: Literal["synthetic-planning-roster-not-current-inventory-claim"]
    resources: tuple[ReferencePublicResourceDefinition, ...]
    resource_catalog_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_public_roster(self) -> ReferencePublicResourceCatalog:
        if self.resources != tuple(sorted(self.resources, key=lambda item: item.resource_id)):
            raise ValueError("Reference public resource catalog must use canonical order")
        identifiers = tuple(item.resource_id for item in self.resources)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Reference public resource identifiers must be unique")
        return self


class ReferenceResourceTelemetryAuditEntry(DeltaModel):
    audit_id: str = Field(pattern=r"^RA-[0-9a-f]{16}$")
    resource_id: str = Field(pattern=r"^RR-[0-9a-f]{16}$")
    observed_at_s: int = Field(ge=-172_800, lt=345_600)
    disposition: Literal["delivered", "omitted-by-observation-channel"]
    public_telemetry_id: str | None = Field(default=None, pattern=r"^RT-[0-9a-f]{16}$")
    contradiction_injected: bool

    @model_validator(mode="after")
    def validate_disposition(self) -> ReferenceResourceTelemetryAuditEntry:
        delivered = self.disposition == "delivered"
        if delivered != (self.public_telemetry_id is not None):
            raise ValueError("Reference resource telemetry audit disposition is inconsistent")
        if not delivered and self.contradiction_injected:
            raise ValueError("An omitted telemetry sample cannot carry a visible contradiction")
        return self


class ReferencePublicResourceTelemetryScenario(DeltaModel):
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    schema_version: Literal["delta-reference-resource-telemetry-v1"]
    seed: int = Field(ge=0)
    iota_micros: int = Field(ge=300_000, le=1_000_000)
    telemetry: tuple[ReferenceResourceTelemetry, ...]
    telemetry_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_telemetry_order(self) -> ReferencePublicResourceTelemetryScenario:
        ordered = tuple(
            sorted(self.telemetry, key=lambda item: (item.delivered_at_s, item.telemetry_id))
        )
        if self.telemetry != ordered:
            raise ValueError("Reference telemetry must use canonical delivery/ID order")
        ids = tuple(item.telemetry_id for item in self.telemetry)
        if len(set(ids)) != len(ids):
            raise ValueError("Reference telemetry identifiers must be unique")
        return self


class ReferenceHiddenResourceTelemetryAudit(DeltaModel):
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    schema_version: Literal["delta-reference-resource-telemetry-audit-v1"]
    seed: int = Field(ge=0)
    iota_micros: int = Field(ge=300_000, le=1_000_000)
    entries: tuple[ReferenceResourceTelemetryAuditEntry, ...]
    hidden_telemetry_audit_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReferenceResourceArtifacts(DeltaModel):
    hidden: ReferenceHiddenResourceScenario
    public_catalog: ReferencePublicResourceCatalog
    public: ReferencePublicResourceTelemetryScenario
    hidden_telemetry_audit: ReferenceHiddenResourceTelemetryAudit

    @model_validator(mode="after")
    def validate_public_resource_join(self) -> ReferenceResourceArtifacts:
        resource_ids = {item.resource_id for item in self.hidden.resources}
        if {item.resource_id for item in self.public_catalog.resources} != resource_ids:
            raise ValueError("Reference public roster and hidden inventory do not join exactly")
        if not {item.resource_id for item in self.public.telemetry} <= resource_ids:
            raise ValueError("Reference telemetry names an unknown physical resource")
        if {item.resource_id for item in self.hidden_telemetry_audit.entries} != resource_ids:
            raise ValueError("Reference telemetry audit must cover every selected resource")
        delivered_ids = {
            item.public_telemetry_id
            for item in self.hidden_telemetry_audit.entries
            if item.public_telemetry_id is not None
        }
        if delivered_ids != {item.telemetry_id for item in self.public.telemetry}:
            raise ValueError("Reference telemetry and its hidden audit do not join exactly")
        return self
