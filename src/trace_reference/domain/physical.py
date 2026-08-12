"""Reduced-order physical-state contracts for WF-DFLD-01-REFERENCE."""

from __future__ import annotations

from itertools import pairwise
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel

from .events import ReferenceEvent


class ReferenceMeteorologyPhase(DeltaModel):
    phase_id: str = Field(pattern=r"^MET-[0-9]{2}$")
    start_s: int
    end_s: int
    nominal_rain_milli_in_per_hour: int = Field(ge=0)
    wind_milli_knots: int = Field(ge=0)
    ceiling_ft: int = Field(gt=0)
    air_operability: Literal["normal", "reduced", "grounded"]

    @model_validator(mode="after")
    def validate_half_open_phase(self) -> ReferenceMeteorologyPhase:
        if self.start_s >= self.end_s:
            raise ValueError("meteorology phase must be a nonempty half-open interval")
        return self


class ReferenceGaugeParameter(DeltaModel):
    gauge_id: Literal["FPT", "RVB", "SJJ", "ANH", "MRU", "OLD", "MSD"]
    official_name: str
    baseline_milli_ft: int
    tide_amplitude_milli_ft: int = Field(gt=0)
    tide_phase_milliradians: int
    runoff_lag_s: int = Field(ge=0)
    runoff_gain_milli_ft_per_inch: int = Field(ge=0)
    release_gain_milli_ft: int = Field(ge=0)
    threshold_status: Literal["unavailable-non-operative"]


class ReferenceGaugeContextPoint(DeltaModel):
    gauge_id: Literal["FPT", "RVB", "SJJ", "ANH", "MRU", "OLD", "MSD"]
    official_name: str
    latitude_e6: int = Field(ge=-90_000_000, le=90_000_000)
    longitude_e6: int = Field(ge=-180_000_000, le=180_000_000)
    threshold_status: Literal["unavailable-non-operative"]


