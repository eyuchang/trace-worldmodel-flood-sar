from __future__ import annotations

import hashlib
import os
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from trace_jepa.worldmodels.contracts import (
    ModelArtifactIdentity,
    ObservationProvenance,
    RouteWorldModelRequestV2,
    SemanticWorldStatePrediction,
)
from trace_jepa.worldmodels.live_artifacts import (
    ArtifactIntegrityError,
    ContentAddressedInferenceStore,
)
from trace_jepa.worldmodels.live_service import (
    LiveBackendOutput,
    LiveInferenceBackpressure,
    LiveInferenceError,
    LiveInferenceFailureCode,
    LiveInferenceRequest,
    LiveInferenceState,
    LiveWorldModelService,
)


def _hash(character: str) -> str:
    return character * 64


def _frames() -> np.ndarray:
    return np.arange(2 * 32 * 32 * 3, dtype=np.uint8).reshape(2, 32, 32, 3)


def _model(**updates) -> ModelArtifactIdentity:
    values = {
        "family": "vjepa2.1",
        "integration_kind": "official-upstream",
        "source_repository": "https://github.com/facebookresearch/vjepa2",
        "source_commit": "a" * 40,
        "encoder_version": "vjepa2.1-vitb",
        "encoder_checkpoint_sha256": _hash("1"),
        "dynamics_version": "vjepa2.1-predictor",
        "dynamics_checkpoint_sha256": _hash("2"),
        "outcome_head_version": "flood-semantic-probe-v2",
        "outcome_head_sha256": _hash("3"),
        "calibration_version": "flood-calibration-v2",
        "calibration_artifact_sha256": _hash("4"),
        "training_snapshot_sha256": _hash("5"),
        "preprocessing_version": "vjepa2.1-384-v1",
        "feature_schema_version": "vjepa-spatiotemporal-v2",
        "action_schema_version": "flood-actions-v2",
        "supported_action_types": ("dispatch_rescue_boat",),
    }
    values.update(updates)
    return ModelArtifactIdentity(**values)


def _observation(frames: np.ndarray | None = None) -> ObservationProvenance:
    frames = _frames() if frames is None else frames
    return ObservationProvenance(
        observation_id="simobs-live-1",
        observation_sha256=_hash("6"),
        frames_sha256=hashlib.sha256(np.ascontiguousarray(frames).tobytes()).hexdigest(),
        controller_manifest_sha256=_hash("7"),
        sensor_model_version="flood-camera-v2",
        observed_at=90.0,
        study_partition="development-v2",
    )


def _route_request(
    model: ModelArtifactIdentity,
    observation: ObservationProvenance,
) -> RouteWorldModelRequestV2:
    return RouteWorldModelRequestV2(
        plan_id="plan-1",
        route_id="north",
        asset_id="boat-1",
        action_type="dispatch_rescue_boat",
        belief_status="open",
        belief_confidence=0.8,
        observation_age_s=10.0,
        observed_depth_m=0.3,
        projected_depth_m=0.4,
        route_closure_depth_m=0.72,
        route_susceptibility=1.0,
        travel_time_s=600.0,
        water_rise_rate=0.00015,
        rain_intensity=0.4,
        upstream_inflow=0.3,
        weather_forecast=0.25,
        sensor_noise=0.1,
        packet_loss=0.02,
        declared_ood_severity=0.2,
        sensor_quality=0.9,
        asset_resource=0.95,
        asset_weather_tolerance=0.8,
        visual_observation_id=observation.observation_id,
        visual_observation_hash=observation.observation_sha256,
        visual_frames_sha256=observation.frames_sha256,
        visual_sensor_version=observation.sensor_model_version,
        visual_observed_at=observation.observed_at,
        expected_model_bundle_sha256=model.bundle_sha256,
        prediction_horizons_s=(60.0, 180.0),
        action_parameters={"duration_s": 600.0},
    )


def _request(
    model: ModelArtifactIdentity | None = None,
    observation: ObservationProvenance | None = None,
) -> LiveInferenceRequest:
    model = _model() if model is None else model
    observation = _observation() if observation is None else observation
    return LiveInferenceRequest(
        route_request=_route_request(model, observation),
        observation=observation,
        model=model,
    )


def _state() -> SemanticWorldStatePrediction:
    return SemanticWorldStatePrediction(
        horizons_s=(60.0, 180.0),
        water_depth_m=(0.4, 0.5),
        obstruction_probability=(0.1, 0.2),
        flow_severity=(0.3, 0.4),
        visibility=(0.8, 0.7),
        operational_state={"asset_resource": 0.9},
        epistemic_uncertainty=(0.1, 0.2),
        support=(0.9, 0.8),
        ood_score=(0.05, 0.1),
    )


