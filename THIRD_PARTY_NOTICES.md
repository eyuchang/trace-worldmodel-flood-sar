# Third-Party Notices

This repository optionally interoperates with the following open-source model
implementations. Model weights and external source checkouts are not vendored.

## DINO-WM

- Source: <https://github.com/gaoyuezhou/dino_wm>
- Pinned revision: `0a9492fa12044b852ae9e001cc74604b79c8bb0c`
- License: MIT
- Retained license: `third_party/licenses/dino_wm-LICENSE`

`src/trace_jepa/worldmodels/upstream_dinowm.py` contains a modified,
device-independent port of the upstream predictor structure. The file identifies
the modifications and preserves the upstream copyright and license notice.

## V-JEPA 2.1

- Source: <https://github.com/facebookresearch/vjepa2>
- Pinned revision: `204698b45b3712590f06245fbfba32d3be539812`
- License for the model code used by this adapter: MIT
- Retained license: `third_party/licenses/vjepa2-LICENSE`

The V-JEPA integration loads the pinned external implementation and official
checkpoint. It does not vendor V-JEPA source or weights. The upstream repository
also identifies separately licensed Apache-2.0 utility files; those files are not
copied into this repository.

## DINOv2

- Source: <https://github.com/facebookresearch/dinov2>
- Pinned revision: `7764ea0f912e53c92e82eb78a2a1631e92725fc8`
- License: Apache License 2.0
- Retained license: `third_party/licenses/dinov2-LICENSE`

The DINOv2 integration loads the pinned external implementation and official
checkpoint. It does not vendor DINOv2 source or weights.
