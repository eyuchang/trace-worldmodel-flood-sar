"""Validated configuration and version bindings for WF-DFLD-01-SMALL."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import Field, model_validator

from .base import DeltaModel


@dataclass(frozen=True)
class ProtocolRevision:
    """Schema and coefficient bindings for one supported generator revision."""

    scenario_schema: str
    randomness_namespace: str
    resource_profile: str
    demand_capacity_schema: str
    truth_coefficients: str | None = None
    observation_coefficients: str | None = None


PROTOCOL_REVISIONS: dict[tuple[str, str], ProtocolRevision] = {
    ("delta-small-generator-v6", "trace-delta-scenario-v2"): ProtocolRevision(
        scenario_schema="trace-delta-scenario-v2",
        randomness_namespace="delta-small-generator-v5",
        resource_profile="kappa-0.5-local-plus-automatic-aid-v1",
        demand_capacity_schema="delta-demand-capacity-v2",
    ),
    ("delta-small-generator-v7", "trace-delta-scenario-v3"): ProtocolRevision(
        scenario_schema="trace-delta-scenario-v3",
        randomness_namespace="delta-small-generator-v7",
        resource_profile="kappa-0.5-local-plus-automatic-aid-v1",
        demand_capacity_schema="delta-demand-capacity-v3",
        truth_coefficients="delta-truth-intercepts-v1",
        observation_coefficients="delta-observation-coefficients-v1",
    ),
    ("delta-small-generator-v8", "trace-delta-scenario-v4"): ProtocolRevision(
        scenario_schema="trace-delta-scenario-v4",
        randomness_namespace="delta-small-generator-v8",
        resource_profile="kappa-0.5-local-plus-automatic-aid-v1",
        demand_capacity_schema="delta-demand-capacity-v4",
        truth_coefficients="delta-truth-intercepts-v2",
        observation_coefficients="delta-observation-coefficients-v2",
    ),
    ("delta-small-generator-v8", "trace-delta-scenario-v5"): ProtocolRevision(
        scenario_schema="trace-delta-scenario-v5",
        randomness_namespace="delta-small-generator-v8",
        resource_profile="kappa-0.5-local-plus-automatic-aid-v1",
        demand_capacity_schema="delta-demand-capacity-v5",
        truth_coefficients="delta-truth-intercepts-v2",
        observation_coefficients="delta-observation-coefficients-v2",
    ),
}


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
    island_ids: tuple[str, ...]
    community_ids: tuple[str, ...]
    crossing_ids: tuple[str, ...]
    gauge_ids: tuple[str, ...]
    roster_size: int = Field(gt=0)


class CallProcessConfig(DeltaModel):
    model: str
    hourly_intensity: tuple[float, ...]
    expected_calls_total: float = Field(gt=0.0)
    peak_expected_calls_per_hour: float = Field(gt=0.0)
    latent_expected_incidents: float = Field(default=26.07, gt=0.0)
    primary_taxonomy: tuple[str, ...]

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
    target_ratio: float | None = Field(default=None, gt=0.0)
    tolerance: float | None = Field(default=None, gt=0.0)
    demand_unit: str
    capacity_unit: str
    headline_metric: str = "legacy-hybrid-uncovered-demand-over-free-capacity"
    secondary_metric: str = "not-defined"

    @model_validator(mode="after")
    def forbid_active_legacy_target(self) -> DemandCapacityConfig:
        if self.schema_version == "delta-demand-capacity-v5" and (
            self.target_ratio is not None or self.tolerance is not None
        ):
            raise ValueError("demand/capacity v5 forbids historical target fields")
        return self


class ExpectedConfig(DeltaModel):
    breaches: int = Field(ge=0)
    mutual_aid_tiers: int = Field(ge=0)
    crew_rotation: bool
    maximum_runtime_s: float = Field(gt=0.0)


class DeltaScenarioConfig(DeltaModel):
    """Frozen Small configuration with cross-field protocol validation."""

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
    exclusions: tuple[str, ...]

    @model_validator(mode="after")
    def validate_small_scope(self) -> DeltaScenarioConfig:
        expected_scope = {
            "scenario_id": "WF-DFLD-01-SMALL",
            "duration_s": 21_600,
            "roster_size": 60,
            "island_ids": ("ISL-01", "ISL-02"),
            "community_ids": ("TWN-01",),
            "crossing_ids": ("XNG-03", "XNG-04"),
            "gauge_ids": ("RVB", "MRU", "FPT"),
        }
        actual_scope = {
            "scenario_id": self.scenario_id,
            "duration_s": self.timeline.duration_s,
            "roster_size": self.extent.roster_size,
            "island_ids": self.extent.island_ids,
            "community_ids": self.extent.community_ids,
            "crossing_ids": self.extent.crossing_ids,
            "gauge_ids": self.extent.gauge_ids,
        }
        if actual_scope != expected_scope:
            mismatches = [
                name for name, expected in expected_scope.items() if actual_scope[name] != expected
            ]
            raise ValueError(f"Small scope mismatch: {', '.join(mismatches)}")
        if self.expected.breaches != 0:
            raise ValueError("breaches are outside the Small scope")
        if self.expected.mutual_aid_tiers != 0 or self.expected.crew_rotation:
            raise ValueError("mutual aid and crew rotation are outside the Small scope")
        revision = PROTOCOL_REVISIONS.get((self.generator_version, self.schema_version))
        if revision is None:
            return self
        bindings = {
            "scenario schema": (self.schema_version, revision.scenario_schema),
            "randomness namespace": (
                self.randomness_namespace_version,
                revision.randomness_namespace,
            ),
            "resource profile": (self.resource_profile_id, revision.resource_profile),
            "demand/capacity schema": (
                self.demand_capacity.schema_version,
                revision.demand_capacity_schema,
            ),
            "truth coefficients": (
                self.truth_coefficients_version,
                revision.truth_coefficients,
            ),
            "observation coefficients": (
                self.observation_coefficients_version,
                revision.observation_coefficients,
            ),
        }
        for label, (actual, expected) in bindings.items():
            if expected is not None and actual != expected:
                raise ValueError(
                    f"{self.generator_version} requires {label} {expected}; received {actual}"
                )
        return self
