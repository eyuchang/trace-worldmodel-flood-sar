# Downloading V-JEPA 2.1 for the Course

## Recommended model

The course default is the official V-JEPA 2.1 ViT-B/16 checkpoint at 384-pixel resolution:

```text
vjepa2_1_vit_base_384
```

It is the smallest V-JEPA 2.1 checkpoint listed by the official repository. Larger models are not a first-week requirement.

## Recommended command

Install a machine-appropriate PyTorch build, then:

```bash
pip install -e ".[jepa]"
trace-jepa-download --model vjepa2_1_vit_base_384
```

The course wrapper:

1. constructs the official model architecture from a pinned upstream Git revision with `pretrained=False`;
2. downloads the official checkpoint to `models/external/vjepa2/`;
3. loads the `ema_encoder` weights explicitly;
4. writes a checksum-bearing manifest to `models/manifests/`.

This is preferable to an unrecorded call that leaves code and weights only in a global cache.

## What the Hub entry returns

The V-JEPA 2.1 Hub entry returns an encoder and a self-supervised pretraining predictor. The course uses the encoder as a frozen visual backbone. The returned predictor is **not** the flood-domain action predictor.

Students separately train:

```text
fused rescue state + versioned action prefix -> future mission predicates
```

## Local-clone path

Use this only when modifying upstream training code:

```bash
mkdir -p third_party
git clone https://github.com/facebookresearch/vjepa2.git third_party/vjepa2
git -C third_party/vjepa2 checkout 204698b45b3712590f06245fbfba32d3be539812
pip install -e third_party/vjepa2
git -C third_party/vjepa2 rev-parse HEAD \
  > models/manifests/vjepa2_source_commit.txt
```

Keep third-party code, weights, and license files separate from the course package.

## Why the course does not use V-JEPA 2-AC directly

The released V-JEPA 2-AC checkpoint was post-trained on robot-arm trajectories and demonstrates reaching, grasping, and pick-and-place. Its action space and training distribution do not match rescue boats, drones, roads, water currents, or incident-command decisions. It is an architectural reference for action conditioning, not a plug-in flood simulator.

## macOS

The official repository documents a `decord` issue on macOS. The course feature-caching path uses OpenCV, but upstream demonstrations and training code should be run on Linux or in a tested container unless the instructor has validated a replacement decoder.
