from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from trace_jepa.workbench.engine import DynamicRun
from trace_jepa.workbench.models import EventType
from trace_jepa.worldmodels.adapters import CachedRouteFeatureProvider
from trace_jepa.worldmodels.contracts import RouteWorldModelRequest
from trace_jepa.worldmodels.encoding import (
    DeterministicSmokeEncoder,
    encode_simulator_observations,
)
from trace_jepa.worldmodels.simulator_observations import (
    SimulatorSensorSnapshot,
    SimulatorVisualObservationStore,
    render_simulator_sensor_clip,
)


SCENARIO = Path(__file__).parents[1] / "configs" / "scenarios" / "riverside_flood_v1.yaml"


def snapshot(**updates) -> SimulatorSensorSnapshot:
    base = SimulatorSensorSnapshot(
        run_id="run-test",
        episode_id="episode-test",
        route_id="north_channel",
        asset_id="survey_drone_1",
        observed_at=42.0,
        environment_tick_index=12,
        sensor_seed=7,
        water_depth_m=0.46,
        route_closure_depth_m=0.72,
        debris_blocked=True,
        rain_intensity=0.5,
        upstream_inflow=0.4,
        weather_severity=0.35,
        sensor_noise=0.1,
        sensor_quality=0.9,
        packet_delivered=True,
        categorical_report_accurate=True,
    )
    return base.model_copy(update=updates)


def test_simulator_sensor_render_is_deterministic_and_state_sensitive() -> None:
    first = render_simulator_sensor_clip(snapshot(), num_frames=4, size=32)
    repeated = render_simulator_sensor_clip(snapshot(), num_frames=4, size=32)
    deeper = render_simulator_sensor_clip(
        snapshot(water_depth_m=0.68), num_frames=4, size=32
    )
    assert np.array_equal(first, repeated)
    assert not np.array_equal(first, deeper)


def test_upstream_style_temporal_sampling_spans_source_motion() -> None:
    dense = render_simulator_sensor_clip(snapshot(), num_frames=8, size=32)
    sampled = render_simulator_sensor_clip(
        snapshot(), num_frames=2, size=32, frame_step=4
    )
    assert np.array_equal(sampled[0], dense[0])
    assert np.array_equal(sampled[1], dense[4])


def test_visual_observation_store_writes_verifiable_manifest(tmp_path) -> None:
    store = SimulatorVisualObservationStore(tmp_path, num_frames=4, size=32)
    first = store.capture(snapshot())
    repeated = store.capture(snapshot())

    assert first.observation_id == repeated.observation_id
    assert first.observation_hash == repeated.observation_hash
    assert first.controller_usable is True
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest["observation_id"] == first.observation_id
    assert manifest["frames_sha256"] == first.frames_sha256
    assert manifest["controller_usable"] is True
    with np.load(first.frames_path, allow_pickle=False) as payload:
        assert payload["frames"].shape == (4, 32, 32, 3)
        assert str(payload["observation_hash"].item()) == first.observation_hash


def test_packet_lost_capture_is_audit_only(tmp_path) -> None:
    store = SimulatorVisualObservationStore(tmp_path, num_frames=4, size=32)
    captured = store.capture(snapshot(packet_delivered=False))
    manifest = json.loads(captured.manifest_path.read_text(encoding="utf-8"))
    assert captured.controller_usable is False
    assert manifest["controller_usable"] is False


