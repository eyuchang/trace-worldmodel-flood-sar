from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from trace_jepa.contracts import PlanPrediction
from trace_jepa.util import sha256_value


SHA256_PATTERN = r"^[0-9a-f]{64}$"
SAFE_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"


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


class ModelArtifactIdentity(FrozenModel):
    """Complete, content-bound identity of one executable model bundle.

    A version label alone is not an artifact identity.  The bundle digest binds
    the upstream source, preprocessing, every learned checkpoint, calibration,
    training snapshot, and action/feature schemas used by an inference.
    """

    identity_schema_version: Literal["model-artifact-identity-v2"] = (
        "model-artifact-identity-v2"
    )
    family: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    integration_kind: Literal[
        "official-upstream",
        "upstream-equivalent-port",
        "upstream-inspired-adaptation",
        "frozen-representation",
        "deterministic-control",
        "transparent-surrogate",
    ]
    source_repository: str = Field(min_length=1, max_length=512)
    source_commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    integration_source_tree_sha256: str | None = Field(
        default=None, pattern=SHA256_PATTERN
    )
    upstream_basis_repository: str | None = Field(
        default=None, min_length=1, max_length=512
    )
    upstream_basis_commit: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{7,64}$"
    )
    encoder_version: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    encoder_checkpoint_sha256: str = Field(pattern=SHA256_PATTERN)
    loaded_encoder_state_sha256: str | None = Field(
        default=None, pattern=SHA256_PATTERN
    )
    dynamics_version: str | None = Field(default=None, pattern=SAFE_IDENTIFIER_PATTERN)
    dynamics_checkpoint_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    outcome_head_version: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    outcome_head_sha256: str = Field(pattern=SHA256_PATTERN)
    calibration_version: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    calibration_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    training_snapshot_sha256: str = Field(pattern=SHA256_PATTERN)
    preprocessing_version: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    feature_schema_version: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    action_schema_version: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    supported_action_types: tuple[str, ...] = Field(min_length=1)
    bundle_sha256: str = ""

    @field_validator("supported_action_types")
    @classmethod
    def validate_actions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if tuple(sorted(set(value))) != value:
            raise ValueError("supported action types must be unique and sorted")
        for action in value:
            if not action or len(action) > 128:
                raise ValueError("supported action type is empty or too long")
        return value

    @model_validator(mode="after")
    def validate_bundle(self) -> "ModelArtifactIdentity":
        if (self.dynamics_version is None) != (self.dynamics_checkpoint_sha256 is None):
            raise ValueError("dynamics version and checkpoint hash must be declared together")
        if (self.upstream_basis_repository is None) != (
            self.upstream_basis_commit is None
        ):
            raise ValueError(
                "upstream basis repository and commit must be declared together"
            )
        expected = sha256_value(self.model_dump(mode="json", exclude={"bundle_sha256"}))
        if not self.bundle_sha256:
            object.__setattr__(self, "bundle_sha256", expected)
        elif self.bundle_sha256 != expected:
            raise ValueError("model bundle hash does not match its component identities")
        return self


class ObservationProvenance(FrozenModel):
    """Controller-visible identity of an observation; simulator truth is absent."""

    provenance_schema_version: Literal["observation-provenance-v2"] = (
        "observation-provenance-v2"
    )
    observation_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    observation_sha256: str = Field(pattern=SHA256_PATTERN)
    frames_sha256: str = Field(pattern=SHA256_PATTERN)
    controller_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    sensor_model_version: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    observed_at: float = Field(ge=0.0)
    study_partition: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)


class InferenceProvenance(FrozenModel):
    """Runtime receipt for one exact observation/model/request execution."""

    provenance_schema_version: Literal["inference-provenance-v2"] = (
        "inference-provenance-v2"
    )
    inference_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    model_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    output_sha256: str = Field(pattern=SHA256_PATTERN)
    requested_at: datetime
    started_at: datetime
    completed_at: datetime
    wall_duration_ms: float = Field(ge=0.0)
    cache_hit: bool
    device_type: Literal["cpu", "cuda", "mps"]
    precision: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    environment_manifest_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_timing(self) -> "InferenceProvenance":
        if not self.requested_at <= self.started_at <= self.completed_at:
            raise ValueError("inference timestamps must be monotone")
        return self


