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


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Verify simulator drone observations and build the offline route-feature cache"
        )
    )
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument(
        "--encoder",
        choices=("vjepa", "deterministic-smoke"),
        default="vjepa",
    )
    parser.add_argument("--checkpoint-dir", type=Path, default=Path("models/external/vjepa2"))
    parser.add_argument("--include-test", action="store_true")
    parser.add_argument("--test-authorization-manifest", type=Path)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    args = parser.parse_args()

    if args.encoder == "vjepa":
        checkpoint = args.checkpoint_dir / "vjepa2_1_vitb_dist_vitG_384.pt"
        if not checkpoint.is_file():
            raise SystemExit("Official checkpoint is absent; run scripts/download_vjepa.py first.")
        encoder = VJEPA2Encoder(checkpoint_dir=args.checkpoint_dir)
        encoder_version = "facebook-vjepa2.1-vit-b-384@204698b45b37"
        checkpoint_sha256 = sha256_file(checkpoint)
    else:
        encoder = DeterministicSmokeEncoder()
        encoder_version = "deterministic-smoke-encoder-v1"
        checkpoint_sha256 = "deterministic-smoke-no-checkpoint"

    summary = encode_simulator_observations(
        args.observations,
        args.cache_dir,
        encoder,
        encoder_version=encoder_version,
        encoder_checkpoint_sha256=checkpoint_sha256,
        include_test=args.include_test,
        test_authorization_manifest=args.test_authorization_manifest,
        shard_index=args.shard_index,
        shard_count=args.shard_count,
    )
    print(json.dumps(summary.__dict__, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