def test_dynamic_run_delivers_visual_identifier_without_simulator_truth(tmp_path) -> None:
    observation_root = tmp_path / "observations"
    run = DynamicRun(
        run_id="sensor-integration-test",
        scenario_path=SCENARIO,
        artifact_root=tmp_path / "runs",
        visual_observation_store=SimulatorVisualObservationStore(
            observation_root, num_frames=4, size=32
        ),
        observation_episode_id="development-episode-test",
    )
    run.emit(
        EventType.SET_S1_PARAMETERS,
        source="test",
        payload={"packet_loss": 0.0, "drone_report_accuracy": 1.0},
    )
    drone = run.state.truth.assets["survey_drone_1"]
    run.emit(
        EventType.ACTION_STARTED,
        source="test",
        payload={
            "asset_id": drone.asset_id,
            "action_type": "verify_route",
            "route_id": "north_channel",
            "target": drone.position.model_dump(mode="json"),
            "path": [],
        },
    )
    run._complete_action(drone.asset_id)
    run._deliver_scheduled()

    belief = run.state.controller.route_beliefs["north_channel"]
    assert belief.visual_observation_id is not None
    assert belief.visual_observation_hash is not None
    assert belief.visual_observed_at == 0.0
    assert belief.visual_sensor_version == "flood-sim-drone-rgb-v2"
    assert (observation_root / f"{belief.visual_observation_id}.npz").is_file()
    assert (observation_root / f"{belief.visual_observation_id}.json").is_file()

    observation_event = next(
        event
        for event in reversed(run.event_store.all())
        if event.event_type == EventType.OBSERVATION
        and event.payload.get("route_id") == "north_channel"
    )
    assert observation_event.payload["visual_observation_id"] == belief.visual_observation_id
    assert observation_event.payload["visual_observation_hash"] == belief.visual_observation_hash
    for audit_only_key in (
        "audit_snapshot",
        "water_depth_m",
        "debris_blocked",
        "weather_severity",
    ):
        assert audit_only_key not in observation_event.payload
    assert run.replay_state().model_dump(mode="json") == run.state.model_dump(mode="json")


def test_nonvisual_observation_does_not_refresh_visual_provenance(tmp_path) -> None:
    run = DynamicRun(
        run_id="sensor-provenance-test",
        scenario_path=SCENARIO,
        artifact_root=tmp_path / "runs",
    )
    run.emit(
        EventType.OBSERVATION,
        source="test-camera",
        payload={
            "kind": "route",
            "route_id": "north_channel",
            "reported_status": "open",
            "confidence": 0.9,
            "observed_at": 12.0,
            "visual_observation_id": "simobs-known",
            "visual_observation_hash": "a" * 64,
            "visual_observed_at": 12.0,
            "visual_sensor_version": "flood-sim-drone-rgb-v2",
        },
    )
    run.emit(
        EventType.OBSERVATION,
        source="test-gauge",
        payload={
            "kind": "route_depth",
            "route_id": "north_channel",
            "water_depth": 0.42,
            "observed_at": 30.0,
        },
    )
    belief = run.state.controller.route_beliefs["north_channel"]
    assert belief.visual_observation_id == "simobs-known"
    assert belief.visual_observation_hash == "a" * 64
    assert belief.visual_observed_at == 12.0


def test_test_partition_remains_locked_without_frozen_manifest(tmp_path) -> None:
    with pytest.raises(ValueError, match="frozen authorization manifest"):
        DynamicRun(
            scenario_path=SCENARIO,
            artifact_root=tmp_path / "runs",
            visual_observation_store=SimulatorVisualObservationStore(
                tmp_path / "observations", num_frames=4, size=32
            ),
            observation_study_partition="test",
        )


