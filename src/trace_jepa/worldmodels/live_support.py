from __future__ import annotations

import time
from typing import Literal

from pydantic import Field

from trace_jepa.worldmodels.contracts import (
    FrozenModel,
    ObservationProvenance,
    RouteWorldModelRequest,
    RouteWorldModelRequestV2,
)
from trace_jepa.worldmodels.live_observations import (
    ObservationIntegrityError,
    VerifiedSimulatorObservationRepository,
)
from trace_jepa.worldmodels.live_service import (
    LiveInferenceRequest,
    LiveInferenceState,
    LiveWorldModelService,
)


class SupportingInferenceStatus(FrozenModel):
    """Non-licensing learned-model evidence attached to a TRACE record."""

    status_schema_version: Literal["supporting-inference-status-v1"] = (
        "supporting-inference-status-v1"
    )
    evidence_role: Literal["supporting-non-licensing"] = "supporting-non-licensing"
    state: Literal["queued", "running", "completed", "failed"]
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_id: str
    model_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_family: str
    model_source_commit: str
    encoder_checkpoint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dynamics_checkpoint_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    outcome_head_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    calibration_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observation_id: str
    observation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frames_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    controller_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    route_id: str
    action_type: str
    artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    latent_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    environment_manifest_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    cache_hit: bool = False
    queue_wait_ms: float | None = Field(default=None, ge=0.0)
    backend_duration_ms: float | None = Field(default=None, ge=0.0)
    persistence_duration_ms: float | None = Field(default=None, ge=0.0)
    total_service_ms: float | None = Field(default=None, ge=0.0)
    failure_code: str | None = None


class LiveSupportingInferenceBridge:
    """Submit learned inference in shadow mode without changing TRACE decisions.

    Completed artifacts are provenance-bound supporting evidence.  They never
    replace the frozen surrogate prediction and therefore cannot alter policy,
    commitment, or plan-selection semantics.
    """

    def __init__(
        self,
        *,
        service: LiveWorldModelService,
        observations: VerifiedSimulatorObservationRepository,
        prediction_horizons_s: tuple[float, ...] = (60.0, 180.0, 600.0),
    ):
        if tuple(sorted(set(prediction_horizons_s))) != prediction_horizons_s or any(
            item <= 0.0 for item in prediction_horizons_s
        ):
            raise ValueError("prediction horizons must be positive, unique, and increasing")
        self.service = service
        self.observations = observations
        self.prediction_horizons_s = prediction_horizons_s
        self._requests: dict[str, LiveInferenceRequest] = {}
        self._statuses: dict[str, SupportingInferenceStatus] = {}
        self.service.start()

    @property
    def model_identity(self):
        return self.service.identity

    def submit(
        self,
        request: RouteWorldModelRequest,
        *,
        observation_hash: str,
        sensor_version: str,
        observed_at: float,
    ) -> SupportingInferenceStatus:
        observation = self._verified_observation(
            request,
            observation_hash=observation_hash,
            sensor_version=sensor_version,
            observed_at=observed_at,
        )
        values = request.model_dump(exclude={"request_schema_version"})
        route_request = RouteWorldModelRequestV2(
            **values,
            visual_observation_hash=observation.observation_sha256,
            visual_frames_sha256=observation.frames_sha256,
            visual_sensor_version=observation.sensor_model_version,
            visual_observed_at=observation.observed_at,
            expected_model_bundle_sha256=self.service.identity.bundle_sha256,
            prediction_horizons_s=self.prediction_horizons_s,
            action_parameters={"travel_time_s": request.travel_time_s},
        )
        live_request = LiveInferenceRequest(
            route_request=route_request,
            observation=observation,
            model=self.service.identity,
        )
        self._requests[live_request.request_sha256] = live_request
        receipt = self.service.submit(live_request)
        status = self._status(live_request, receipt)
        self._statuses[live_request.request_sha256] = status
        return status

    def poll_updates(self) -> tuple[SupportingInferenceStatus, ...]:
        changed: list[SupportingInferenceStatus] = []
        for request_sha256, live_request in tuple(self._requests.items()):
            receipt = self.service.poll(request_sha256)
            if receipt is None:
                continue
            status = self._status(live_request, receipt)
            if status != self._statuses.get(request_sha256):
                self._statuses[request_sha256] = status
                changed.append(status)
        return tuple(changed)

    def wait_for_terminal(
        self,
        request_sha256: str,
        *,
        timeout_s: float,
    ) -> SupportingInferenceStatus:
        if timeout_s <= 0.0:
            raise ValueError("supporting inference timeout must be positive")
        if request_sha256 not in self._requests:
            raise KeyError("supporting inference request is unknown")
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            receipt = self.service.poll(request_sha256)
            if receipt is not None:
                status = self._status(self._requests[request_sha256], receipt)
                self._statuses[request_sha256] = status
                if status.state in {"completed", "failed"}:
                    return status
            time.sleep(0.001)
        raise TimeoutError("supporting inference did not complete within its deadline")

    def reset(self) -> None:
        """Invalidate all pre-reset associations without reusing their receipts."""

        self._requests.clear()
        self._statuses.clear()

    def close(self) -> None:
        self.service.close()

    def _verified_observation(
        self,
        request: RouteWorldModelRequest,
        *,
        observation_hash: str,
        sensor_version: str,
        observed_at: float,
    ) -> ObservationProvenance:
        if request.visual_observation_id is None:
            raise ObservationIntegrityError("route request has no visual observation")
        observation = self.observations.provenance(
            request.visual_observation_id,
            expected_observation_sha256=observation_hash,
        )
        if (
            observation.sensor_model_version != sensor_version
            or observation.observed_at != observed_at
        ):
            raise ObservationIntegrityError(
                "controller observation metadata does not match its artifact"
            )
        return observation

    def _status(self, live_request: LiveInferenceRequest, receipt) -> SupportingInferenceStatus:
        failure_code = (
            receipt.failure_code.value if receipt.failure_code is not None else None
        )
        latent_sha256 = None
        if receipt.state == LiveInferenceState.COMPLETED:
            artifact = self.service.artifact(live_request.request_sha256)
            if artifact is not None:
                latent_sha256 = artifact[0].latent_sha256
        model = live_request.model
        return SupportingInferenceStatus(
            state=receipt.state.value,
            request_sha256=live_request.request_sha256,
            plan_id=live_request.route_request.plan_id,
            model_bundle_sha256=model.bundle_sha256,
            model_family=model.family,
            model_source_commit=model.source_commit,
            encoder_checkpoint_sha256=model.encoder_checkpoint_sha256,
            dynamics_checkpoint_sha256=model.dynamics_checkpoint_sha256,
            outcome_head_sha256=model.outcome_head_sha256,
            calibration_artifact_sha256=model.calibration_artifact_sha256,
            observation_id=live_request.observation.observation_id,
            observation_sha256=live_request.observation.observation_sha256,
            frames_sha256=live_request.observation.frames_sha256,
            controller_manifest_sha256=(
                live_request.observation.controller_manifest_sha256
            ),
            route_id=live_request.route_request.route_id,
            action_type=live_request.route_request.action_type,
            artifact_sha256=receipt.artifact_sha256,
            latent_sha256=latent_sha256,
            environment_manifest_sha256=receipt.environment_manifest_sha256,
            cache_hit=receipt.cache_hit,
            queue_wait_ms=receipt.queue_wait_ms,
            backend_duration_ms=receipt.backend_duration_ms,
            persistence_duration_ms=receipt.persistence_duration_ms,
            total_service_ms=receipt.total_service_ms,
            failure_code=failure_code,
        )
