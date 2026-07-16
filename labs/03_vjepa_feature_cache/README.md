# Lab 3 - Reproducible V-JEPA 2.1 feature cache

## Goal

Use the official V-JEPA 2.1 encoder as a frozen visual backbone while preserving code and weight provenance.

## Tasks

1. Install the optional JEPA dependencies.
2. Download the class-default model through the course wrapper.
3. Inspect the checksum-bearing manifest.
4. Record the source and license of one short, ethically sourced flood-response clip.
5. Encode the same clip twice and compare the video hash, sampled frame indices, model entry point, and feature shape.

## Commands

```bash
pip install -e ".[jepa]"
trace-jepa-download --model vjepa2_1_vit_base_384
python scripts/encode_video.py \
  --video data/raw/demo/flood_clip.mp4 \
  --output data/processed/demo/flood_clip_vjepa.npz
```

## Exit test

A model manifest and feature-cache manifest exist, and repeated encoding preserves the declared input identity and tensor shape.

## Important boundary

The downloaded model is not a flood simulator. It is a representation backbone. The flood-domain action predictor is built in Lab 4.
