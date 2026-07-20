from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from trace_jepa.contracts import PlanPrediction


class WorldModelInputUnavailable(RuntimeError):
    """Raised when a declared controller-visible model input is absent."""


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RouteWorldModelRequest(FrozenModel):
    """Controller-visible inputs for one route/action prediction.

    Dynamic simulator truth is intentionally absent. Static route parameters,
    controller beliefs, declared forcing parameters, and asset telemetry are
    allowed because those values are available to the decision maker.
    """

    request_schema_version: str = "route-world-model-request-v1"
    plan_id: str
    route_id: str
    asset_id: str
    action_type: str = "dispatch_rescue_boat"
    belief_status: Literal["unknown", "open", "blocked"]
    belief_confidence: float = Field(ge=0.0, le=1.0)
    observation_age_s: float = Field(ge=0.0)
    observed_depth_m: float | None = Field(default=None, ge=0.0)
    projected_depth_m: float = Field(ge=0.0)
    route_closure_depth_m: float = Field(gt=0.0)
    route_susceptibility: float = Field(ge=0.0)
    travel_time_s: float = Field(gt=0.0)
    water_rise_rate: float = Field(ge=0.0)
    rain_intensity: float = Field(ge=0.0, le=1.0)
    upstream_inflow: float = Field(ge=0.0, le=1.0)
    weather_forecast: float = Field(ge=0.0, le=1.0)
    sensor_noise: float = Field(ge=0.0, le=1.0)
    packet_loss: float = Field(ge=0.0, le=1.0)
    declared_ood_severity: float = Field(ge=0.0, le=1.0)
    sensor_quality: float = Field(ge=0.0, le=1.0)
    asset_resource: float = Field(ge=0.0, le=1.0)
    asset_weather_tolerance: float = Field(ge=0.0, le=1.0)
    visual_observation_id: str | None = None
    visual_observation_age_s: float | None = Field(default=None, ge=0.0)

    @property
    def structured_features(self) -> tuple[float, ...]:
        status = {
            "unknown": (1.0, 0.0, 0.0),
            "open": (0.0, 1.0, 0.0),
            "blocked": (0.0, 0.0, 1.0),
        }[self.belief_status]
        observed_depth = (
            self.observed_depth_m
            if self.observed_depth_m is not None
            else 0.75 * self.route_closure_depth_m
        )
        return (
            *status,
            self.belief_confidence,
            self.observation_age_s / 600.0,
            observed_depth / self.route_closure_depth_m,
            self.projected_depth_m / self.route_closure_depth_m,
            self.route_susceptibility,
            self.travel_time_s / 1800.0,
            self.water_rise_rate * 10_000.0,
            self.rain_intensity,
            self.upstream_inflow,
            self.weather_forecast,
            self.sensor_noise,
            self.packet_loss,
            self.declared_ood_severity,
            self.sensor_quality,
            self.asset_resource,
            self.asset_weather_tolerance,
        )


class WorldModelProvenance(FrozenModel):
    encoder_version: str
    encoder_checkpoint_sha256: str
    predictor_version: str
    predictor_checkpoint_sha256: str
    calibration_version: str
    training_snapshot: str
    semantic_probe_versions: tuple[str, ...]
    supported_action_types: tuple[str, ...]
    feature_schema_version: str = "route-jepa-fusion-v1"


@runtime_checkable
class RouteWorldModel(Protocol):
    @property
    def provenance(self) -> WorldModelProvenance: ...

    def predict(self, request: RouteWorldModelRequest) -> PlanPrediction: ...
