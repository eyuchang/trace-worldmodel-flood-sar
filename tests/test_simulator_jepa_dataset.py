from __future__ import annotations

import json

import numpy as np

from trace_jepa.worldmodels.dataset import ACTION_NAMES, load_feature_dataset
from trace_jepa.worldmodels.encoding import (
    DeterministicSmokeEncoder,
    encode_simulator_observations,
)
from trace_jepa.worldmodels.simulator_dataset import (
    DEVELOPMENT_SPLITS,
    capture_simulator_development_episodes,
    generate_simulator_development_episodes,
    write_simulator_feature_dataset,
)
from trace_jepa.worldmodels.simulator_observations import SimulatorVisualObservationStore


def test_simulator_development_campaign_is_deterministic_and_test_locked() -> None:
    first = generate_simulator_development_episodes(
        80, data_seed=101, split_seed=202
    )
    repeated = generate_simulator_development_episodes(
        80, data_seed=101, split_seed=202
    )
    assert [episode.split for episode in first] == [episode.split for episode in repeated]
    assert [episode.snapshot for episode in first] == [episode.snapshot for episode in repeated]
    assert set(episode.split for episode in first) == set(DEVELOPMENT_SPLITS)
    assert all(episode.snapshot.study_partition == "development" for episode in first)
    assert all(episode.request.observed_depth_m is None for episode in first)
    assert all(episode.request.visual_observation_id is None for episode in first)
    for left, right in zip(first, repeated, strict=True):
        for action in ACTION_NAMES:
            assert np.array_equal(
                left.target_by_action[action], right.target_by_action[action]
            )
            assert left.outcome_by_action[action] == right.outcome_by_action[action]


def test_simulator_campaign_joins_verified_features_without_test_rows(tmp_path) -> None:
    episodes = generate_simulator_development_episodes(
        40, data_seed=303, split_seed=404
    )
    observation_dir = tmp_path / "observations"
    captured = capture_simulator_development_episodes(
        episodes,
        SimulatorVisualObservationStore(observation_dir, num_frames=2, size=32),
    )
    assert all(episode.request.visual_observation_id is not None for episode in captured)
    cache_dir = tmp_path / "features"
    summary = encode_simulator_observations(
        observation_dir,
        cache_dir,
        DeterministicSmokeEncoder(),
        encoder_version="deterministic-smoke-encoder-v1",
        encoder_checkpoint_sha256="deterministic-smoke-no-checkpoint",
    )
    assert summary.encoded == 40
    dataset_path = tmp_path / "simulator-development.npz"
    manifest_path = write_simulator_feature_dataset(
        dataset_path,
        captured,
        cache_dir,
        encoder_manifest={
            "family": "deterministic smoke feature extractor",
            "version": "deterministic-smoke-encoder-v1",
            "checkpoint_sha256": "deterministic-smoke-no-checkpoint",
            "smoke_only": True,
        },
        data_seed=303,
        split_seed=404,
    )
    arrays, manifest = load_feature_dataset(dataset_path)
    assert arrays["structured"].shape == (80, 19)
    assert arrays["visual"].shape == (80, 9)
    assert not np.any(arrays["splits"].astype(str) == "test")
    assert manifest["test_generated"] is False
    assert manifest["test_included"] is False
    assert manifest["observation_source"] == "flood-sim-drone-rgb-v2"
    written = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert sum(written["split_episode_counts"].values()) == 40


def test_simulator_campaign_outcomes_follow_declared_water_update() -> None:
    episodes = generate_simulator_development_episodes(
        60, data_seed=505, split_seed=606
    )
    for episode in episodes:
        forcing = (
            0.25
            + 0.75 * episode.request.rain_intensity
            + 0.85 * episode.request.upstream_inflow
        )
        for action_index, action in enumerate(ACTION_NAMES):
            action_travel = episode.request.travel_time_s + 180.0 * action_index
            future_depth = (
                episode.snapshot.water_depth_m
                + episode.request.water_rise_rate
                * forcing
                * episode.request.route_susceptibility
                * action_travel
            )
            remaining_resource = episode.target_by_action[action][3]
            expected = int(
                future_depth < episode.request.route_closure_depth_m
                and not episode.snapshot.debris_blocked
                and remaining_resource > 0.0
            )
            assert episode.outcome_by_action[action] == expected
