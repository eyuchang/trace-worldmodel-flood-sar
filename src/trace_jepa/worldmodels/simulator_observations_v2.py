from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from trace_jepa.util import sha256_value


SENSOR_MODEL_VERSION_V2 = "flood-benchmark-camera-v2"
CONTROLLER_OBSERVATION_SCHEMA_V2 = "flood-benchmark-controller-observation-v2"
AUDIT_OBSERVATION_SCHEMA_V2 = "flood-benchmark-audit-observation-v2"

CameraNameV2 = Literal["drone_oblique", "riverbank_fixed", "nadir_wide"]
WeatherBandV2 = Literal["mild", "adverse", "severe"]
RouteReportV2 = Literal["open", "blocked", "unknown"]


class FrozenModelV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CameraProfileV2(FrozenModelV2):
    """Declared camera geometry and measurement characteristics.

    Profiles are benchmark instruments rather than learned parameters. None of
    the fields depend on a candidate action.
    """

    name: CameraNameV2
    image_size: int = Field(ge=32)
    num_frames: int = Field(ge=2)
    frame_step_s: float = Field(gt=0.0)
    vertical_scale: float = Field(gt=0.0)
    horizon_shift: float = Field(ge=-0.4, le=0.4)
    occlusion_fraction: float = Field(ge=0.0, le=0.5)
    radiometric_shift: float = Field(ge=-0.4, le=0.4)
    noise_multiplier: float = Field(gt=0.0)


def camera_profile_v2(name: CameraNameV2) -> CameraProfileV2:
    profiles = {
        "drone_oblique": CameraProfileV2(
            name="drone_oblique",
            image_size=96,
            num_frames=8,
            frame_step_s=0.5,
            vertical_scale=1.0,
            horizon_shift=0.0,
            occlusion_fraction=0.02,
            radiometric_shift=0.0,
            noise_multiplier=1.0,
        ),
        "riverbank_fixed": CameraProfileV2(
            name="riverbank_fixed",
            image_size=96,
            num_frames=8,
            frame_step_s=0.5,
            vertical_scale=1.18,
            horizon_shift=0.08,
            occlusion_fraction=0.12,
            radiometric_shift=-0.06,
            noise_multiplier=1.15,
        ),
        "nadir_wide": CameraProfileV2(
            name="nadir_wide",
            image_size=96,
            num_frames=8,
            frame_step_s=0.5,
            vertical_scale=0.82,
            horizon_shift=-0.06,
            occlusion_fraction=0.0,
            radiometric_shift=0.08,
            noise_multiplier=0.9,
        ),
    }
    return profiles[name]


class AuditExogenousStateV2(FrozenModelV2):
    """Exact simulator truth, forbidden from controller/model inputs.

    The schema intentionally has no action field. It represents one sample from
    the persistent exogenous world trajectory shared by every counterfactual arm.
    """

    truth_schema_version: str = "flood-benchmark-exogenous-truth-v2"
    episode_id: str
    route_id: str
    state_index: int = Field(ge=0)
    sampled_at_s: float = Field(ge=0.0)
    geography_profile: str
    weather_profile: str
    ood_profile: str
    route_length_m: float = Field(gt=0.0)
    water_depth_m: float = Field(ge=0.0)
    route_closure_depth_m: float = Field(gt=0.0)
    rain_intensity: float = Field(ge=0.0, le=1.5)
    upstream_inflow: float = Field(ge=0.0, le=1.5)
    debris_load: float = Field(ge=0.0, le=1.0)
    flow_turbulence: float = Field(ge=0.0, le=1.0)
    atmospheric_visibility: float = Field(ge=0.0, le=1.0)
    sensor_noise_scale: float = Field(ge=0.0, le=1.0)
    packet_delivery_probability: float = Field(ge=0.0, le=1.0)
    episode_sensor_seed: int = Field(ge=0)

    @property
    def debris_blocked(self) -> bool:
        return self.debris_load >= 0.68

    @property
    def state_sha256(self) -> str:
        return sha256_value(self.model_dump(mode="json"))


class ControllerObservationRecordV2(FrozenModelV2):
    """Controller-visible metadata; exact simulator truth is deliberately absent."""

    observation_schema_version: str = CONTROLLER_OBSERVATION_SCHEMA_V2
    observation_id: str
    observation_hash: str
    episode_id: str
    route_id: str
    sampled_at_s: float = Field(ge=0.0)
    camera_name: CameraNameV2
    sensor_model_version: str = SENSOR_MODEL_VERSION_V2
    frames_sha256: str
    frame_shape: tuple[int, int, int, int]
    reported_route_status: RouteReportV2
    report_confidence: float = Field(ge=0.0, le=1.0)
    reported_weather_band: WeatherBandV2
    packet_delivered: bool

    @model_validator(mode="after")
    def _validate_identifiers(self) -> "ControllerObservationRecordV2":
        if not self.observation_id.startswith("bmv2obs-"):
            raise ValueError("benchmark-v2 observations require the bmv2obs namespace")
        for digest in (self.observation_hash, self.frames_sha256):
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ValueError("observation digests must be lowercase SHA-256 values")
        return self


