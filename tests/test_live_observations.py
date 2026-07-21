from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from trace_jepa.worldmodels.live_observations import (
    ObservationIntegrityError,
    VerifiedSimulatorObservationRepository,
)
from trace_jepa.worldmodels.simulator_observations import (
    SENSOR_MODEL_VERSION,
    SimulatorSensorSnapshot,
    SimulatorVisualObservationStore,
)


def _capture(root: Path, *, partition: str = "development"):
    store = SimulatorVisualObservationStore(root, num_frames=4, size=32)
    return store.capture(
        SimulatorSensorSnapshot(
            run_id="run-live",
            episode_id="episode-live",
            study_partition=partition,
            route_id="north",
            asset_id="drone-1",
            observed_at=60.0,
            environment_tick_index=2,
            sensor_seed=7,
            water_depth_m=0.4,
            route_closure_depth_m=0.72,
            debris_blocked=False,
            rain_intensity=0.3,
            upstream_inflow=0.2,
            weather_severity=0.25,
            sensor_noise=0.1,
            sensor_quality=0.9,
            packet_delivered=True,
            categorical_report_accurate=True,
            sensor_model_version=SENSOR_MODEL_VERSION,
        )
    )


def test_repository_returns_controller_safe_provenance_and_verified_frames(
    tmp_path: Path,
) -> None:
    captured = _capture(tmp_path)
    repository = VerifiedSimulatorObservationRepository(tmp_path)
    provenance = repository.provenance(
        captured.observation_id,
        expected_observation_sha256=captured.observation_hash,
    )
    frames = repository.read_frames(provenance)
    assert frames.dtype == np.uint8
    assert frames.shape == (4, 32, 32, 3)
    assert provenance.observation_sha256 == captured.observation_hash
    assert "water_depth" not in provenance.model_dump_json()
    assert "audit_snapshot" not in provenance.model_dump_json()


def test_repository_rejects_controller_hash_mismatch_and_test_partition(
    tmp_path: Path,
) -> None:
    development = tmp_path / "development"
    development.mkdir()
    captured = _capture(development)
    repository = VerifiedSimulatorObservationRepository(development)
    with pytest.raises(ObservationIntegrityError, match="controller belief hash"):
        repository.provenance(
            captured.observation_id,
            expected_observation_sha256="0" * 64,
        )

    test_root = tmp_path / "test"
    test_root.mkdir()
    test_capture = _capture(test_root, partition="test")
    with pytest.raises(ObservationIntegrityError, match="not authorized"):
        VerifiedSimulatorObservationRepository(test_root).provenance(
            test_capture.observation_id,
            expected_observation_sha256=test_capture.observation_hash,
        )


def test_repository_rejects_manifest_frame_and_provenance_tampering(
    tmp_path: Path,
) -> None:
    captured = _capture(tmp_path)
    repository = VerifiedSimulatorObservationRepository(tmp_path)
    provenance = repository.provenance(
        captured.observation_id,
        expected_observation_sha256=captured.observation_hash,
    )

    payload = json.loads(captured.manifest_path.read_text(encoding="utf-8"))
    payload["sensor_model_version"] = "substituted-camera"
    captured.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ObservationIntegrityError, match="provenance"):
        repository.read_frames(provenance)

    captured = _capture(tmp_path)
    with captured.frames_path.open("wb") as handle:
        np.savez_compressed(
            handle,
            frames=np.zeros((4, 32, 32, 3), dtype=np.uint8),
            observation_id=np.asarray(captured.observation_id),
            observation_hash=np.asarray(captured.observation_hash),
        )
    with pytest.raises(ObservationIntegrityError, match="frame hash"):
        repository.provenance(
            captured.observation_id,
            expected_observation_sha256=captured.observation_hash,
        )


def test_repository_rejects_unsafe_identifier(tmp_path: Path) -> None:
    with pytest.raises(ObservationIntegrityError, match="unsafe"):
        VerifiedSimulatorObservationRepository(tmp_path).provenance(
            "../outside",
            expected_observation_sha256="0" * 64,
        )
