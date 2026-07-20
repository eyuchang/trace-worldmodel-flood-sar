from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from trace_jepa.util import sha256_value
from trace_jepa.worldmodels.contracts import RouteWorldModelRequest


@dataclass(frozen=True)
class ControlledVisualCue:
    """Observable scene factors intentionally omitted from structured telemetry."""

    surface_debris: float
    flow_turbulence: float
    visibility: float
    cue_seed: int


@dataclass(frozen=True)
class RenderedRouteObservation:
    frames: np.ndarray
    observation_hash: str
    cue: ControlledVisualCue


def render_controlled_route_clip(
    request: RouteWorldModelRequest,
    cue: ControlledVisualCue,
    *,
    num_frames: int = 64,
    size: int = 96,
) -> RenderedRouteObservation:
    """Render a deterministic controlled clip for integration experiments.

    This is a benchmark instrument, not field imagery. Labels may depend on the
    visible debris/turbulence cue; the structured baseline cannot read the cue's
    numeric value, while the visual model receives only pixels.
    """

    if num_frames < 2 or size < 32:
        raise ValueError("rendering requires at least 2 frames and a 32-pixel canvas")
    rng = np.random.default_rng(cue.cue_seed)
    frames = np.empty((num_frames, size, size, 3), dtype=np.uint8)
    water_base = int(
        np.clip(
            request.projected_depth_m / request.route_closure_depth_m,
            0.0,
            1.5,
        )
        / 1.5
        * (size * 0.62)
    )
    debris_count = int(round(4 + 28 * np.clip(cue.surface_debris, 0.0, 1.0)))
    debris_xy = rng.integers(3, size - 3, size=(debris_count, 2))
    phase = rng.uniform(0.0, 2.0 * np.pi, size=debris_count)

    for frame_index in range(num_frames):
        image = np.zeros((size, size, 3), dtype=np.float32)
        sky = 120.0 + 65.0 * np.clip(cue.visibility, 0.0, 1.0)
        image[:] = (sky * 0.72, sky * 0.82, sky)
        water_top = max(2, size - water_base - int(2 * np.sin(frame_index / 5.0)))
        image[water_top:] = (36.0, 92.0, 132.0)

        x = np.arange(size, dtype=np.float32)
        wave = 3.0 * np.clip(cue.flow_turbulence, 0.0, 1.0) * np.sin(x / 5.0 + frame_index * 0.35)
        for column, delta in enumerate(wave.astype(int)):
            y = int(np.clip(water_top + delta, 0, size - 1))
            image[y : min(size, y + 2), column] = (170.0, 205.0, 218.0)

        drift = frame_index * (0.25 + 1.25 * cue.flow_turbulence)
        for index, (base_x, base_y) in enumerate(debris_xy):
            x_pos = int((base_x + drift + 2.0 * np.sin(phase[index] + frame_index / 7.0)) % size)
            y_pos = int(max(water_top + 2, min(size - 3, base_y)))
            image[y_pos - 2 : y_pos + 2, max(0, x_pos - 2) : min(size, x_pos + 2)] = (
                92.0,
                62.0,
                35.0,
            )

        rain_count = int(round(24 * request.weather_forecast))
        rain_x = rng.integers(0, size, size=rain_count)
        rain_y = (rng.integers(0, size, size=rain_count) + frame_index * 3) % size
        image[rain_y, rain_x] = (205.0, 220.0, 235.0)
        noise = rng.normal(0.0, 8.0 * request.sensor_noise, image.shape)
        frames[frame_index] = np.clip(image + noise, 0.0, 255.0).astype(np.uint8)

    observation_hash = sha256_value(
        {
            "request": request.model_dump(mode="json"),
            "cue": cue.__dict__,
            "frames_sha256": hashlib.sha256(frames.tobytes()).hexdigest(),
        }
    )
    return RenderedRouteObservation(
        frames=frames,
        observation_hash=observation_hash,
        cue=cue,
    )
