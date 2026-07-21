from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path

import numpy as np

from trace_jepa.workbench.engine import DynamicRun
from trace_jepa.workbench.models import EventType, EventVisibility, ScenarioLevel
from trace_jepa.worldmodels.contracts import (
    ModelArtifactIdentity,
    RouteWorldModelRequestV2,
    SemanticWorldStatePrediction,
)
from trace_jepa.worldmodels.live_artifacts import ContentAddressedInferenceStore
from trace_jepa.worldmodels.live_observations import (
    VerifiedSimulatorObservationRepository,
)
from trace_jepa.worldmodels.live_service import (
    LiveBackendOutput,
    LiveWorldModelService,
)
from trace_jepa.worldmodels.live_support import LiveSupportingInferenceBridge
from trace_jepa.worldmodels.simulator_observations import (
    SENSOR_MODEL_VERSION,
    SimulatorSensorSnapshot,
    SimulatorVisualObservationStore,
)


SCENARIO = Path(__file__).parents[1] / "configs" / "scenarios" / "riverside_flood_v1.yaml"


def _hash(character: str) -> str:
    return character * 64


def _identity() -> ModelArtifactIdentity:
    return ModelArtifactIdentity(
        family="vjepa2.1-shadow",
        integration_kind="official-upstream",
        source_repository="https://github.com/facebookresearch/vjepa2",
        source_commit="a" * 40,
        encoder_version="vjepa2.1-vitb",
        encoder_checkpoint_sha256=_hash("1"),
        dynamics_version="vjepa2.1-predictor",
        dynamics_checkpoint_sha256=_hash("2"),
        outcome_head_version="semantic-probe-v2",
        outcome_head_sha256=_hash("3"),
        calibration_version="development-calibration-v2",
        calibration_artifact_sha256=_hash("4"),
        training_snapshot_sha256=_hash("5"),
        preprocessing_version="vjepa2.1-384-v1",
        feature_schema_version="vjepa-spatiotemporal-v2",
        action_schema_version="flood-actions-dynamic-v1",
        supported_action_types=(
            "deploy_ground_team",
            "dispatch_rescue_boat",
            "evacuate_to_safety",
        ),
    )


class _DelayedBackend:
    device_type = "cpu"
    precision = "float32"

    def __init__(self, delay_s: float = 0.12):
        self._identity = _identity()
        self.delay_s = delay_s
        self.calls = 0
        self.received_requests: list[RouteWorldModelRequestV2] = []
        self._lock = threading.Lock()

    @property
    def identity(self) -> ModelArtifactIdentity:
        return self._identity

    @property
    def environment_manifest_sha256(self) -> str:
        return _hash("9")

    def infer(
        self, *, frames: np.ndarray, request: RouteWorldModelRequestV2
    ) -> LiveBackendOutput:
        with self._lock:
            self.calls += 1
            self.received_requests.append(request)
        time.sleep(self.delay_s)
        count = len(request.prediction_horizons_s)
        state = SemanticWorldStatePrediction(
            horizons_s=request.prediction_horizons_s,
            water_depth_m=tuple(0.4 for _ in range(count)),
            obstruction_probability=tuple(0.1 for _ in range(count)),
            flow_severity=tuple(0.2 for _ in range(count)),
            visibility=tuple(0.8 for _ in range(count)),
            operational_state={"supporting_only": 1.0},
            epistemic_uncertainty=tuple(0.2 for _ in range(count)),
            support=tuple(0.8 for _ in range(count)),
            ood_score=tuple(0.1 for _ in range(count)),
        )
        return LiveBackendOutput(
            semantic_state=state,
            latent_tokens=np.ones((2, 8), dtype=np.float32),
            diagnostics={"test_backend": True},
        )


def _capture(root: Path):
    store = SimulatorVisualObservationStore(root, num_frames=4, size=32)
    captured = store.capture(
        SimulatorSensorSnapshot(
            run_id="live-e2e",
            episode_id="live-e2e-episode",
            route_id="north_channel",
            asset_id="survey_drone_1",
            observed_at=0.0,
            environment_tick_index=0,
            sensor_seed=7,
            water_depth_m=0.35,
            route_closure_depth_m=0.72,
            debris_blocked=False,
            rain_intensity=0.25,
            upstream_inflow=0.2,
            weather_severity=0.25,
            sensor_noise=0.1,
            sensor_quality=0.9,
            packet_delivered=True,
            categorical_report_accurate=True,
            sensor_model_version=SENSOR_MODEL_VERSION,
        )
    )
    return captured


def _deliver(run: DynamicRun, captured) -> None:
    run.emit(
        EventType.OBSERVATION,
        source="survey_drone_1",
        scenario_level=ScenarioLevel.S1,
        visibility=EventVisibility.CONTROLLER,
        payload={
            "kind": "route",
            "route_id": "north_channel",
            "reported_status": "open",
            "confidence": 0.9,
            "source": "survey_drone_1",
            "observed_at": 0.0,
            "visual_observation_id": captured.observation_id,
            "visual_observation_hash": captured.observation_hash,
            "visual_observed_at": 0.0,
            "visual_sensor_version": SENSOR_MODEL_VERSION,
        },
    )


