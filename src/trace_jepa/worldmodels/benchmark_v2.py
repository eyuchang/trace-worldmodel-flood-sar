from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from pydantic import Field, model_validator

from trace_jepa.util import sha256_value
from trace_jepa.worldmodels.simulator_observations_v2 import (
    AuditExogenousStateV2,
    AuditObservationEnvelopeV2,
    CameraNameV2,
    ControllerObservationPackageV2,
    FrozenModelV2,
    camera_profile_v2,
    capture_controller_observation_v2,
)


BENCHMARK_V2_GENERATOR_VERSION = "coherent-flood-sar-benchmark-v2"
BENCHMARK_V2_ID_NAMESPACE = "flood-bmv2-dev"

GeographyNameV2 = Literal["urban_plain", "river_valley", "coastal_delta"]
WeatherNameV2 = Literal["stratiform", "convective", "upstream_surge"]
OODNameV2 = Literal["in_domain", "sensor_shift", "hydrology_shift", "compound"]
ActionNameV2 = Literal["hold_position", "dispatch_rescue_boat", "dispatch_helicopter"]

ACTION_NAMES_V2: tuple[ActionNameV2, ...] = (
    "hold_position",
    "dispatch_rescue_boat",
    "dispatch_helicopter",
)


class GeographyProfileV2(FrozenModelV2):
    name: GeographyNameV2
    route_length_m: float = Field(gt=0.0)
    closure_depth_m: float = Field(gt=0.0)
    hydrologic_susceptibility: float = Field(gt=0.0)
    drainage_rate_m_s: float = Field(ge=0.0)
    base_rise_rate_m_s: float = Field(gt=0.0)
    debris_susceptibility: float = Field(gt=0.0)


class WeatherProfileV2(FrozenModelV2):
    name: WeatherNameV2
    rain_mean: float = Field(ge=0.0, le=1.0)
    rain_persistence: float = Field(ge=0.0, lt=1.0)
    rain_innovation_scale: float = Field(gt=0.0)
    inflow_mean: float = Field(ge=0.0, le=1.0)
    inflow_persistence: float = Field(ge=0.0, lt=1.0)
    inflow_innovation_scale: float = Field(gt=0.0)


class OODProfileV2(FrozenModelV2):
    name: OODNameV2
    hydrology_multiplier: float = Field(gt=0.0)
    debris_multiplier: float = Field(gt=0.0)
    sensor_noise_multiplier: float = Field(gt=0.0)
    visibility_offset: float = Field(ge=-0.5, le=0.5)


def geography_profile_v2(name: GeographyNameV2) -> GeographyProfileV2:
    profiles = {
        "urban_plain": GeographyProfileV2(
            name="urban_plain",
            route_length_m=900.0,
            closure_depth_m=0.74,
            hydrologic_susceptibility=0.86,
            drainage_rate_m_s=0.000030,
            base_rise_rate_m_s=0.000055,
            debris_susceptibility=0.78,
        ),
        "river_valley": GeographyProfileV2(
            name="river_valley",
            route_length_m=1_450.0,
            closure_depth_m=0.66,
            hydrologic_susceptibility=1.24,
            drainage_rate_m_s=0.000010,
            base_rise_rate_m_s=0.000082,
            debris_susceptibility=1.08,
        ),
        "coastal_delta": GeographyProfileV2(
            name="coastal_delta",
            route_length_m=1_120.0,
            closure_depth_m=0.84,
            hydrologic_susceptibility=1.05,
            drainage_rate_m_s=0.000018,
            base_rise_rate_m_s=0.000067,
            debris_susceptibility=1.26,
        ),
    }
    return profiles[name]


def weather_profile_v2(name: WeatherNameV2) -> WeatherProfileV2:
    profiles = {
        "stratiform": WeatherProfileV2(
            name="stratiform",
            rain_mean=0.46,
            rain_persistence=0.93,
            rain_innovation_scale=0.07,
            inflow_mean=0.42,
            inflow_persistence=0.92,
            inflow_innovation_scale=0.06,
        ),
        "convective": WeatherProfileV2(
            name="convective",
            rain_mean=0.52,
            rain_persistence=0.66,
            rain_innovation_scale=0.24,
            inflow_mean=0.45,
            inflow_persistence=0.78,
            inflow_innovation_scale=0.13,
        ),
        "upstream_surge": WeatherProfileV2(
            name="upstream_surge",
            rain_mean=0.28,
            rain_persistence=0.86,
            rain_innovation_scale=0.10,
            inflow_mean=0.78,
            inflow_persistence=0.91,
            inflow_innovation_scale=0.14,
        ),
    }
    return profiles[name]


