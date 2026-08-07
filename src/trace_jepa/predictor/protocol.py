from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from trace_jepa.contracts import PlanCandidate, PlanPrediction
from trace_jepa.experimental.profile import AdequacyStatus


class PredictorModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PredictorRouteObservation(PredictorModel):
    route_id: str
    report: Literal["unknown", "open", "blocked"]
    nominal_travel_s: float = Field(ge=0.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    observation_age_s: float = Field(default=0.0, ge=0.0)
    stage_millifeet: int | None = None


class PredictorVisualFeatureRef(PredictorModel):
    """Content-addressed reference to an offline visual feature vector."""

    observation_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    observation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    feature_cache_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    feature_schema_version: str
    encoder_version: str
    encoder_checkpoint_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    captured_at_s: int = Field(ge=0)


class PredictorPriorProfile(PredictorModel):
    """Versioned within-predictor prior selected by the scenario pi axis."""

    profile_id: str
    calibration_version: str
    prior_accuracy_milli: int = Field(ge=300, le=1000)


class PredictorContext(PredictorModel):
    simulation_time_s: int = Field(default=0, ge=0)
    rain_milli_inches_per_hour: int = Field(default=0, ge=0)
    wind_milli_knots: int = Field(default=0, ge=0)
    available_resource_units: int = Field(default=0, ge=0)
    prior_profile: PredictorPriorProfile = PredictorPriorProfile(
        profile_id="delta-prior-high-v1",
        calibration_version="toy-calibration-v1",
        prior_accuracy_milli=900,
    )
    visual_feature: PredictorVisualFeatureRef | None = None


class PredictorObservation(PredictorModel):
    routes: list[PredictorRouteObservation]
    context: PredictorContext = PredictorContext()

    def route(self, route_id: str) -> PredictorRouteObservation:
        for route in self.routes:
            if route.route_id == route_id:
                return route
        raise KeyError(route_id)


class PredictorRequest(PredictorModel):
    plan: PlanCandidate
    observation: PredictorObservation


class PredictorProvenance(PredictorModel):
    predictor_version: str
    calibration_version: str
    training_snapshot: str
    model_hash: str
    calibration_hash: str
    adequacy_status: AdequacyStatus
    qualification_artifact_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    encoder_version: str | None = None
    encoder_checkpoint_hash: str | None = None
    feature_schema_version: str = "action-prefix-features-v2"
    action_schema_version: str = "delta-response-actions-v2"
    supported_action_types: tuple[str, ...] = (
        "dispatch_rescue_boat",
        "deploy_ground_team",
        "perform_welfare_check",
        "inspect_levee",
    )
    qualified_action_types: tuple[str, ...] = ()


def request_feature_vector(
    request: PredictorRequest,
    *,
    action_names: tuple[str, ...],
) -> list[float]:
    """Return the frozen structured feature vector for learned adapters."""

    action = request.plan.first_action
    route = request.observation.route(action.route_id) if action.route_id else None
    report = route.report if route else "unknown"
    report_one_hot = {
        "unknown": (1.0, 0.0, 0.0),
        "open": (0.0, 1.0, 0.0),
        "blocked": (0.0, 0.0, 1.0),
    }[report]
    action_one_hot = [float(action.action_type == name) for name in action_names]
    context = request.observation.context
    return [
        *report_one_hot,
        route.confidence if route else 0.0,
        (route.observation_age_s if route else 0.0) / 120.0,
        (route.nominal_travel_s if route else 0.0) / 1800.0,
        (route.stage_millifeet if route and route.stage_millifeet is not None else 0) / 12_000.0,
        context.rain_milli_inches_per_hour / 1000.0,
        context.wind_milli_knots / 45_000.0,
        context.available_resource_units / 10.0,
        context.prior_profile.prior_accuracy_milli / 1000.0,
        *action_one_hot,
    ]


@runtime_checkable
class ActionPrefixPredictor(Protocol):
    predictor_version: str
    calibration_version: str
    training_snapshot: str
    model_hash: str
    calibration_hash: str
    adequacy_status: AdequacyStatus

    def predict(self, request: PredictorRequest) -> PlanPrediction: ...

    def provenance(self) -> PredictorProvenance: ...
