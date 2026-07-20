from __future__ import annotations

import argparse
import json
from pathlib import Path

from trace_jepa.perception.vjepa import VJEPA2Encoder
from trace_jepa.util import sha256_file
from trace_jepa.worldmodels.encoding import (
    DeterministicSmokeEncoder,
    encode_simulator_observations,
)
from trace_jepa.worldmodels.simulator_dataset import (
    capture_simulator_development_episodes,
    generate_simulator_development_episodes,
    write_simulator_feature_dataset,
)
from trace_jepa.worldmodels.simulator_observations import SimulatorVisualObservationStore


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build the development-only synchronized simulator/V-JEPA route dataset"
        )
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--observation-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--episodes", type=int, default=400)
    parser.add_argument("--data-seed", type=int, default=20260722)
    parser.add_argument("--split-seed", type=int, default=20260723)
    parser.add_argument("--frames", type=int, default=16)
    parser.add_argument("--frame-step", type=int, default=4)
    parser.add_argument("--size", type=int, default=96)
    parser.add_argument(
        "--encoder",
        choices=("vjepa", "deterministic-smoke"),
        default="vjepa",
    )
    parser.add_argument("--checkpoint-dir", type=Path, default=Path("models/external/vjepa2"))
    args = parser.parse_args()

    episodes = generate_simulator_development_episodes(
        args.episodes,
        data_seed=args.data_seed,
        split_seed=args.split_seed,
    )
    store = SimulatorVisualObservationStore(
        args.observation_dir,
        num_frames=args.frames,
        size=args.size,
        frame_step=args.frame_step,
    )
    captured = capture_simulator_development_episodes(episodes, store)
    print(f"Captured or verified {len(captured)} development observations")

    if args.encoder == "vjepa":
        checkpoint = args.checkpoint_dir / "vjepa2_1_vitb_dist_vitG_384.pt"
        if not checkpoint.is_file():
            raise SystemExit("Official checkpoint is absent; run scripts/download_vjepa.py first.")
        encoder = VJEPA2Encoder(checkpoint_dir=args.checkpoint_dir)
        encoder_version = "facebook-vjepa2.1-vit-b-384@204698b45b37"
        checkpoint_sha256 = sha256_file(checkpoint)
        encoder_manifest: dict[str, object] = {
            "family": "V-JEPA 2.1",
            "version": encoder_version,
            "checkpoint_sha256": checkpoint_sha256,
            "role": "frozen_visual_encoder",
            "source_revision": "204698b45b3712590f06245fbfba32d3be539812",
            "pretraining_predictor_used": False,
            "smoke_only": False,
            "input_frames": args.frames,
            "input_frame_step": args.frame_step,
        }
    else:
        encoder = DeterministicSmokeEncoder()
        encoder_version = "deterministic-smoke-encoder-v1"
        checkpoint_sha256 = "deterministic-smoke-no-checkpoint"
        encoder_manifest = {
            "family": "deterministic smoke feature extractor",
            "version": encoder_version,
            "checkpoint_sha256": checkpoint_sha256,
            "role": "plumbing_test_only",
            "pretraining_predictor_used": False,
            "smoke_only": True,
            "input_frames": args.frames,
            "input_frame_step": args.frame_step,
        }

    summary = encode_simulator_observations(
        args.observation_dir,
        args.cache_dir,
        encoder,
        encoder_version=encoder_version,
        encoder_checkpoint_sha256=checkpoint_sha256,
    )
    expected = {episode.request.visual_observation_id for episode in captured}
    if set(summary.observation_ids) != expected:
        raise ValueError("encoded observation inventory does not match the campaign")
    manifest_path = write_simulator_feature_dataset(
        args.output,
        captured,
        args.cache_dir,
        encoder_manifest=encoder_manifest,
        data_seed=args.data_seed,
        split_seed=args.split_seed,
    )
    print(json.dumps(summary.__dict__, indent=2, sort_keys=True))
    print(f"Wrote dataset: {args.output}")
    print(f"Wrote manifest: {manifest_path}")


if __name__ == "__main__":
    main()
