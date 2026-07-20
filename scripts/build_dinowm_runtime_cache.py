from __future__ import annotations

import argparse
from pathlib import Path

from trace_jepa.worldmodels.adapters import LinearActionHead
from trace_jepa.worldmodels.dinowm_runtime import build_dinowm_action_feature_cache


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build cached DINO-WM future features for the TRACE runtime adapter"
    )
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--dynamics-checkpoint", type=Path, required=True)
    parser.add_argument("--outcome-head", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    args = parser.parse_args()
    head = LinearActionHead.load(args.outcome_head)
    manifest = build_dinowm_action_feature_cache(
        args.inventory,
        args.dataset,
        args.dynamics_checkpoint,
        args.cache_dir,
        encoder_version=str(head.metadata["encoder_version"]),
        encoder_checkpoint_sha256=str(head.metadata["encoder_checkpoint_sha256"]),
    )
    print(f"manifest={manifest}")


if __name__ == "__main__":
    main()
