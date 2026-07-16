from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from trace_jepa.perception.video import sample_video
from trace_jepa.perception.vjepa import VJEPA2Encoder
from trace_jepa.util import sha256_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Encode one video with the official V-JEPA 2.1 backbone")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="vjepa2_1_vit_base_384")
    parser.add_argument("--frames", type=int, default=64)
    args = parser.parse_args()

    frames, indices = sample_video(args.video, num_frames=args.frames)
    encoder = VJEPA2Encoder(model_name=args.model, crop_size=384)
    embedding = encoder.encode_frames(frames)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output,
        embedding=embedding,
        frame_indices=np.asarray(indices, dtype=np.int32),
    )
    manifest = {
        "video": str(args.video),
        "video_sha256": sha256_file(args.video),
        "model": args.model,
        "num_frames": args.frames,
        "frame_indices": indices,
        "embedding_shape": list(embedding.shape),
    }
    args.output.with_suffix(args.output.suffix + ".json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"Wrote {args.output} with shape {embedding.shape}")


if __name__ == "__main__":
    main()
