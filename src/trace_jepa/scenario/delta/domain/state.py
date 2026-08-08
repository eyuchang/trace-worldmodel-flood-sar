"""Physical-state and hidden-truth models for Delta Small."""

from __future__ import annotations

from pydantic import Field, model_validator

from .base import DeltaModel
from .types import CallTaxonomy, Capability, RouteStatus


class WeatherSample(DeltaModel):
    simulation_time_s: int = Field(ge=0)
    rain_milli_inches_per_hour: int = Field(ge=0)
    wind_milli_knots: int = Field(ge=0)
    ceiling_ft: int = Field(gt=0)
    aviation_operable: bool


class GaugeSample(DeltaModel):
    gauge_id: str
    simulation_time_s: int = Field(ge=0)
    baseline_millifeet: int
    tide_millifeet: int
    runoff_millifeet: int
    wind_setup_millifeet: int
    upstream_release_millifeet: int
    stage_millifeet: int
    action_threshold_crossed: bool

    @model_validator(mode="after")
    def validate_additive_components(self) -> GaugeSample:
        total = (
            self.baseline_millifeet
            + self.tide_millifeet
            + self.runoff_millifeet
            + self.wind_setup_millifeet
            + self.upstream_release_millifeet
        )
        if self.stage_millifeet != total:
            raise ValueError("gauge stage must equal the declared additive components")
        return self


class CrossingState(DeltaModel):
    crossing_id: str
    simulation_time_s: int = Field(ge=0)
    status: RouteStatus
    travel_time_s: int = Field(gt=0)
    confidence_milli: int = Field(ge=0, le=1000)
    evidence: str


class LeveeTruth(DeltaModel):
    segment_id: str
    island_id: str
    district_id: str
    simulation_time_s: int = Field(ge=0)
    condition: str
    seepage_state: str
    breach: bool


class StructureTruth(DeltaModel):
    structure_id: str
    community_id: str
    island_id: str
    easting_mm: int
    northing_mm: int
    placement_profile: str


class StructureState(DeltaModel):
    structure_id: str
    simulation_time_s: int = Field(ge=0)
    flood_state: str
    access_state: str


class PersonTruth(DeltaModel):
    person_id: str
    home_structure_id: str
    mobility: str
    medical_dependency: str
    preferred_language: str


class PersonPosition(DeltaModel):
    person_id: str
    simulation_time_s: int = Field(ge=0)
    structure_id: str
    state: str


class IncidentTruth(DeltaModel):
    incident_id: str
    structure_id: str
    person_ids: tuple[str, ...]
    incident_type: CallTaxonomy
    required_capability: Capability
    onset_s: int = Field(ge=0)
    service_duration_s: int = Field(gt=0)
    service_units: int = Field(gt=0)
    complexity_milli: int = Field(ge=0, le=1000)
    causal_mechanism: str
    infrastructure_id: str | None = None
    causal_factors_milli: dict[str, int] = Field(default_factory=dict)


class IncidentCandidateAudit(DeltaModel):
    """Hidden record of keyed candidate thinning and episode formation."""

    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    draw_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    structure_id: str
    infrastructure_id: str | None = None
    incident_type: CallTaxonomy
    simulation_time_s: int = Field(ge=0)
    probability_millionths: int = Field(ge=0, le=1_000_000)
    episode_key: str
    disposition: str
    suppression_reason: str | None = None


class GroundTruth(DeltaModel):
    schema_version: str
    cohort_label: str
    structures: tuple[StructureTruth, ...]
    structure_states: tuple[StructureState, ...]
    people: tuple[PersonTruth, ...]
    person_positions: tuple[PersonPosition, ...]
    levees: tuple[LeveeTruth, ...]
    incidents: tuple[IncidentTruth, ...]


class GroundTruthV8(GroundTruth):
    candidate_audit: tuple[IncidentCandidateAudit, ...]
