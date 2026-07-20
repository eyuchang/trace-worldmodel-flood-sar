from __future__ import annotations

import argparse
from pathlib import Path

from trace_jepa.worldmodels.dinowm_dataset import (
    capture_dinowm_transitions,
    generate_dinowm_transitions,
    write_dinowm_transition_inventory,
)
from trace_jepa.worldmodels.simulator_observations import SimulatorVisualObservationStore


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build synchronized Flood-SAR current/action/next observation transitions"
    )
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--observation-dir", type=Path, required=True)
    parser.add_argument("--episodes", type=int, default=600)
    parser.add_argument("--data-seed", type=int, default=20260730)
    parser.add_argument("--split-seed", type=int, default=20260731)
    parser.add_argument("--study-partition", choices=("development", "test"), default="development")
    parser.add_argument("--test-authorization-manifest", type=Path)
    parser.add_argument("--frames", type=int, default=2)
    parser.add_argument("--size", type=int, default=96)
    args = parser.parse_args()

    transitions = generate_dinowm_transitions(
        args.episodes,
        data_seed=args.data_seed,
        split_seed=args.split_seed,
        study_partition=args.study_partition,
        test_authorization_manifest=args.test_authorization_manifest,
    )
    store = SimulatorVisualObservationStore(
        args.observation_dir,
        num_frames=args.frames,
        size=args.size,
    )
    captured = capture_dinowm_transitions(transitions, store)
    write_dinowm_transition_inventory(
        args.inventory,
        captured,
        data_seed=args.data_seed,
        split_seed=args.split_seed,
        study_partition=args.study_partition,
    )
    print(f"episodes={len({row.episode.episode_id for row in captured})}")
    print(f"transitions={len(captured)}")
    print(f"inventory={args.inventory}")


if __name__ == "__main__":
    main()