def _decision_signature(
    run: DynamicRun,
) -> list[tuple[str, tuple[str, str, tuple[str, ...]]]]:
    result = {}
    for record in run.runtime.repository.all():
        if record.consumer_actions:
            result[str(record.metadata["lineage_key"])] = (
                record.consumer_actions[-1].decision.value,
                record.final_status.value,
                tuple(record.failed_gates),
            )
    return sorted(result.items())


def test_delivered_observation_runs_nonblocking_shadow_inference_without_new_trigger(
    tmp_path: Path,
) -> None:
    observation_root = tmp_path / "observations"
    captured = _capture(observation_root)
    backend = _DelayedBackend()
    service = LiveWorldModelService(
        backend=backend,
        observation_reader=VerifiedSimulatorObservationRepository(observation_root),
        artifact_store=ContentAddressedInferenceStore(tmp_path / "inference-store"),
        queue_capacity=8,
    )
    bridge = LiveSupportingInferenceBridge(
        service=service,
        observations=VerifiedSimulatorObservationRepository(observation_root),
    )
    run = DynamicRun(
        run_id="with-shadow",
        scenario_path=SCENARIO,
        artifact_root=tmp_path / "runs",
        supporting_world_model=bridge,
    )
    _deliver(run, captured)

    started = time.perf_counter()
    run._run_plan_cycle()
    first_cycle_s = time.perf_counter() - started
    assert first_cycle_s < backend.delay_s

    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and not run.controller.poll_supporting_inference(
        run.state
    ):
        time.sleep(0.01)
    else:
        if time.monotonic() >= deadline:
            raise AssertionError("supporting inference did not complete")
    record_count_after_attachment = len(run.runtime.repository.all())
    run._run_plan_cycle()

    attachments = []
    for path in run.runtime.ledger.root.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        attachment = payload["reachability_evidence"].get(
            "supporting_worldmodel_inference"
        )
        if attachment is not None:
            attachments.append(attachment)
    assert attachments
    assert all(item["state"] == "completed" for item in attachments)
    assert all(item["used_for_trace_gate"] is False for item in attachments)
    assert all(item["artifact_sha256"] for item in attachments)
    assert all(item["model_bundle_sha256"] == _identity().bundle_sha256 for item in attachments)
    assert all(item["observation_sha256"] == captured.observation_hash for item in attachments)
    assert backend.received_requests
    assert all("truth" not in item.model_dump_json().lower() for item in backend.received_requests)
    assert run.runtime.repository.verify_chain()
    assert record_count_after_attachment > 0

    baseline = DynamicRun(
        run_id="without-shadow",
        scenario_path=SCENARIO,
        artifact_root=tmp_path / "baseline-runs",
    )
    _deliver(baseline, captured)
    baseline._run_plan_cycle()
    baseline._run_plan_cycle()
    assert _decision_signature(run) == _decision_signature(baseline)
    bridge.close()


def test_blocking_appendix_mode_binds_evidence_before_authoritative_selection(
    tmp_path: Path,
) -> None:
    observation_root = tmp_path / "observations"
    captured = _capture(observation_root)
    backend = _DelayedBackend(delay_s=0.03)
    repository = VerifiedSimulatorObservationRepository(observation_root)
    bridge = LiveSupportingInferenceBridge(
        service=LiveWorldModelService(
            backend=backend,
            observation_reader=repository,
            artifact_store=ContentAddressedInferenceStore(tmp_path / "store"),
        ),
        observations=repository,
    )
    run = DynamicRun(
        run_id="blocking-support",
        scenario_path=SCENARIO,
        artifact_root=tmp_path / "runs",
        supporting_world_model=bridge,
        wait_for_supporting_inference=True,
    )
    _deliver(run, captured)
    run._run_plan_cycle()
    attachments = [
        json.loads(path.read_text(encoding="utf-8"))["reachability_evidence"].get(
            "supporting_worldmodel_inference"
        )
        for path in run.runtime.ledger.root.glob("*.json")
    ]
    attachments = [item for item in attachments if item is not None]
    assert attachments
    assert all(item["state"] == "completed" for item in attachments)
    baseline = DynamicRun(
        run_id="blocking-baseline",
        scenario_path=SCENARIO,
        artifact_root=tmp_path / "baseline",
    )
    _deliver(baseline, captured)
    baseline._run_plan_cycle()
    assert _decision_signature(run) == _decision_signature(baseline)
    bridge.close()


def test_reset_invalidates_pre_reset_supporting_inference(tmp_path: Path) -> None:
    observation_root = tmp_path / "observations"
    captured = _capture(observation_root)
    backend = _DelayedBackend(delay_s=0.08)
    repository = VerifiedSimulatorObservationRepository(observation_root)
    bridge = LiveSupportingInferenceBridge(
        service=LiveWorldModelService(
            backend=backend,
            observation_reader=repository,
            artifact_store=ContentAddressedInferenceStore(tmp_path / "store"),
        ),
        observations=repository,
    )
    run = DynamicRun(
        run_id="reset-support",
        scenario_path=SCENARIO,
        artifact_root=tmp_path / "runs",
        supporting_world_model=bridge,
    )
    _deliver(run, captured)
    run._run_plan_cycle()
    asyncio.run(run.reset())
    time.sleep(0.12)
    assert run.controller.poll_supporting_inference(run.state) is False
    assert run.runtime.repository.all() == []
    bridge.close()