def ood_profile_v2(name: OODNameV2) -> OODProfileV2:
    profiles = {
        "in_domain": OODProfileV2(
            name="in_domain",
            hydrology_multiplier=1.0,
            debris_multiplier=1.0,
            sensor_noise_multiplier=1.0,
            visibility_offset=0.0,
        ),
        "sensor_shift": OODProfileV2(
            name="sensor_shift",
            hydrology_multiplier=1.0,
            debris_multiplier=1.0,
            sensor_noise_multiplier=1.75,
            visibility_offset=-0.12,
        ),
        "hydrology_shift": OODProfileV2(
            name="hydrology_shift",
            hydrology_multiplier=1.55,
            debris_multiplier=1.25,
            sensor_noise_multiplier=1.0,
            visibility_offset=0.0,
        ),
        "compound": OODProfileV2(
            name="compound",
            hydrology_multiplier=1.45,
            debris_multiplier=1.35,
            sensor_noise_multiplier=1.65,
            visibility_offset=-0.15,
        ),
    }
    return profiles[name]


class BenchmarkV2Spec(FrozenModelV2):
    """Prospective generator specification; it cannot generate test episodes."""

    spec_schema_version: str = "flood-benchmark-v2-spec-v1"
    campaign_seed: int = Field(ge=0)
    split_seed: int = Field(ge=0)
    episode_count: int = Field(ge=8)
    observation_times_s: tuple[float, ...] = (0.0, 300.0, 600.0, 900.0)
    geography_profiles: tuple[GeographyNameV2, ...] = (
        "urban_plain",
        "river_valley",
        "coastal_delta",
    )
    camera_profiles: tuple[CameraNameV2, ...] = (
        "drone_oblique",
        "riverbank_fixed",
        "nadir_wide",
    )
    weather_profiles: tuple[WeatherNameV2, ...] = (
        "stratiform",
        "convective",
        "upstream_surge",
    )
    ood_profiles: tuple[OODNameV2, ...] = (
        "in_domain",
        "sensor_shift",
        "hydrology_shift",
        "compound",
    )

    @model_validator(mode="after")
    def _validate_design(self) -> "BenchmarkV2Spec":
        if len(self.observation_times_s) < 3:
            raise ValueError("benchmark-v2 requires at least three trajectory observations")
        if self.observation_times_s[0] != 0.0 or any(
            right <= left
            for left, right in zip(
                self.observation_times_s,
                self.observation_times_s[1:],
            )
        ):
            raise ValueError("observation times must start at zero and increase strictly")
        for profiles in (
            self.geography_profiles,
            self.camera_profiles,
            self.weather_profiles,
            self.ood_profiles,
        ):
            if not profiles or len(set(profiles)) != len(profiles):
                raise ValueError("profile lists must be nonempty and unique")
        return self

    @property
    def spec_sha256(self) -> str:
        return sha256_value(self.model_dump(mode="json"))


class ExogenousTrajectoryV2(FrozenModelV2):
    generator_version: str = BENCHMARK_V2_GENERATOR_VERSION
    episode_id: str
    data_seed: int = Field(ge=0)
    geography_profile: GeographyNameV2
    weather_profile: WeatherNameV2
    ood_profile: OODNameV2
    random_draws_sha256: str
    states: tuple[AuditExogenousStateV2, ...]
    trajectory_sha256: str

    def hash_payload(self) -> dict[str, object]:
        return {
            "generator_version": self.generator_version,
            "episode_id": self.episode_id,
            "data_seed": self.data_seed,
            "geography_profile": self.geography_profile,
            "weather_profile": self.weather_profile,
            "ood_profile": self.ood_profile,
            "random_draws_sha256": self.random_draws_sha256,
            "states": [state.model_dump(mode="json") for state in self.states],
        }

    @model_validator(mode="after")
    def _validate_trajectory(self) -> "ExogenousTrajectoryV2":
        if len(self.states) < 3:
            raise ValueError("a coherent trajectory requires at least three states")
        if any(state.episode_id != self.episode_id for state in self.states):
            raise ValueError("trajectory states cross episode boundaries")
        if any(
            right.sampled_at_s <= left.sampled_at_s
            for left, right in zip(self.states, self.states[1:])
        ):
            raise ValueError("trajectory time must increase strictly")
        if self.trajectory_sha256 != sha256_value(self.hash_payload()):
            raise ValueError("trajectory digest mismatch")
        return self