class ReferenceGaugeContextRegistry(DeltaModel):
    registry_version: Literal["delta-reference-gauge-context-v1"]
    scientific_status: Literal["official-identity-context-only-thresholds-non-operative"]
    derived_from_registry: Literal[
        "data/scenario/delta/reference/sources/gauge_identity_research_v1.yaml"
    ]
    derived_from_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transformation: Literal["exact-field-transcription-no-coordinate-interpolation"]
    gauges: tuple[ReferenceGaugeContextPoint, ...] = Field(min_length=7, max_length=7)
    limitations: tuple[str, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_context_gauges(self) -> ReferenceGaugeContextRegistry:
        expected = ("FPT", "RVB", "SJJ", "ANH", "MRU", "OLD", "MSD")
        if tuple(item.gauge_id for item in self.gauges) != expected:
            raise ValueError("Reference context-gauge coverage or order is incomplete")
        return self


class ReferenceBreachParameters(DeltaModel):
    breach_id: Literal["BREACH-01"]
    segment_id: Literal["SIM-RD407-WEST-01"]
    island_id: Literal["ISL-01"]
    activation_s: Literal[187200]
    initial_width_milli_ft: Literal[60000]
    final_width_milli_ft: Literal[210000]
    widening_duration_s: Literal[32400]
    mean_inflow_cfs: int = Field(gt=0)
    tidal_inflow_amplitude_cfs: int = Field(gt=0)
    storage_capacity_acre_ft: int = Field(gt=0)
    first_street_flooding_delay_s: Literal[21600]
    one_third_city_delay_s: Literal[50400]
    source_semantics: Literal["synthetic-segment-anchored-to-source-bound-andrus-footprint"]


class ReferenceCrossingRule(DeltaModel):
    crossing_id: str = Field(pattern=r"^XNG-(0[1-9]|10)$")
    rule: Literal[
        "normally-open",
        "close-at-t53-after-scripted-breach",
        "ferry-suspend-on-model-wind-or-stage",
        "unavailable-because-current-type-unresolved",
    ]
    wind_suspend_milli_knots: int | None = Field(default=None, gt=0)
    stage_suspend_milli_ft: int | None = Field(default=None, gt=0)


class ReferencePhysicalParameters(DeltaModel):
    parameter_version: Literal["delta-reference-physical-v1"]
    scientific_status: Literal["reduced-order-teaching-model-not-hydrodynamic-forecast"]
    output_tick_s: Literal[300]
    m2_period_s: Literal[44700]
    perigean_spring_center_s: Literal[237600]
    evaluation_rainfall_target_milli_in: Literal[9800]
    meteorology_phases: tuple[ReferenceMeteorologyPhase, ...] = Field(min_length=9)
    gauges: tuple[ReferenceGaugeParameter, ...] = Field(min_length=7, max_length=7)
    breach: ReferenceBreachParameters
    crossing_rules: tuple[ReferenceCrossingRule, ...] = Field(min_length=10, max_length=10)
    limitations: tuple[str, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_complete_physical_contract(self) -> ReferencePhysicalParameters:
        phases = sorted(self.meteorology_phases, key=lambda item: item.start_s)
        if phases[0].start_s != -172_800 or phases[-1].end_s != 345_600:
            raise ValueError("meteorology phases must cover the complete burn-in/evaluation window")
        if any(left.end_s != right.start_s for left, right in pairwise(phases)):
            raise ValueError("meteorology phases must be contiguous and non-overlapping")
        if tuple(item.gauge_id for item in self.gauges) != (
            "FPT",
            "RVB",
            "SJJ",
            "ANH",
            "MRU",
            "OLD",
            "MSD",
        ):
            raise ValueError("Reference gauge parameter coverage/order is incomplete")
        if tuple(item.crossing_id for item in self.crossing_rules) != tuple(
            f"XNG-{index:02d}" for index in range(1, 11)
        ):
            raise ValueError("Reference crossing-rule coverage/order is incomplete")
        return self


class ReferenceWeatherSample(DeltaModel):
    at_s: int
    phase_id: str
    nominal_rain_milli_in_per_hour: int = Field(ge=0)
    effective_rain_milli_in_per_hour: int = Field(ge=0)
    wind_milli_knots: int = Field(ge=0)
    ceiling_ft: int = Field(gt=0)
    air_operability: Literal["normal", "reduced", "grounded"]


class ReferenceGaugeStageSample(DeltaModel):
    gauge_id: str
    baseline_milli_ft: int
    tide_milli_ft: int
    runoff_milli_ft: int
    wind_setup_milli_ft: int
    upstream_release_milli_ft: int
    stage_milli_ft: int
    threshold_status: Literal["unavailable-non-operative"]

    @model_validator(mode="after")
    def validate_additive_stage(self) -> ReferenceGaugeStageSample:
        expected = (
            self.baseline_milli_ft
            + self.tide_milli_ft
            + self.runoff_milli_ft
            + self.wind_setup_milli_ft
            + self.upstream_release_milli_ft
        )
        if self.stage_milli_ft != expected:
            raise ValueError("gauge stage must equal its exposed additive components")
        return self


class ReferenceBreachSample(DeltaModel):
    breach_id: Literal["BREACH-01"]
    segment_id: Literal["SIM-RD407-WEST-01"]
    active: bool
    width_milli_ft: int = Field(ge=0)
    net_inflow_cfs: int
    stored_milli_acre_ft: int = Field(ge=0)
    isleton_flood_state: Literal[
        "not-threatened",
        "first-street-flooding",
        "one-third-city-synthetic-extent",
    ]


class ReferenceCrossingStateSample(DeltaModel):
    crossing_id: str = Field(pattern=r"^XNG-(0[1-9]|10)$")
    status: Literal["open", "closed", "suspended", "unavailable-unresolved"]
    reason: str
    source_semantics: Literal["model-state-not-current-operability"]


class ReferencePhysicalSample(DeltaModel):
    at_s: int
    weather: ReferenceWeatherSample
    gauges: tuple[ReferenceGaugeStageSample, ...] = Field(min_length=7, max_length=7)
    breach: ReferenceBreachSample
    crossings: tuple[ReferenceCrossingStateSample, ...] = Field(min_length=10, max_length=10)


class ReferencePhysicalScenario(DeltaModel):
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    schema_version: Literal["delta-reference-physical-scenario-v1"]
    parameter_version: Literal["delta-reference-physical-v1"]
    samples: tuple[ReferencePhysicalSample, ...] = Field(min_length=1729, max_length=1729)
    events: tuple[ReferenceEvent, ...] = Field(min_length=3458)
    physical_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
