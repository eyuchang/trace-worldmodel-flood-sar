import json

import pytest

from trace_jepa.worldmodels.dinowm_dataset import (
    capture_dinowm_transitions,
    generate_dinowm_transitions,
    write_dinowm_transition_inventory,
)
from trace_jepa.worldmodels.simulator_observations import SimulatorVisualObservationStore


def test_dinowm_transitions_follow_existing_action_horizon_dynamics(tmp_path):
    transitions = generate_dinowm_transitions(
        40,
        data_seed=101,
        split_seed=102,
    )
    assert len(transitions) == 80
    for first, second in zip(transitions[::2], transitions[1::2], strict=True):
        assert first.episode.episode_id == second.episode.episode_id
        assert first.current_snapshot == second.current_snapshot
        assert first.next_snapshot.water_depth_m <= second.next_snapshot.water_depth_m
        assert first.next_snapshot.observed_at < second.next_snapshot.observed_at
        assert first.split == second.split

    store = SimulatorVisualObservationStore(tmp_path / "observations", num_frames=2, size=32)
    captured = capture_dinowm_transitions(transitions, store)
    assert captured[0].current_observation == captured[1].current_observation
    assert captured[0].next_observation != captured[1].next_observation
    inventory = write_dinowm_transition_inventory(
        tmp_path / "inventory.json",
        captured,
        data_seed=101,
        split_seed=102,
        study_partition="development",
    )
    payload = json.loads(inventory.read_text())
    assert payload["episode_count"] == 40
    assert payload["transition_count"] == 80
    assert sum(payload["split_episode_counts"].values()) == 40


def test_dinowm_test_generation_fails_without_frozen_authorization():
    with pytest.raises(ValueError, match="frozen authorization"):
        generate_dinowm_transitions(
            40,
            data_seed=201,
            split_seed=202,
            study_partition="test",
        )