class OperationalStateV2(FrozenModelV2):
    operation_schema_version: str = "flood-benchmark-operational-state-v2"
    episode_id: str
    sampled_at_s: float = Field(ge=0.0)
    action_name: str
    asset_progress: float = Field(ge=0.0, le=1.0)
    resource_remaining: float = Field(ge=0.0, le=1.0)
    people_reached: int = Field(ge=0)
    action_feasible: bool

    @property
    def state_sha256(self) -> str:
        return sha256_value(self.model_dump(mode="json"))


class CounterfactualTransitionV2(FrozenModelV2):
    transition_schema_version: str = "flood-benchmark-counterfactual-v2"
    episode_id: str
    action_name: ActionNameV2
    horizon_s: float = Field(gt=0.0)
    current_observation_id: str
    current_observation_hash: str
    future_observation_id: str
    future_observation_hash: str
    future_exogenous_state_sha256: str
    initial_operational_state: OperationalStateV2
    final_operational_state: OperationalStateV2
    transition_sha256: str

    def hash_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"transition_sha256"})

    @model_validator(mode="after")
    def _validate_transition(self) -> "CounterfactualTransitionV2":
        if self.transition_sha256 != sha256_value(self.hash_payload()):
            raise ValueError("counterfactual transition digest mismatch")
        return self


@dataclass(frozen=True)
class BenchmarkEpisodeV2:
    episode_id: str
    camera_name: CameraNameV2
    trajectory: ExogenousTrajectoryV2
    controller_observations: tuple[ControllerObservationPackageV2, ...]
    audit_observations: tuple[AuditObservationEnvelopeV2, ...]
    counterfactuals: tuple[CounterfactualTransitionV2, ...]

    def __post_init__(self) -> None:
        if self.episode_id != self.trajectory.episode_id:
            raise ValueError("benchmark episode and trajectory identifiers differ")
        if len(self.controller_observations) != len(self.trajectory.states):
            raise ValueError("one controller observation is required per trajectory state")
        if len(self.audit_observations) != len(self.trajectory.states):
            raise ValueError("one audit envelope is required per trajectory state")

    @property
    def episode_sha256(self) -> str:
        return sha256_value(
            {
                "episode_id": self.episode_id,
                "camera_name": self.camera_name,
                "trajectory_sha256": self.trajectory.trajectory_sha256,
                "controller_packages": [
                    package.package_sha256 for package in self.controller_observations
                ],
                "audit_observations": [
                    envelope.model_dump(mode="json") for envelope in self.audit_observations
                ],
                "counterfactuals": [
                    transition.model_dump(mode="json") for transition in self.counterfactuals
                ],
            }
        )


def _seed_from(value: object) -> int:
    return int(sha256_value(value)[:16], 16)


def benchmark_v2_episode_ids(count: int, campaign_seed: int) -> tuple[str, ...]:
    """Return development-only IDs from a namespace unused by v1 campaigns."""

    if count < 1:
        raise ValueError("episode count must be positive")
    campaign_token = sha256_value(
        {
            "generator": BENCHMARK_V2_GENERATOR_VERSION,
            "campaign_seed": campaign_seed,
            "partition": "development",
        }
    )[:10]
    return tuple(
        f"{BENCHMARK_V2_ID_NAMESPACE}-{campaign_token}-{index + 1:06d}" for index in range(count)
    )


