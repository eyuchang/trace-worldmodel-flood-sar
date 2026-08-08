from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trace_jepa.scenario.delta.geography_models import GeographyCatalog


class DeltaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AxisConfig(DeltaModel):
    sigma: float = Field(ge=0.2, le=2.0)
    kappa: float = Field(ge=0.25, le=2.0)
    mu: float = Field(ge=0.5, le=3.0)
    iota: float = Field(ge=0.3, le=1.0)
    phi: int = Field(ge=1, le=9)
    pi: float = Field(ge=0.3, le=1.0)
    exposure_profile: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]+$")
    delta: float = Field(ge=0.0, le=0.6)


class TimelineConfig(DeltaModel):
    epoch_utc: datetime
    timezone: str
    onset_clock: str
    duration_s: int = Field(gt=0)
    tick_s: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_ticks(self) -> TimelineConfig:
        if self.duration_s % self.tick_s != 0:
            raise ValueError("duration_s must be exactly divisible by tick_s")
        if self.epoch_utc.utcoffset() is None:
            raise ValueError("epoch_utc must include a timezone")
        return self


class ExtentConfig(DeltaModel):
    island_ids: list[str]
    community_ids: list[str]
    crossing_ids: list[str]
    gauge_ids: list[str]
    roster_size: int = Field(gt=0)


class CallProcessConfig(DeltaModel):
    model: str
    hourly_intensity: list[float]
    expected_calls_total: float = Field(gt=0.0)
    peak_expected_calls_per_hour: float = Field(gt=0.0)
    latent_expected_incidents: float = Field(default=26.07, gt=0.0)
    primary_taxonomy: list[str]

    @model_validator(mode="after")
    def validate_intensity_contract(self) -> CallProcessConfig:
        if len(self.hourly_intensity) != 6:
            raise ValueError("Small requires six expected observed-call intensities")
        if any(value < 0.0 for value in self.hourly_intensity):
            raise ValueError("hourly intensities must be non-negative")
        if abs(sum(self.hourly_intensity) - self.expected_calls_total) > 1e-12:
            raise ValueError("hourly intensities must integrate to expected_calls_total")
        if max(self.hourly_intensity) != self.peak_expected_calls_per_hour:
            raise ValueError("peak intensity disagrees with hourly_intensity")
        return self


class DemandCapacityConfig(DeltaModel):
    schema_version: str
    window_s: int = Field(gt=0)
    target_ratio: float = Field(gt=0.0)
    tolerance: float = Field(gt=0.0)
    demand_unit: str
    capacity_unit: str
    headline_metric: str = "legacy-hybrid-uncovered-demand-over-free-capacity"
    secondary_metric: str = "not-defined"


class ExpectedConfig(DeltaModel):
    breaches: int = Field(ge=0)
    mutual_aid_tiers: int = Field(ge=0)
    crew_rotation: bool
    maximum_runtime_s: float = Field(gt=0.0)


