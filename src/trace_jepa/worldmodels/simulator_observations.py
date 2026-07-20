from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from trace_jepa.util import sha256_value


SENSOR_MODEL_VERSION = "flood-sim-drone-rgb-v2"


class SimulatorSensorSnapshot(BaseModel):
    """Audit-only simulator state sampled by the synthetic drone camera.

    This object must never be passed to the controller. Only its rendered frames,
    content identifier, and integrity hash cross the observation boundary.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    episode_id: str
    study_partition: Literal["development", "test"] = "development"
    route_id: str
    asset_id: str
    observed_at: float = Field(ge=0.0)
    environment_tick_index: int = Field(ge=0)
    sensor_seed: int
    water_depth_m: float = Field(ge=0.0)
    route_closure_depth_m: float = Field(gt=0.0)
    debris_blocked: bool
    rain_intensity: float = Field(ge=0.0, le=1.0)
    upstream_inflow: float = Field(ge=0.0, le=1.0)
    weather_severity: float = Field(ge=0.0, le=1.0)
    sensor_noise: float = Field(ge=0.0, le=1.0)
    sensor_quality: float = Field(ge=0.0, le=1.0)
    packet_delivered: bool
    categorical_report_accurate: bool
    sensor_model_version: str = SENSOR_MODEL_VERSION


@dataclass(frozen=True)
class CapturedVisualObservation:
    observation_id: str
    observation_hash: str
    frames_sha256: str
    frames_path: Path
    manifest_path: Path
    controller_usable: bool


def validate_test_authorization(path: Path | None) -> dict[str, object]:
    """Validate the explicit freeze manifest required before any test capture."""

    if path is None or not Path(path).is_file():
        raise ValueError("test observations require a frozen authorization manifest")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {
        "manifest_version",
        "protocol_sha256",
        "code_commit",
        "dataset_manifest_sha256",
        "predictor_checkpoint_sha256",
        "calibration_version",
        "test_authorized",
    }
    if required - payload.keys():
        raise ValueError("test authorization manifest is incomplete")
    if payload["test_authorized"] is not True:
        raise ValueError("test authorization manifest has not been activated")
    if any(str(payload[key]).startswith("REPLACE_") for key in required - {"test_authorized"}):
        raise ValueError("test authorization manifest still contains template values")
    return payload


def _frame_digest(frames: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(frames).tobytes()).hexdigest()


def render_simulator_sensor_clip(
    snapshot: SimulatorSensorSnapshot,
    *,
    num_frames: int = 64,
    size: int = 96,
    frame_step: int = 1,
) -> np.ndarray:
    """Render a deterministic RGB observation from the sampled simulator state."""

    if num_frames < 2 or size < 32 or frame_step < 1:
        raise ValueError("sensor rendering requires at least 2 frames and a 32-pixel canvas")
    seed_material = sha256_value(
        {
            "sensor_seed": snapshot.sensor_seed,
            "route_id": snapshot.route_id,
            "asset_id": snapshot.asset_id,
            "observed_at": snapshot.observed_at,
            "tick": snapshot.environment_tick_index,
            "sensor_model_version": snapshot.sensor_model_version,
        }
    )
    rng = np.random.default_rng(int(seed_material[:16], 16))
    frames = np.empty((num_frames, size, size, 3), dtype=np.uint8)
    depth_ratio = np.clip(
        snapshot.water_depth_m / snapshot.route_closure_depth_m,
        0.0,
        1.5,
    )
    water_height = int((depth_ratio / 1.5) * size * 0.65)
    turbulence = np.clip(
        0.45 * snapshot.rain_intensity + 0.55 * snapshot.upstream_inflow,
        0.0,
        1.0,
    )
    visibility = np.clip(
        snapshot.sensor_quality * (1.0 - 0.65 * snapshot.weather_severity),
        0.08,
        1.0,
    )
    debris_level = 0.82 if snapshot.debris_blocked else 0.12
    debris_count = int(round(4 + 32 * debris_level))
    debris_xy = rng.integers(3, size - 3, size=(debris_count, 2))
    debris_phase = rng.uniform(0.0, 2.0 * np.pi, size=debris_count)

    for frame_index in range(num_frames):
        source_frame_index = frame_index * frame_step
        frame_rng = np.random.default_rng(
            int(
                sha256_value(
                    {
                        "sensor_clip": seed_material,
                        "source_frame_index": source_frame_index,
                    }
                )[:16],
                16,
            )
        )
        image = np.zeros((size, size, 3), dtype=np.float32)
        sky = 72.0 + 122.0 * visibility
        image[:] = (0.72 * sky, 0.82 * sky, sky)
        water_top = max(
            2,
            size - water_height - int(2 * np.sin(source_frame_index / 5.0)),
        )
        image[water_top:] = (34.0, 90.0, 132.0)

        columns = np.arange(size, dtype=np.float32)
        wave = 4.0 * turbulence * np.sin(
            columns / 5.0 + source_frame_index * 0.32
        )
        for column, delta in enumerate(wave.astype(int)):
            y = int(np.clip(water_top + delta, 0, size - 1))
            image[y : min(size, y + 2), column] = (168.0, 204.0, 219.0)

        drift = source_frame_index * (0.20 + 1.35 * turbulence)
        for index, (base_x, base_y) in enumerate(debris_xy):
            x_pos = int(
                (
                    base_x
                    + drift
                    + 2.0 * np.sin(debris_phase[index] + source_frame_index / 7.0)
                )
                % size
            )
            y_pos = int(max(water_top + 2, min(size - 3, base_y)))
            image[
                y_pos - 2 : y_pos + 2,
                max(0, x_pos - 2) : min(size, x_pos + 2),
            ] = (91.0, 61.0, 34.0)

        rain_count = int(round(28 * snapshot.rain_intensity))
        rain_x = frame_rng.integers(0, size, size=rain_count)
        rain_y = (
            frame_rng.integers(0, size, size=rain_count) + 3 * source_frame_index
        ) % size
        image[rain_y, rain_x] = (205.0, 220.0, 236.0)
        pixel_noise = frame_rng.normal(
            0.0,
            2.0 + 12.0 * snapshot.sensor_noise + 8.0 * (1.0 - snapshot.sensor_quality),
            image.shape,
        )
        frames[frame_index] = np.clip(image + pixel_noise, 0.0, 255.0).astype(np.uint8)
    return frames


class SimulatorVisualObservationStore:
    """Persist synchronized simulator imagery and an audit manifest atomically."""

    def __init__(
        self,
        root: Path,
        *,
        num_frames: int = 64,
        size: int = 96,
        frame_step: int = 1,
    ):
        self.root = Path(root)
        self.num_frames = num_frames
        self.size = size
        if frame_step < 1:
            raise ValueError("frame_step must be positive")
        self.frame_step = frame_step
        self.root.mkdir(parents=True, exist_ok=True)

    def capture(self, snapshot: SimulatorSensorSnapshot) -> CapturedVisualObservation:
        frames = render_simulator_sensor_clip(
            snapshot,
            num_frames=self.num_frames,
            size=self.size,
            frame_step=self.frame_step,
        )
        snapshot_payload = snapshot.model_dump(mode="json")
        snapshot_sha256 = sha256_value(snapshot_payload)
        frames_sha256 = _frame_digest(frames)
        observation_hash = sha256_value(
            {
                "snapshot_sha256": snapshot_sha256,
                "frames_sha256": frames_sha256,
                "shape": list(frames.shape),
                "dtype": str(frames.dtype),
            }
        )
        observation_id = f"simobs-{observation_hash[:24]}"
        frames_path = self.root / f"{observation_id}.npz"
        manifest_path = self.root / f"{observation_id}.json"
        if not frames_path.exists():
            with tempfile.NamedTemporaryFile(dir=self.root, suffix=".npz", delete=False) as handle:
                temporary_frames = Path(handle.name)
                np.savez_compressed(
                    handle,
                    frames=frames,
                    observation_id=np.asarray(observation_id),
                    observation_hash=np.asarray(observation_hash),
                )
                handle.flush()
                os.fsync(handle.fileno())
            temporary_frames.replace(frames_path)
        manifest = {
            "manifest_version": "simulator-visual-observation-v1",
            "observation_id": observation_id,
            "observation_hash": observation_hash,
            "frames_file": frames_path.name,
            "frames_sha256": frames_sha256,
            "frame_shape": list(frames.shape),
            "frame_dtype": str(frames.dtype),
            "frame_step": self.frame_step,
            "controller_usable": snapshot.packet_delivered,
            "study_partition": snapshot.study_partition,
            "sampled_at": snapshot.observed_at,
            "route_id": snapshot.route_id,
            "asset_id": snapshot.asset_id,
            "episode_id": snapshot.episode_id,
            "sensor_model_version": snapshot.sensor_model_version,
            "audit_snapshot_sha256": snapshot_sha256,
            "audit_snapshot": snapshot_payload,
        }
        encoded = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False)
        with tempfile.NamedTemporaryFile(
            dir=self.root,
            suffix=".json",
            mode="w",
            encoding="utf-8",
            delete=False,
        ) as handle:
            temporary_manifest = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_manifest.replace(manifest_path)
        return CapturedVisualObservation(
            observation_id=observation_id,
            observation_hash=observation_hash,
            frames_sha256=frames_sha256,
            frames_path=frames_path,
            manifest_path=manifest_path,
            controller_usable=snapshot.packet_delivered,
        )