def generate_exogenous_trajectory_v2(
    episode_id: str,
    *,
    data_seed: int,
    geography_name: GeographyNameV2,
    weather_name: WeatherNameV2,
    ood_name: OODNameV2,
    observation_times_s: tuple[float, ...],
) -> ExogenousTrajectoryV2:
    """Generate one persistent trajectory before considering any candidate action."""

    if not episode_id.startswith(f"{BENCHMARK_V2_ID_NAMESPACE}-"):
        raise ValueError("benchmark-v2 rejects IDs from earlier campaign namespaces")
    if (
        len(observation_times_s) < 3
        or observation_times_s[0] != 0.0
        or any(right <= left for left, right in zip(observation_times_s, observation_times_s[1:]))
    ):
        raise ValueError("trajectory times must start at zero and increase strictly")
    geography = geography_profile_v2(geography_name)
    weather = weather_profile_v2(weather_name)
    ood = ood_profile_v2(ood_name)
    episode_seed = _seed_from(
        {
            "generator": BENCHMARK_V2_GENERATOR_VERSION,
            "episode_id": episode_id,
            "data_seed": data_seed,
        }
    )
    rng = np.random.default_rng(episode_seed)
    step_count = len(observation_times_s) - 1
    draws = {
        "initial_depth_fraction": float(rng.uniform(0.28, 0.78)),
        "initial_rain": float(np.clip(rng.normal(weather.rain_mean, 0.08), 0.0, 1.0)),
        "initial_inflow": float(np.clip(rng.normal(weather.inflow_mean, 0.08), 0.0, 1.0)),
        "initial_debris": float(rng.uniform(0.08, 0.48)),
        "rain_innovations": rng.normal(0.0, 1.0, size=step_count).tolist(),
        "inflow_innovations": rng.normal(0.0, 1.0, size=step_count).tolist(),
        "debris_innovations": rng.normal(0.0, 1.0, size=step_count).tolist(),
        "visibility_innovations": rng.normal(0.0, 1.0, size=len(observation_times_s)).tolist(),
        "base_sensor_noise": float(rng.uniform(0.04, 0.15)),
    }
    random_draws_sha256 = sha256_value(draws)
    water_depth = geography.closure_depth_m * draws["initial_depth_fraction"]
    rain = draws["initial_rain"]
    inflow = draws["initial_inflow"]
    debris = draws["initial_debris"]
    states: list[AuditExogenousStateV2] = []
    route_id = f"bmv2-route-{sha256_value(episode_id)[:12]}"

    for state_index, sampled_at_s in enumerate(observation_times_s):
        turbulence = float(np.clip(0.38 * rain + 0.62 * inflow, 0.0, 1.0))
        visibility = float(
            np.clip(
                0.98
                - 0.48 * min(1.0, rain)
                - 0.16 * turbulence
                + 0.025 * draws["visibility_innovations"][state_index]
                + ood.visibility_offset,
                0.05,
                1.0,
            )
        )
        sensor_noise = float(
            np.clip(
                draws["base_sensor_noise"] * ood.sensor_noise_multiplier,
                0.0,
                1.0,
            )
        )
        # This visual-world-model benchmark is explicitly conditional on
        # delivered imagery. Packet-loss policy is evaluated elsewhere; exposing
        # the pixels from a dropped packet would violate the controller boundary.
        packet_probability = 1.0
        states.append(
            AuditExogenousStateV2(
                episode_id=episode_id,
                route_id=route_id,
                state_index=state_index,
                sampled_at_s=sampled_at_s,
                geography_profile=geography.name,
                weather_profile=weather.name,
                ood_profile=ood.name,
                route_length_m=geography.route_length_m,
                water_depth_m=float(max(0.0, water_depth)),
                route_closure_depth_m=geography.closure_depth_m,
                rain_intensity=float(rain),
                upstream_inflow=float(inflow),
                debris_load=float(debris),
                flow_turbulence=turbulence,
                atmospheric_visibility=visibility,
                sensor_noise_scale=sensor_noise,
                packet_delivery_probability=packet_probability,
                episode_sensor_seed=episode_seed,
            )
        )
        if state_index == step_count:
            continue
        delta_s = observation_times_s[state_index + 1] - sampled_at_s
        rain = float(
            np.clip(
                weather.rain_mean
                + weather.rain_persistence * (rain - weather.rain_mean)
                + weather.rain_innovation_scale * draws["rain_innovations"][state_index],
                0.0,
                1.5,
            )
        )
        inflow_target = 0.65 * weather.inflow_mean + 0.35 * min(1.0, rain)
        inflow = float(
            np.clip(
                inflow_target
                + weather.inflow_persistence * (inflow - inflow_target)
                + weather.inflow_innovation_scale * draws["inflow_innovations"][state_index],
                0.0,
                1.5,
            )
        )
        forcing = 0.20 + 0.72 * rain + 0.88 * inflow
        rise_rate = (
            geography.base_rise_rate_m_s
            * geography.hydrologic_susceptibility
            * ood.hydrology_multiplier
            * forcing
        )
        water_depth = max(
            0.0,
            water_depth + delta_s * (rise_rate - geography.drainage_rate_m_s),
        )
        debris_drive = (
            (0.42 * rain + 0.58 * inflow) * geography.debris_susceptibility * ood.debris_multiplier
        )
        debris = float(
            np.clip(
                debris
                + delta_s / 900.0 * (0.19 * debris_drive - 0.045)
                + 0.025 * draws["debris_innovations"][state_index],
                0.0,
                1.0,
            )
        )

    payload = {
        "generator_version": BENCHMARK_V2_GENERATOR_VERSION,
        "episode_id": episode_id,
        "data_seed": data_seed,
        "geography_profile": geography_name,
        "weather_profile": weather_name,
        "ood_profile": ood_name,
        "random_draws_sha256": random_draws_sha256,
        "states": [state.model_dump(mode="json") for state in states],
    }
    return ExogenousTrajectoryV2(
        episode_id=episode_id,
        data_seed=data_seed,
        geography_profile=geography_name,
        weather_profile=weather_name,
        ood_profile=ood_name,
        random_draws_sha256=random_draws_sha256,
        states=tuple(states),
        trajectory_sha256=sha256_value(payload),
    )