@dataclass(frozen=True)
class ControllerObservationPackageV2:
    """Immutable pixels plus controller-visible metadata.

    Audit truth is held in a separate envelope and cannot be reached through this
    object. The pixel array is copied and marked read-only at construction.
    """

    record: ControllerObservationRecordV2
    frames: np.ndarray

    def __post_init__(self) -> None:
        frames = np.asarray(self.frames)
        if frames.dtype != np.uint8 or frames.shape != self.record.frame_shape:
            raise ValueError("controller frames do not match the declared schema")
        frames = np.ascontiguousarray(frames).copy()
        if _frames_sha256(frames) != self.record.frames_sha256:
            raise ValueError("controller frame digest mismatch")
        frames.setflags(write=False)
        object.__setattr__(self, "frames", frames)

    @property
    def package_sha256(self) -> str:
        return sha256_value(
            {
                "record": self.record.model_dump(mode="json"),
                "frames_sha256": self.record.frames_sha256,
            }
        )


class AuditObservationEnvelopeV2(FrozenModelV2):
    """Audit-only link between one public observation and its exact truth."""

    audit_schema_version: str = AUDIT_OBSERVATION_SCHEMA_V2
    controller_observation_id: str
    controller_observation_hash: str
    controller_package_sha256: str
    truth_state_sha256: str
    truth_state: AuditExogenousStateV2
    camera_profile_sha256: str
    report_randomness_sha256: str

    @model_validator(mode="after")
    def _validate_truth_digest(self) -> "AuditObservationEnvelopeV2":
        if self.truth_state.state_sha256 != self.truth_state_sha256:
            raise ValueError("audit truth digest mismatch")
        return self


def _frames_sha256(frames: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(frames).tobytes()).hexdigest()


def _seed_from(value: object) -> int:
    return int(sha256_value(value)[:16], 16)


def render_controller_frames_v2(
    state: AuditExogenousStateV2,
    camera: CameraProfileV2,
) -> np.ndarray:
    """Render an action-independent, temporally persistent sensor clip.

    Debris and rain particles are initialized once from the episode/camera seed
    and advanced using absolute time. Pixel noise is keyed by absolute frame time.
    Candidate actions are intentionally absent from both the API and all seed
    material, so equal episode/time/camera inputs are counterfactually invariant.
    """

    size = camera.image_size
    persistent_seed = _seed_from(
        {
            "episode_sensor_seed": state.episode_sensor_seed,
            "route_id": state.route_id,
            "camera_name": camera.name,
            "sensor_model_version": SENSOR_MODEL_VERSION_V2,
        }
    )
    persistent_rng = np.random.default_rng(persistent_seed)
    debris_pool = persistent_rng.integers(3, size - 3, size=(48, 2))
    debris_phase = persistent_rng.uniform(0.0, 2.0 * np.pi, size=48)
    rain_pool = persistent_rng.integers(0, size, size=(64, 2))
    frames = np.empty((camera.num_frames, size, size, 3), dtype=np.uint8)

    depth_ratio = float(np.clip(state.water_depth_m / state.route_closure_depth_m, 0.0, 1.6))
    water_height = int(
        np.clip(depth_ratio / 1.6 * size * 0.68 * camera.vertical_scale, 1, size - 2)
    )
    debris_count = int(round(3 + 39 * state.debris_load))
    rain_count = int(round(4 + 38 * np.clip(state.rain_intensity, 0.0, 1.0)))
    visible_columns = int(round(size * (1.0 - camera.occlusion_fraction)))

    for frame_index in range(camera.num_frames):
        absolute_time_s = state.sampled_at_s + frame_index * camera.frame_step_s
        frame_seed = _seed_from(
            {
                "persistent_seed": persistent_seed,
                "absolute_time_us": int(round(absolute_time_s * 1_000_000.0)),
            }
        )
        frame_rng = np.random.default_rng(frame_seed)
        image = np.zeros((size, size, 3), dtype=np.float32)
        sky = 74.0 + 120.0 * state.atmospheric_visibility
        image[:] = (0.70 * sky, 0.82 * sky, sky)
        water_top = int(
            np.clip(
                size
                - water_height
                + camera.horizon_shift * size
                - 2.0 * np.sin(absolute_time_s / 5.0),
                2,
                size - 2,
            )
        )
        image[water_top:, :visible_columns] = (34.0, 91.0, 133.0)

        columns = np.arange(visible_columns, dtype=np.float32)
        wave = 4.0 * state.flow_turbulence * np.sin(columns / 5.0 + absolute_time_s * 0.32)
        for column, delta in enumerate(wave.astype(int)):
            y = int(np.clip(water_top + delta, 0, size - 1))
            image[y : min(size, y + 2), column] = (168.0, 204.0, 219.0)

        drift = absolute_time_s * (0.03 + 0.17 * state.flow_turbulence)
        for index, (base_x, base_y) in enumerate(debris_pool[:debris_count]):
            x_position = int(
                (base_x + drift + 2.0 * np.sin(debris_phase[index] + absolute_time_s / 7.0))
                % max(1, visible_columns)
            )
            y_position = int(max(water_top + 2, min(size - 3, base_y)))
            image[
                y_position - 2 : y_position + 2,
                max(0, x_position - 2) : min(visible_columns, x_position + 2),
            ] = (91.0, 61.0, 34.0)

        if rain_count:
            rain = rain_pool[:rain_count]
            rain_x = rain[:, 0] % max(1, visible_columns)
            rain_y = (rain[:, 1] + np.floor(7.0 * absolute_time_s).astype(int)) % size
            image[rain_y, rain_x] = (205.0, 221.0, 236.0)

        noise_sigma = (
            1.5
            + 9.0 * state.sensor_noise_scale * camera.noise_multiplier
            + 5.0 * (1.0 - state.atmospheric_visibility)
        )
        image += frame_rng.normal(0.0, noise_sigma, image.shape)
        image *= 1.0 + camera.radiometric_shift
        if visible_columns < size:
            image[:, visible_columns:] = 24.0
        frames[frame_index] = np.clip(image, 0.0, 255.0).astype(np.uint8)
    return frames