class DeltaScenarioConfig(DeltaModel):
    schema_version: str
    scenario_id: str
    generator_version: str
    randomness_namespace_version: str | None = None
    truth_coefficients_version: str | None = None
    observation_coefficients_version: str | None = None
    resource_profile_id: str = "kappa-0.5-local-v1"
    seed: int = Field(ge=0)
    timeline: TimelineConfig
    axes: AxisConfig
    extent: ExtentConfig
    call_process: CallProcessConfig
    demand_capacity: DemandCapacityConfig
    expected: ExpectedConfig
    exclusions: list[str]

    @model_validator(mode="after")
    def validate_small_scope(self) -> DeltaScenarioConfig:
        if self.scenario_id != "WF-DFLD-01-SMALL":
            raise ValueError("only WF-DFLD-01-SMALL is supported")
        if self.timeline.duration_s != 21_600:
            raise ValueError("Small must use the frozen six-hour duration")
        if self.extent.roster_size != 60:
            raise ValueError("Small must use the frozen 60-person teaching cohort")
        if self.extent.island_ids != ["ISL-01", "ISL-02"]:
            raise ValueError("Small must contain only Andrus and Brannan islands")
        if self.extent.community_ids != ["TWN-01"]:
            raise ValueError("Small must contain only the Isleton community")
        if self.extent.crossing_ids != ["XNG-03", "XNG-04"]:
            raise ValueError("Small must contain only the two frozen crossings")
        if self.extent.gauge_ids != ["RVB", "MRU", "FPT"]:
            raise ValueError("Small must contain the three reviewed gauge identities")
        if self.expected.breaches != 0:
            raise ValueError("breaches are outside the Small scope")
        if self.expected.mutual_aid_tiers != 0 or self.expected.crew_rotation:
            raise ValueError("mutual aid and crew rotation are outside the Small scope")
        if self.generator_version == "delta-small-generator-v6":
            if self.schema_version != "trace-delta-scenario-v2":
                raise ValueError("generator v6 requires trace-delta-scenario-v2")
            if self.randomness_namespace_version != "delta-small-generator-v5":
                raise ValueError("generator v6 must preserve the frozen v5 random namespace")
            if self.resource_profile_id != "kappa-0.5-local-plus-automatic-aid-v1":
                raise ValueError("generator v6 requires the registered automatic-aid profile")
            if self.demand_capacity.schema_version != "delta-demand-capacity-v2":
                raise ValueError("generator v6 requires delta-demand-capacity-v2")
        if self.generator_version == "delta-small-generator-v7":
            if self.schema_version != "trace-delta-scenario-v3":
                raise ValueError("generator v7 requires trace-delta-scenario-v3")
            if self.randomness_namespace_version != "delta-small-generator-v7":
                raise ValueError("generator v7 requires its new keyed random namespace")
            if self.resource_profile_id != "kappa-0.5-local-plus-automatic-aid-v1":
                raise ValueError("generator v7 requires the documented v3 resource roster")
            if self.demand_capacity.schema_version != "delta-demand-capacity-v3":
                raise ValueError("generator v7 requires delta-demand-capacity-v3")
            if self.truth_coefficients_version != "delta-truth-intercepts-v1":
                raise ValueError("generator v7 requires frozen truth intercepts v1")
            if self.observation_coefficients_version != "delta-observation-coefficients-v1":
                raise ValueError("generator v7 requires frozen observation coefficients v1")
        if self.generator_version == "delta-small-generator-v8":
            if self.schema_version != "trace-delta-scenario-v4":
                raise ValueError("generator v8 requires trace-delta-scenario-v4")
            if self.randomness_namespace_version != "delta-small-generator-v8":
                raise ValueError("generator v8 requires its new keyed random namespace")
            if self.resource_profile_id != "kappa-0.5-local-plus-automatic-aid-v1":
                raise ValueError("generator v8 requires the unchanged documented roster")
            if self.demand_capacity.schema_version != "delta-demand-capacity-v4":
                raise ValueError("generator v8 requires delta-demand-capacity-v4")
            if self.truth_coefficients_version != "delta-truth-intercepts-v2":
                raise ValueError("generator v8 requires frozen truth intercepts v2")
            if self.observation_coefficients_version != "delta-observation-coefficients-v2":
                raise ValueError("generator v8 requires frozen observation coefficients v2")
        return self


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
    status: str
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
    person_ids: list[str]
    incident_type: str
    required_capability: str
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
    incident_type: str
    simulation_time_s: int = Field(ge=0)
    probability_millionths: int = Field(ge=0, le=1_000_000)
    episode_key: str
    disposition: str
    suppression_reason: str | None = None


class GroundTruth(DeltaModel):
    schema_version: str
    cohort_label: str
    structures: list[StructureTruth]
    structure_states: list[StructureState]
    people: list[PersonTruth]
    person_positions: list[PersonPosition]
    levees: list[LeveeTruth]
    incidents: list[IncidentTruth]


class GroundTruthV8(GroundTruth):
    candidate_audit: list[IncidentCandidateAudit]


class CallLocation(DeltaModel):
    stated: str
    easting_mm: int
    northing_mm: int
    precision_m: int = Field(gt=0)
    method: str
    confidence_milli: int = Field(ge=0, le=1000)


class ReportedCall(DeltaModel):
    call_type: str
    occupants: int = Field(ge=0)
    occupants_confidence: str
    medical: list[str]
    description_token: str


class CallQuality(DeltaModel):
    call_dropped: bool
    callback_failed: bool
    revision_of_call_id: str | None = None


class CallRecord(DeltaModel):
    call_id: str
    received_s: int = Field(ge=0)
    received_ts: datetime
    psap: str
    channel: str
    callback_token: str
    on_scene: bool
    third_party: bool
    language: str
    location: CallLocation
    reported: ReportedCall
    quality: CallQuality


class CallLineage(DeltaModel):
    call_id: str
    truth_incident_id: str | None
    truth_person_ids: list[str]
    relationship: str


class ObservationArtifact(DeltaModel):
    schema_version: str
    calls: list[CallRecord]
    lineage: list[CallLineage]
    expected_calls_total: float
    peak_expected_calls_per_hour: float
    coefficients_version: str | None = None
    location_method_target_milli: dict[str, int] | None = None
    location_error_scale_milli: int | None = Field(default=None, ge=0)


class CoordinationDelivery(DeltaModel):
    call_id: str
    source_authority_id: str
    controller_authority_id: str
    available_to_controller_s: int = Field(ge=0)
    sharing_latency_s: int = Field(ge=0)


class CoordinationArtifact(DeltaModel):
    schema_version: str
    phi: int = Field(ge=1, le=9)
    logical_authority_ids: list[str] = Field(min_length=1)
    semantics: str
    deliveries: list[CoordinationDelivery]


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


class GeneratedScenario(DeltaModel):
    config: DeltaScenarioConfig
    geography: GeographyCatalog
    weather: list[WeatherSample]
    gauges: list[GaugeSample]
    crossing_states: list[CrossingState]
    truth: GroundTruth | GroundTruthV8
    observations: ObservationArtifact
    coordination: CoordinationArtifact | None = None
    resources: ResourceArtifact
    prior_profile: PriorProfileArtifact
    stage_seeds: list[str]
    generation_order: list[str]
    source_path: Path
