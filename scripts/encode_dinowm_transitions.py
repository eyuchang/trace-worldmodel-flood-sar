from __future__ import annotations

import argparse
import json
from pathlib import Path

from trace_jepa.perception.dinov2 import (
    DINOv2EncoderSpec,
    DINOv2PatchEncoder,
    resolve_dinov2_checkpoint,
)
from trace_jepa.util import sha256_file
from trace_jepa.worldmodels.dinowm_io import encode_dinowm_transition_inventory


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Encode synchronized Flood-SAR transitions with frozen DINOv2 patch tokens"
    )
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--observation-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input-size", type=int, default=112)
    parser.add_argument("--frame-index", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--test-authorization-manifest", type=Path)
    args = parser.parse_args()

    spec = DINOv2EncoderSpec(input_size=args.input_size)
    encoder = DINOv2PatchEncoder(spec=spec)
    checkpoint = resolve_dinov2_checkpoint(spec.model_name)
    encoder_manifest = {
        "family": "DINOv2",
        "version": f"{spec.model_name}@{spec.source_revision[:12]}",
        "model_name": spec.model_name,
        "source_revision": spec.source_revision,
        "feature_key": spec.feature_key,
        "input_size": spec.input_size,
        "patch_size": 14,
        "patch_count": (spec.input_size // 14) ** 2,
        "feature_dim": 384,
        "checkpoint_sha256": sha256_file(checkpoint),
        "frozen": True,
    }
    manifest_path = encode_dinowm_transition_inventory(
        args.inventory,
        args.observation_dir,
        args.output,
        encoder,
        encoder_manifest=encoder_manifest,
        frame_index=args.frame_index,
        batch_size=args.batch_size,
        test_authorization_manifest=args.test_authorization_manifest,
    )
    print(json.dumps(encoder_manifest, indent=2, sort_keys=True))
    print(f"dataset={args.output}")
    print(f"manifest={manifest_path}")


if __name__ == "__main__":
    main()