def _initial_operational_state(episode_id: str) -> OperationalStateV2:
    resource = 0.72 + 0.26 * (
        _seed_from({"episode_id": episode_id, "field": "initial_resource"}) / float(2**64)
    )
    return OperationalStateV2(
        episode_id=episode_id,
        sampled_at_s=0.0,
        action_name="unassigned",
        asset_progress=0.0,
        resource_remaining=float(np.clip(resource, 0.0, 1.0)),
        people_reached=0,
        action_feasible=True,
    )


def advance_operational_state_v2(
    initial: OperationalStateV2,
    action_name: ActionNameV2,
    future_environment: AuditExogenousStateV2,
) -> OperationalStateV2:
    """Advance only operational state; the exogenous trajectory is read-only."""

    elapsed_s = future_environment.sampled_at_s - initial.sampled_at_s
    if elapsed_s <= 0.0:
        raise ValueError("operational transitions require a positive horizon")
    if action_name == "hold_position":
        progress = 0.0
        resource_cost = 0.000025 * elapsed_s
        feasible = True
        capacity = 0
    elif action_name == "dispatch_rescue_boat":
        effective_speed_m_s = 4.2 * (1.0 - 0.35 * future_environment.flow_turbulence)
        progress = float(
            np.clip(
                effective_speed_m_s * elapsed_s / future_environment.route_length_m,
                0.0,
                1.0,
            )
        )
        resource_cost = 0.00016 * elapsed_s * (1.0 + 0.45 * future_environment.flow_turbulence)
        feasible = (
            future_environment.water_depth_m < 1.15 * future_environment.route_closure_depth_m
            and not future_environment.debris_blocked
        )
        capacity = 12
    else:
        effective_speed_m_s = 24.0
        progress = float(
            np.clip(
                effective_speed_m_s * elapsed_s / future_environment.route_length_m,
                0.0,
                1.0,
            )
        )
        resource_cost = (
            0.00029 * elapsed_s * (1.0 + 0.50 * (1.0 - future_environment.atmospheric_visibility))
        )
        feasible = (
            future_environment.atmospheric_visibility >= 0.34
            and future_environment.rain_intensity <= 1.05
        )
        capacity = 6
    remaining = float(np.clip(initial.resource_remaining - resource_cost, 0.0, 1.0))
    reached = capacity if feasible and progress >= 1.0 and remaining > 0.0 else 0
    return OperationalStateV2(
        episode_id=initial.episode_id,
        sampled_at_s=future_environment.sampled_at_s,
        action_name=action_name,
        asset_progress=progress,
        resource_remaining=remaining,
        people_reached=reached,
        action_feasible=feasible,
    )


def _counterfactual_transition(
    *,
    episode_id: str,
    action_name: ActionNameV2,
    initial: OperationalStateV2,
    future_operational: OperationalStateV2,
    current_observation: ControllerObservationPackageV2,
    future_observation: ControllerObservationPackageV2,
    future_environment: AuditExogenousStateV2,
) -> CounterfactualTransitionV2:
    payload = {
        "transition_schema_version": "flood-benchmark-counterfactual-v2",
        "episode_id": episode_id,
        "action_name": action_name,
        "horizon_s": future_environment.sampled_at_s,
        "current_observation_id": current_observation.record.observation_id,
        "current_observation_hash": current_observation.record.observation_hash,
        "future_observation_id": future_observation.record.observation_id,
        "future_observation_hash": future_observation.record.observation_hash,
        "future_exogenous_state_sha256": future_environment.state_sha256,
        "initial_operational_state": initial.model_dump(mode="json"),
        "final_operational_state": future_operational.model_dump(mode="json"),
    }
    return CounterfactualTransitionV2(
        **payload,
        transition_sha256=sha256_value(payload),
    )