def capture_controller_observation_v2(
    state: AuditExogenousStateV2,
    camera: CameraProfileV2,
) -> tuple[ControllerObservationPackageV2, AuditObservationEnvelopeV2]:
    """Create separate controller and audit packages for one trajectory state."""

    frames = render_controller_frames_v2(state, camera)
    frames_sha256 = _frames_sha256(frames)
    report_seed_material = {
        "episode_sensor_seed": state.episode_sensor_seed,
        "state_index": state.state_index,
        "sampled_at_s": state.sampled_at_s,
        "camera_name": camera.name,
        "report_schema": CONTROLLER_OBSERVATION_SCHEMA_V2,
    }
    report_randomness_sha256 = sha256_value(report_seed_material)
    report_rng = np.random.default_rng(_seed_from(report_seed_material))
    actual_open = state.water_depth_m < state.route_closure_depth_m and not state.debris_blocked
    report_accuracy = float(
        np.clip(
            0.98
            - 0.34 * state.sensor_noise_scale * camera.noise_multiplier
            - 0.22 * camera.occlusion_fraction,
            0.51,
            0.995,
        )
    )
    packet_delivered = bool(report_rng.random() <= state.packet_delivery_probability)
    report_correct = bool(report_rng.random() <= report_accuracy)
    reported_open = actual_open if report_correct else not actual_open
    weather_severity = float(
        np.clip(
            0.55 * min(1.0, state.rain_intensity) + 0.45 * (1.0 - state.atmospheric_visibility),
            0.0,
            1.0,
        )
    )
    weather_band: WeatherBandV2
    if weather_severity < 0.34:
        weather_band = "mild"
    elif weather_severity < 0.67:
        weather_band = "adverse"
    else:
        weather_band = "severe"
    public_payload = {
        "observation_schema_version": CONTROLLER_OBSERVATION_SCHEMA_V2,
        "episode_id": state.episode_id,
        "route_id": state.route_id,
        "sampled_at_s": state.sampled_at_s,
        "camera_name": camera.name,
        "sensor_model_version": SENSOR_MODEL_VERSION_V2,
        "frames_sha256": frames_sha256,
        "frame_shape": tuple(int(value) for value in frames.shape),
        "reported_route_status": ("open" if reported_open else "blocked")
        if packet_delivered
        else "unknown",
        "report_confidence": report_accuracy if packet_delivered else 0.0,
        "reported_weather_band": weather_band,
        "packet_delivered": packet_delivered,
    }
    observation_hash = sha256_value(public_payload)
    observation_id = f"bmv2obs-{observation_hash[:24]}"
    record = ControllerObservationRecordV2(
        observation_id=observation_id,
        observation_hash=observation_hash,
        **public_payload,
    )
    package = ControllerObservationPackageV2(record=record, frames=frames)
    envelope = AuditObservationEnvelopeV2(
        controller_observation_id=observation_id,
        controller_observation_hash=observation_hash,
        controller_package_sha256=package.package_sha256,
        truth_state_sha256=state.state_sha256,
        truth_state=state,
        camera_profile_sha256=sha256_value(camera.model_dump(mode="json")),
        report_randomness_sha256=report_randomness_sha256,
    )
    return package, envelope
