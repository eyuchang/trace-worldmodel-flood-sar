"""Predictor-prior and resource-inventory domain models."""

from pydantic import Field

from .base import DeltaModel


class PriorProfileArtifact(DeltaModel):
    profile_id: str
    schema_version: str
    calibration_version: str
    prior_accuracy_milli: int = Field(ge=300, le=1000)
    selected_by_pi: float = Field(ge=0.3, le=1.0)


class ResourceUnit(DeltaModel):
    resource_id: str
    resource_class: str
    base_id: str
    capabilities: tuple[str, ...]
    route_id: str
    passenger_capacity: int = Field(ge=0)
    activation_time_s: int = Field(ge=0)
    transit_time_s: int = Field(default=0, ge=0)
    staging_time_s: int = Field(ge=0)
    nominal_travel_time_s: int = Field(gt=0)
    available_from_s: int = Field(ge=0)
    service_duration_s: int = Field(gt=0)
    service_units: int = Field(gt=0)
    is_available: bool
    availability_mode: str = "local-from-scenario-start"
    origin_base_id: str | None = None
    source_record_ids: tuple[str, ...] = ()


class ResourceArtifact(DeltaModel):
    schema_version: str
    capability_schema_version: str
    coordination_domain: str
    resource_profile_id: str = "kappa-0.5-local-v1"
    service_unit_definition: str = "normalized-analytical-capability-load-unit"
    units: list[ResourceUnit]
