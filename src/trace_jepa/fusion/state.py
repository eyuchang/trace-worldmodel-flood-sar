from __future__ import annotations

from pydantic import BaseModel, ConfigDict
import numpy as np

from trace_jepa.util import sha256_value


class FloodMissionState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    video_embedding: tuple[float, ...]
    drone_battery: float
    boat_capacity: int
    north_route_verified: bool
    north_route_open: bool | None
    south_route_open: bool
    stranded_people: int
    weather_severity: float

    @property
    def state_hash(self) -> str:
        return sha256_value(self.model_dump(mode="json"))

    def as_vector(self) -> np.ndarray:
        structured = np.array(
            [
                self.drone_battery,
                self.boat_capacity / 10.0,
                float(self.north_route_verified),
                -1.0 if self.north_route_open is None else float(self.north_route_open),
                float(self.south_route_open),
                self.stranded_people / 10.0,
                self.weather_severity,
            ],
            dtype=np.float32,
        )
        return np.concatenate([np.asarray(self.video_embedding, dtype=np.float32), structured])


def fuse_state(video_embedding: np.ndarray, observation: dict) -> FloodMissionState:
    return FloodMissionState(
        video_embedding=tuple(float(item) for item in video_embedding.reshape(-1)),
        drone_battery=float(observation["drone_battery"]),
        boat_capacity=int(observation["boat_capacity"]),
        north_route_verified=bool(observation["north_route_verified"]),
        north_route_open=observation.get("north_route_open"),
        south_route_open=bool(observation["south_route_open"]),
        stranded_people=int(observation["stranded_people"]),
        weather_severity=float(observation["weather_severity"]),
    )