def test_content_addressed_artifact_roundtrip_is_idempotent(tmp_path: Path) -> None:
    store = ContentAddressedInferenceStore(tmp_path / "store")
    latent = np.arange(24, dtype=np.float32).reshape(2, 3, 4)
    kwargs = {
        "request_sha256": _hash("8"),
        "model_bundle_sha256": _model().bundle_sha256,
        "observation_sha256": _hash("6"),
        "action_type": "dispatch_rescue_boat",
        "semantic_state": _state(),
        "latent_tokens": latent,
        "environment_manifest_sha256": _hash("9"),
        "diagnostics": {"predictor_loss": 0.2},
    }
    first = store.put(**kwargs)
    second = store.put(**kwargs)
    loaded, loaded_latent = store.get_for_request(_hash("8")) or (None, None)
    assert first == second == loaded
    assert np.array_equal(loaded_latent, latent)


def test_artifact_store_rejects_nonfinite_tensors_and_tampering(tmp_path: Path) -> None:
    store = ContentAddressedInferenceStore(tmp_path / "store")
    kwargs = {
        "request_sha256": _hash("8"),
        "model_bundle_sha256": _model().bundle_sha256,
        "observation_sha256": _hash("6"),
        "action_type": "dispatch_rescue_boat",
        "semantic_state": _state(),
        "environment_manifest_sha256": _hash("9"),
    }
    with pytest.raises(ValueError, match="finite tensor"):
        store.put(**kwargs, latent_tokens=np.array([np.nan], dtype=np.float32))
    metadata = store.put(**kwargs, latent_tokens=np.ones((2, 3), dtype=np.float32))
    tensor_path = (
        tmp_path / "store" / "artifacts" / metadata.artifact_sha256[:2] / metadata.tensor_file
    )
    tensor_path.write_bytes(b"tampered")
    with pytest.raises(ArtifactIntegrityError, match="file hash"):
        store.get(metadata.artifact_sha256)