def generate_benchmark_episode_v2(
    episode_id: str,
    *,
    data_seed: int,
    geography_name: GeographyNameV2,
    camera_name: CameraNameV2,
    weather_name: WeatherNameV2,
    ood_name: OODNameV2,
    observation_times_s: tuple[float, ...],
) -> BenchmarkEpisodeV2:
    trajectory = generate_exogenous_trajectory_v2(
        episode_id,
        data_seed=data_seed,
        geography_name=geography_name,
        weather_name=weather_name,
        ood_name=ood_name,
        observation_times_s=observation_times_s,
    )
    camera = camera_profile_v2(camera_name)
    captured = tuple(
        capture_controller_observation_v2(state, camera) for state in trajectory.states
    )
    controller_observations = tuple(item[0] for item in captured)
    audit_observations = tuple(item[1] for item in captured)
    initial_operation = _initial_operational_state(episode_id)
    counterfactuals: list[CounterfactualTransitionV2] = []
    for state_index in range(1, len(trajectory.states)):
        future_environment = trajectory.states[state_index]
        for action_name in ACTION_NAMES_V2:
            future_operation = advance_operational_state_v2(
                initial_operation,
                action_name,
                future_environment,
            )
            counterfactuals.append(
                _counterfactual_transition(
                    episode_id=episode_id,
                    action_name=action_name,
                    initial=initial_operation,
                    future_operational=future_operation,
                    current_observation=controller_observations[0],
                    future_observation=controller_observations[state_index],
                    future_environment=future_environment,
                )
            )
    return BenchmarkEpisodeV2(
        episode_id=episode_id,
        camera_name=camera_name,
        trajectory=trajectory,
        controller_observations=controller_observations,
        audit_observations=audit_observations,
        counterfactuals=tuple(counterfactuals),
    )


def _balanced_assignment(
    values: tuple[str, ...],
    *,
    count: int,
    campaign_seed: int,
    factor_name: str,
) -> tuple[str, ...]:
    repeated = [values[index % len(values)] for index in range(count)]
    rng = np.random.default_rng(
        _seed_from(
            {
                "campaign_seed": campaign_seed,
                "factor_name": factor_name,
                "generator": BENCHMARK_V2_GENERATOR_VERSION,
            }
        )
    )
    permutation = rng.permutation(count)
    assigned = [""] * count
    for source_index, target_index in enumerate(permutation):
        assigned[int(target_index)] = repeated[source_index]
    return tuple(assigned)


def generate_benchmark_episodes_v2(
    spec: BenchmarkV2Spec,
) -> tuple[BenchmarkEpisodeV2, ...]:
    """Generate a balanced, development-only benchmark campaign."""

    episode_ids = benchmark_v2_episode_ids(spec.episode_count, spec.campaign_seed)
    geographies = _balanced_assignment(
        spec.geography_profiles,
        count=spec.episode_count,
        campaign_seed=spec.campaign_seed,
        factor_name="geography",
    )
    cameras = _balanced_assignment(
        spec.camera_profiles,
        count=spec.episode_count,
        campaign_seed=spec.campaign_seed,
        factor_name="camera",
    )
    weather = _balanced_assignment(
        spec.weather_profiles,
        count=spec.episode_count,
        campaign_seed=spec.campaign_seed,
        factor_name="weather",
    )
    ood = _balanced_assignment(
        spec.ood_profiles,
        count=spec.episode_count,
        campaign_seed=spec.campaign_seed,
        factor_name="ood",
    )
    episodes = []
    for index, episode_id in enumerate(episode_ids):
        data_seed = _seed_from(
            {
                "campaign_seed": spec.campaign_seed,
                "episode_id": episode_id,
                "generator": BENCHMARK_V2_GENERATOR_VERSION,
            }
        )
        episodes.append(
            generate_benchmark_episode_v2(
                episode_id,
                data_seed=data_seed,
                geography_name=geographies[index],
                camera_name=cameras[index],
                weather_name=weather[index],
                ood_name=ood[index],
                observation_times_s=spec.observation_times_s,
            )
        )
    return tuple(episodes)
