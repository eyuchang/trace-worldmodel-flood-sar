from __future__ import annotations

from collections import defaultdict

import numpy as np
import pytest
from pydantic import ValidationError

from trace_jepa.worldmodels.benchmark_v2 import (
    ACTION_NAMES_V2,
    BenchmarkV2Spec,
    benchmark_v2_episode_ids,
    camera_profile_v2,
    generate_benchmark_episode_v2,
    generate_benchmark_episodes_v2,
    generate_exogenous_trajectory_v2,
)
from trace_jepa.worldmodels.simulator_observations_v2 import (
    capture_controller_observation_v2,
    render_controller_frames_v2,
)


def _spec() -> BenchmarkV2Spec:
    return BenchmarkV2Spec(
        campaign_seed=20260760,
        split_seed=20260761,
        episode_count=12,
    )


def _episode():
    episode_id = benchmark_v2_episode_ids(1, 99)[0]
    return generate_benchmark_episode_v2(
        episode_id,
        data_seed=1001,
        geography_name="river_valley",
        camera_name="drone_oblique",
        weather_name="convective",
        ood_name="sensor_shift",
        observation_times_s=(0.0, 120.0, 300.0),
    )


def test_live_benchmark_generation_is_exactly_reproducible() -> None:
    first = generate_benchmark_episodes_v2(_spec())
    repeated = generate_benchmark_episodes_v2(_spec())
    assert [episode.episode_sha256 for episode in first] == [
        episode.episode_sha256 for episode in repeated
    ]
    assert all(episode.episode_id.startswith("flood-bmv2-dev-") for episode in first)


def test_counterfactual_actions_share_exogenous_observations() -> None:
    episode = _episode()
    by_horizon = defaultdict(list)
    for transition in episode.counterfactuals:
        by_horizon[transition.horizon_s].append(transition)

    assert set(by_horizon) == {120.0, 300.0}
    for transitions in by_horizon.values():
        assert {item.action_name for item in transitions} == set(ACTION_NAMES_V2)
        assert len({item.current_observation_hash for item in transitions}) == 1
        assert len({item.future_observation_hash for item in transitions}) == 1
        assert len({item.future_exogenous_state_sha256 for item in transitions}) == 1
        assert len({item.final_operational_state.state_sha256 for item in transitions}) == len(
            ACTION_NAMES_V2
        )


def test_equal_time_sensor_bytes_are_action_independent_and_camera_sensitive() -> None:
    episode = _episode()
    state = episode.trajectory.states[1]
    repeated = render_controller_frames_v2(state, camera_profile_v2("drone_oblique"))
    alternate = render_controller_frames_v2(state, camera_profile_v2("riverbank_fixed"))
    assert np.array_equal(repeated, episode.controller_observations[1].frames)
    assert not np.array_equal(repeated, alternate)


def test_controller_observation_excludes_audit_truth() -> None:
    episode = _episode()
    package = episode.controller_observations[0]
    envelope = episode.audit_observations[0]
    controller_payload = package.record.model_dump(mode="json")
    forbidden = {
        "water_depth_m",
        "route_closure_depth_m",
        "rain_intensity",
        "upstream_inflow",
        "debris_load",
        "debris_blocked",
        "flow_turbulence",
        "ood_profile",
        "episode_sensor_seed",
        "truth_state",
        "truth_state_sha256",
    }
    assert forbidden.isdisjoint(controller_payload)
    assert envelope.controller_package_sha256 == package.package_sha256
    assert package.frames.flags.writeable is False


def test_hydrology_shift_changes_dynamics_with_common_random_draws() -> None:
    episode_id = benchmark_v2_episode_ids(1, 707)[0]
    common = {
        "episode_id": episode_id,
        "data_seed": 808,
        "geography_name": "river_valley",
        "weather_name": "stratiform",
        "observation_times_s": (0.0, 300.0, 600.0),
    }
    in_domain = generate_exogenous_trajectory_v2(**common, ood_name="in_domain")
    shifted = generate_exogenous_trajectory_v2(**common, ood_name="hydrology_shift")
    assert in_domain.random_draws_sha256 == shifted.random_draws_sha256
    assert in_domain.states[0].water_depth_m == shifted.states[0].water_depth_m
    assert shifted.states[-1].water_depth_m > in_domain.states[-1].water_depth_m


def test_observation_capture_and_integrity_are_repeatable() -> None:
    episode = _episode()
    state = episode.trajectory.states[-1]
    camera = camera_profile_v2(episode.camera_name)
    first_package, first_audit = capture_controller_observation_v2(state, camera)
    second_package, second_audit = capture_controller_observation_v2(state, camera)
    assert first_package.record == second_package.record
    assert np.array_equal(first_package.frames, second_package.frames)
    assert first_package.package_sha256 == second_package.package_sha256
    assert first_audit == second_audit

    payload = episode.counterfactuals[0].model_dump(mode="json")
    payload["transition_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="digest mismatch"):
        type(episode.counterfactuals[0]).model_validate(payload)