def test_artifact_store_rejects_symlinked_roots_and_pointers(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    symlink = tmp_path / "store-link"
    symlink.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        ContentAddressedInferenceStore(symlink)

    store = ContentAddressedInferenceStore(tmp_path / "store")
    outside = tmp_path / "outside"
    outside.write_text("{}", encoding="utf-8")
    pointer = store.requests_root / f"{_hash('8')}.json"
    os.symlink(outside, pointer)
    with pytest.raises(ArtifactIntegrityError, match="unsafe"):
        store.get_for_request(_hash("8"))


class _Reader:
    def __init__(self, frames: np.ndarray):
        self.frames = frames

    def read_frames(self, observation: ObservationProvenance) -> np.ndarray:
        return self.frames.copy()


class _Backend:
    def __init__(
        self,
        model: ModelArtifactIdentity,
        *,
        delay_s: float = 0.0,
        fail: bool = False,
        nonfinite: bool = False,
        wrong_horizons: bool = False,
        latent_only: bool = False,
        environment_sha256: str = _hash("9"),
    ):
        self._model = model
        self.delay_s = delay_s
        self.fail = fail
        self.nonfinite = nonfinite
        self.wrong_horizons = wrong_horizons
        self.latent_only = latent_only
        self._environment_sha256 = environment_sha256
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    @property
    def identity(self) -> ModelArtifactIdentity:
        return self._model

    @property
    def environment_manifest_sha256(self) -> str:
        return self._environment_sha256

    def infer(self, *, frames: np.ndarray, request: RouteWorldModelRequestV2) -> LiveBackendOutput:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(self.delay_s)
            if self.fail:
                raise RuntimeError("private backend detail")
            latent = np.ones((2, 4), dtype=np.float32)
            if self.nonfinite:
                latent[0, 0] = np.nan
            state = _state()
            if self.wrong_horizons:
                state = state.model_copy(update={"horizons_s": (60.0, 181.0)})
            return LiveBackendOutput(
                None if self.latent_only else state,
                latent,
                {"batch_size": 1},
            )
        finally:
            with self._lock:
                self.active -= 1


def _wait(service: LiveWorldModelService, request_sha256: str, timeout_s: float = 3.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        receipt = service.poll(request_sha256)
        if receipt and receipt.state in {LiveInferenceState.COMPLETED, LiveInferenceState.FAILED}:
            return receipt
        time.sleep(0.01)
    raise AssertionError("live inference did not finish")


def test_live_service_serializes_inference_and_replays_verified_cache(tmp_path: Path) -> None:
    model = _model()
    frames = _frames()
    backend = _Backend(model, delay_s=0.03)
    store = ContentAddressedInferenceStore(tmp_path / "store")
    service = LiveWorldModelService(
        backend=backend,
        observation_reader=_Reader(frames),
        artifact_store=store,
        queue_capacity=3,
    )
    first = _request(model)
    second_observation = _observation(frames)
    second_observation = second_observation.model_copy(
        update={"observation_id": "simobs-live-2", "observation_sha256": _hash("a")}
    )
    second = _request(model, second_observation)
    service.start()
    service.submit(first)
    service.submit(second)
    first_receipt = _wait(service, first.request_sha256)
    assert first_receipt.state == LiveInferenceState.COMPLETED
    assert first_receipt.wall_duration_ms is not None
    assert first_receipt.wall_duration_ms >= 20.0
    assert first_receipt.queue_wait_ms is not None
    assert first_receipt.backend_duration_ms is not None
    assert first_receipt.backend_duration_ms >= 20.0
    assert first_receipt.persistence_duration_ms is not None
    assert first_receipt.total_service_ms is not None
    assert first_receipt.total_service_ms >= first_receipt.wall_duration_ms
    assert first_receipt.device_type == "cpu"
    assert first_receipt.precision == "float32"
    assert first_receipt.environment_manifest_sha256 == _hash("9")
    assert store.get_request(first.request_sha256) == first.model_dump(mode="json")
    assert _wait(service, second.request_sha256).state == LiveInferenceState.COMPLETED
    assert backend.max_active == 1
    service.close()

    replay = LiveWorldModelService(
        backend=_Backend(model),
        observation_reader=_Reader(frames),
        artifact_store=store,
    )
    receipt = replay.submit(first)
    assert receipt.state == LiveInferenceState.COMPLETED
    assert receipt.cache_hit is True
    assert receipt.wall_duration_ms == 0.0
    assert receipt.total_service_ms is not None

    mismatched_environment = LiveWorldModelService(
        backend=_Backend(model, environment_sha256=_hash("e")),
        observation_reader=_Reader(frames),
        artifact_store=store,
    )
    mismatch = mismatched_environment.submit(first)
    assert mismatch.state == LiveInferenceState.FAILED
    assert mismatch.failure_code == LiveInferenceFailureCode.ARTIFACT_INTEGRITY
    assert mismatch.failure_type == "ProducerEnvironmentMismatch"


def test_live_service_fails_closed_on_observation_backend_and_output_errors(tmp_path: Path) -> None:
    model = _model()
    request = _request(model)
    cases = (
        (_Reader(np.zeros_like(_frames())), _Backend(model), LiveInferenceFailureCode.OBSERVATION_INTEGRITY),
        (_Reader(_frames()), _Backend(model, fail=True), LiveInferenceFailureCode.BACKEND_FAILURE),
        (_Reader(_frames()), _Backend(model, nonfinite=True), LiveInferenceFailureCode.OUTPUT_INVALID),
        (
            _Reader(_frames()),
            _Backend(model, wrong_horizons=True),
            LiveInferenceFailureCode.OUTPUT_INVALID,
        ),
    )
    for index, (reader, backend, expected) in enumerate(cases):
        service = LiveWorldModelService(
            backend=backend,
            observation_reader=reader,
            artifact_store=ContentAddressedInferenceStore(tmp_path / f"store-{index}"),
        )
        service.start()
        service.submit(request)
        receipt = _wait(service, request.request_sha256)
        assert receipt.state == LiveInferenceState.FAILED
        assert receipt.failure_code == expected
        assert "private backend detail" not in (receipt.failure_type or "")
        assert service.artifact(request.request_sha256) is None
        service.close()


def test_live_service_rejects_wrong_bundle_backpressure_and_closed_use(tmp_path: Path) -> None:
    model = _model()
    service = LiveWorldModelService(
        backend=_Backend(model),
        observation_reader=_Reader(_frames()),
        artifact_store=ContentAddressedInferenceStore(tmp_path / "store"),
        queue_capacity=1,
    )
    wrong_model = _model(outcome_head_sha256=_hash("e"))
    with pytest.raises(LiveInferenceError, match="does not match"):
        service.submit(_request(wrong_model))

    first = _request(model)
    service.submit(first)
    second_observation = _observation().model_copy(
        update={"observation_id": "simobs-live-3", "observation_sha256": _hash("b")}
    )
    with pytest.raises(LiveInferenceBackpressure, match="queue is full"):
        service.submit(_request(model, second_observation))
    service.close()
    with pytest.raises(LiveInferenceError, match="closed"):
        service.submit(first)


def test_live_service_accepts_explicit_latent_only_supporting_output(
    tmp_path: Path,
) -> None:
    model = _model()
    service = LiveWorldModelService(
        backend=_Backend(model, latent_only=True),
        observation_reader=_Reader(_frames()),
        artifact_store=ContentAddressedInferenceStore(tmp_path / "store"),
    )
    request = _request(model)
    service.start()
    service.submit(request)
    assert _wait(service, request.request_sha256).state == LiveInferenceState.COMPLETED
    artifact = service.artifact(request.request_sha256)
    assert artifact is not None
    assert artifact[0].semantic_state is None
    service.close()


def test_live_request_rejects_truth_fields_and_model_link_mismatch() -> None:
    request = _request()
    payload = request.model_dump()
    payload["audit_snapshot"] = {"water_depth_m": 1.0}
    with pytest.raises(ValidationError, match="Extra inputs"):
        LiveInferenceRequest(**payload)

    wrong = _model(outcome_head_sha256=_hash("e"))
    with pytest.raises(ValidationError, match="different model bundle"):
        LiveInferenceRequest(
            route_request=request.route_request,
            observation=request.observation,
            model=wrong,
        )

    route_payload = request.route_request.model_dump()
    route_payload["action_parameters"] = {
        "nested": {"audit_snapshot": {"water_depth_m": 9.0}}
    }
    with pytest.raises(ValidationError, match="audit-only simulator state"):
        RouteWorldModelRequestV2(**route_payload)
