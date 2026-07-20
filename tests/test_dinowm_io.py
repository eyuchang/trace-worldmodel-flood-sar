import json

import numpy as np
import pytest

from trace_jepa.worldmodels.dinowm_dataset import (
    capture_dinowm_transitions,
    generate_dinowm_transitions,
    write_dinowm_transition_inventory,
)
from trace_jepa.worldmodels.dinowm_io import (
    encode_dinowm_transition_inventory,
    load_dinowm_transition_dataset,
)
from trace_jepa.worldmodels.simulator_observations import SimulatorVisualObservationStore


class _SpatialSmokeEncoder:
    def encode_images(self, images):
        means = images.astype(np.float32).mean(axis=(1, 2)) / 255.0
        return np.repeat(means[:, None, :], 4, axis=1)


def test_dinowm_io_preserves_episode_splits_and_spatial_tokens(tmp_path):
    transitions = generate_dinowm_transitions(40, data_seed=301, split_seed=302)[:8]
    observation_dir = tmp_path / "observations"
    captured = capture_dinowm_transitions(
        transitions,
        SimulatorVisualObservationStore(observation_dir, num_frames=2, size=32),
    )
    inventory = write_dinowm_transition_inventory(
        tmp_path / "inventory.json",
        captured,
        data_seed=301,
        split_seed=302,
        study_partition="development",
    )
    dataset = tmp_path / "transitions.npz"
    manifest_path = encode_dinowm_transition_inventory(
        inventory,
        observation_dir,
        dataset,
        _SpatialSmokeEncoder(),
        encoder_manifest={"version": "spatial-smoke-v1", "checkpoint_sha256": "none"},
        frame_index=1,
        batch_size=3,
    )
    arrays, manifest = load_dinowm_transition_dataset(dataset)
    assert arrays["current_latents"].shape == (8, 4, 3)
    assert arrays["next_latents"].shape == (8, 4, 3)
    assert manifest["test_included"] is False
    assert json.loads(manifest_path.read_text())["transition_count"] == 8


def test_dinowm_loader_rejects_unauthorized_test_manifest(tmp_path):
    path = tmp_path / "test.npz"
    np.savez_compressed(path, placeholder=np.zeros(1))
    path.with_suffix(".npz.json").write_text(
        json.dumps({"dataset_sha256": "wrong", "test_included": True})
    )
    with pytest.raises(ValueError, match="hash"):
        load_dinowm_transition_dataset(path, allow_test=True)