class RouteWorldModelRequestV2(RouteWorldModelRequest):
    """Hash-bound live request for future-state inference.

    ``action_parameters`` may contain only JSON values.  It must never contain
    simulator state or an audit snapshot; ``extra='forbid'`` enforces the typed
    controller boundary.
    """

    request_schema_version: Literal["route-world-model-request-v2"] = (
        "route-world-model-request-v2"
    )
    visual_observation_id: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    visual_observation_hash: str = Field(pattern=SHA256_PATTERN)
    visual_frames_sha256: str = Field(pattern=SHA256_PATTERN)
    visual_sensor_version: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    visual_observed_at: float = Field(ge=0.0)
    expected_model_bundle_sha256: str = Field(pattern=SHA256_PATTERN)
    prediction_horizons_s: tuple[float, ...] = Field(min_length=1)
    action_parameters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("prediction_horizons_s")
    @classmethod
    def validate_horizons(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if any(item <= 0.0 for item in value):
            raise ValueError("prediction horizons must be positive")
        if tuple(sorted(set(value))) != value:
            raise ValueError("prediction horizons must be unique and increasing")
        return value

    @field_validator("action_parameters")
    @classmethod
    def validate_action_parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        forbidden = {"truth", "audit_snapshot", "simulator_state", "latent_truth"}
        node_count = 0

        def visit(item: Any, depth: int) -> None:
            nonlocal node_count
            node_count += 1
            if node_count > 128 or depth > 4:
                raise ValueError("action parameters exceed the bounded JSON schema")
            if isinstance(item, dict):
                for key, nested in item.items():
                    if not isinstance(key, str) or not key or len(key) > 128:
                        raise ValueError("action parameter keys must be bounded strings")
                    if key.lower() in forbidden:
                        raise ValueError(
                            "action parameters contain audit-only simulator state"
                        )
                    visit(nested, depth + 1)
            elif isinstance(item, (list, tuple)):
                if len(item) > 64:
                    raise ValueError("action parameter arrays are too large")
                for nested in item:
                    visit(nested, depth + 1)
            elif isinstance(item, str):
                if len(item) > 512:
                    raise ValueError("action parameter strings are too large")
            elif item is not None and not isinstance(item, (bool, int, float)):
                raise ValueError("action parameters must contain canonical JSON values")

        visit(value, 0)
        try:
            encoded = json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("action parameters must be canonical JSON values") from exc
        if len(encoded.encode("utf-8")) > 8192:
            raise ValueError("action parameters exceed the serialized size limit")
        return value


class SemanticWorldStatePrediction(FrozenModel):
    """Planner-independent short-horizon state predicted by a world model."""

    state_schema_version: Literal["flood-route-semantic-state-v2"] = (
        "flood-route-semantic-state-v2"
    )
    horizons_s: tuple[float, ...] = Field(min_length=1)
    water_depth_m: tuple[float, ...] = Field(min_length=1)
    obstruction_probability: tuple[float, ...] = Field(min_length=1)
    flow_severity: tuple[float, ...] = Field(min_length=1)
    visibility: tuple[float, ...] = Field(min_length=1)
    operational_state: dict[str, float] = Field(default_factory=dict)
    epistemic_uncertainty: tuple[float, ...] = Field(min_length=1)
    support: tuple[float, ...] = Field(min_length=1)
    ood_score: tuple[float, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_state_vectors(self) -> "SemanticWorldStatePrediction":
        vectors = (
            self.water_depth_m,
            self.obstruction_probability,
            self.flow_severity,
            self.visibility,
            self.epistemic_uncertainty,
            self.support,
            self.ood_score,
        )
        if any(len(vector) != len(self.horizons_s) for vector in vectors):
            raise ValueError("every semantic-state vector must match the horizon count")
        if tuple(sorted(set(self.horizons_s))) != self.horizons_s:
            raise ValueError("semantic-state horizons must be unique and increasing")
        if any(value < 0.0 for value in self.water_depth_m):
            raise ValueError("predicted water depth cannot be negative")
        bounded = (
            self.obstruction_probability,
            self.flow_severity,
            self.visibility,
            self.epistemic_uncertainty,
            self.support,
            self.ood_score,
        )
        if any(value < 0.0 or value > 1.0 for vector in bounded for value in vector):
            raise ValueError("probability, support, visibility, and severity values must be in [0, 1]")
        return self


class RouteWorldModelOutput(FrozenModel):
    """Atomic result after semantic prediction and external route evaluation."""

    output_schema_version: Literal["route-world-model-output-v2"] = (
        "route-world-model-output-v2"
    )
    semantic_state: SemanticWorldStatePrediction
    prediction: PlanPrediction
    planner_version: str = Field(pattern=SAFE_IDENTIFIER_PATTERN)
    model: ModelArtifactIdentity
    observation: ObservationProvenance
    inference: InferenceProvenance
    prediction_timestamp: float = Field(ge=0.0)
    valid_until: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_links(self) -> "RouteWorldModelOutput":
        if self.inference.model_bundle_sha256 != self.model.bundle_sha256:
            raise ValueError("inference/model bundle link is inconsistent")
        if self.valid_until < self.prediction_timestamp:
            raise ValueError("world-model output expires before it is produced")
        return self


@runtime_checkable
class RouteWorldModel(Protocol):
    @property
    def provenance(self) -> WorldModelProvenance: ...

    def predict(self, request: RouteWorldModelRequest) -> PlanPrediction: ...