def test_offline_encoder_verifies_clip_and_populates_runtime_cache(tmp_path) -> None:
    observation_dir = tmp_path / "observations"
    captured = SimulatorVisualObservationStore(
        observation_dir, num_frames=4, size=32
    ).capture(snapshot())
    cache_dir = tmp_path / "features"
    summary = encode_simulator_observations(
        observation_dir,
        cache_dir,
        DeterministicSmokeEncoder(),
        encoder_version="deterministic-smoke-encoder-v1",
        encoder_checkpoint_sha256="deterministic-smoke-no-checkpoint",
    )
    assert summary.encoded == 1
    assert summary.cache_hits == 0
    provider = CachedRouteFeatureProvider(
        cache_dir,
        encoder_version="deterministic-smoke-encoder-v1",
        encoder_checkpoint_sha256="deterministic-smoke-no-checkpoint",
    )
    request = RouteWorldModelRequest(
        plan_id="plan-test",
        route_id="north_channel",
        asset_id="rescue_boat_1",
        action_type="dispatch_rescue_boat",
        belief_status="open",
        belief_confidence=0.9,
        observation_age_s=1.0,
        projected_depth_m=0.4,
        route_closure_depth_m=0.72,
        route_susceptibility=1.0,
        travel_time_s=300.0,
        water_rise_rate=0.0001,
        rain_intensity=0.2,
        upstream_inflow=0.2,
        weather_forecast=0.2,
        sensor_noise=0.1,
        packet_loss=0.0,
        declared_ood_severity=0.1,
        sensor_quality=0.9,
        asset_resource=0.9,
        asset_weather_tolerance=0.8,
        visual_observation_id=captured.observation_id,
    )
    feature = provider.features(request)
    assert feature.vector.shape == (9,)
    assert feature.observation_hash == captured.observation_hash

    repeated = encode_simulator_observations(
        observation_dir,
        cache_dir,
        DeterministicSmokeEncoder(),
        encoder_version="deterministic-smoke-encoder-v1",
        encoder_checkpoint_sha256="deterministic-smoke-no-checkpoint",
    )
    assert repeated.encoded == 0
    assert repeated.cache_hits == 1


def test_offline_encoder_skips_packet_lost_clip(tmp_path) -> None:
    observation_dir = tmp_path / "observations"
    SimulatorVisualObservationStore(observation_dir, num_frames=4, size=32).capture(
        snapshot(packet_delivered=False)
    )
    summary = encode_simulator_observations(
        observation_dir,
        tmp_path / "features",
        DeterministicSmokeEncoder(),
        encoder_version="deterministic-smoke-encoder-v1",
        encoder_checkpoint_sha256="deterministic-smoke-no-checkpoint",
    )
    assert summary.skipped_audit_only == 1
    assert summary.encoded == 0


def test_offline_encoder_rejects_tampered_clip(tmp_path) -> None:
    observation_dir = tmp_path / "observations"
    captured = SimulatorVisualObservationStore(
        observation_dir, num_frames=4, size=32
    ).capture(snapshot())
    with np.load(captured.frames_path, allow_pickle=False) as payload:
        frames = payload["frames"].copy()
        observation_id = payload["observation_id"].copy()
        observation_hash = payload["observation_hash"].copy()
    frames[0, 0, 0, 0] ^= 1
    np.savez_compressed(
        captured.frames_path,
        frames=frames,
        observation_id=observation_id,
        observation_hash=observation_hash,
    )
    with pytest.raises(ValueError, match="frame digest mismatch"):
        encode_simulator_observations(
            observation_dir,
            tmp_path / "features",
            DeterministicSmokeEncoder(),
            encoder_version="deterministic-smoke-encoder-v1",
            encoder_checkpoint_sha256="deterministic-smoke-no-checkpoint",
        )


def test_offline_encoder_shards_form_exact_disjoint_inventory(tmp_path) -> None:
    observation_dir = tmp_path / "observations"
    store = SimulatorVisualObservationStore(observation_dir, num_frames=4, size=32)
    expected = {
        store.capture(snapshot(episode_id=f"episode-{index}")).observation_id
        for index in range(7)
    }
    observed: set[str] = set()
    for shard_index in range(3):
        summary = encode_simulator_observations(
            observation_dir,
            tmp_path / "features",
            DeterministicSmokeEncoder(),
            encoder_version="deterministic-smoke-encoder-v1",
            encoder_checkpoint_sha256="deterministic-smoke-no-checkpoint",
            shard_index=shard_index,
            shard_count=3,
        )
        assert not observed.intersection(summary.observation_ids)
        observed.update(summary.observation_ids)
    assert observed == expected
