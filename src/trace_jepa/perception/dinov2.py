from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


DINOV2_SOURCE_REVISION = "7764ea0f912e53c92e82eb78a2a1631e92725fc8"


@dataclass(frozen=True)
class DINOv2EncoderSpec:
    model_name: str = "dinov2_vits14"
    input_size: int = 112
    source_revision: str = DINOV2_SOURCE_REVISION
    feature_key: str = "x_norm_patchtokens"


class DINOv2PatchEncoder:
    """Frozen DINOv2 spatial encoder for offline world-model trajectories."""

    def __init__(
        self,
        *,
        spec: DINOv2EncoderSpec | None = None,
        model=None,
        repository: str | None = None,
        local_repo: Path | None = None,
        device: str = "cpu",
    ):
        try:
            import torch
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("DINOv2 encoding requires the optional jepa dependencies") from exc

        self.spec = spec or DINOv2EncoderSpec()
        if self.spec.input_size < 28 or self.spec.input_size % 14 != 0:
            raise ValueError("DINOv2 input_size must be a positive multiple of patch size 14")
        if model is None:  # pragma: no cover - exercised by the offline integration command
            if local_repo is not None:
                if not Path(local_repo).is_dir() or Path(local_repo).is_symlink():
                    raise ValueError("local DINOv2 repository is absent or unsafe")
                model = torch.hub.load(
                    str(local_repo),
                    self.spec.model_name,
                    source="local",
                    pretrained=True,
                )
            else:
                pinned_repository = repository or (
                    f"facebookresearch/dinov2:{self.spec.source_revision}"
                )
                model = torch.hub.load(
                    pinned_repository,
                    self.spec.model_name,
                    pretrained=True,
                )
        self.device = device
        self.model = model.to(device).eval()
        for parameter in self.model.parameters():
            parameter.requires_grad_(False)

    def _prepare(self, images: np.ndarray):
        import torch
        import torch.nn.functional as functional

        values = np.asarray(images)
        if values.ndim != 4 or values.shape[-1] != 3 or values.dtype != np.uint8:
            raise ValueError("DINOv2 images must be uint8 [batch,height,width,3]")
        tensor = torch.from_numpy(np.ascontiguousarray(values)).permute(0, 3, 1, 2).float()
        tensor = tensor / 255.0
        tensor = functional.interpolate(
            tensor,
            size=(self.spec.input_size, self.spec.input_size),
            mode="bicubic",
            align_corners=False,
            antialias=True,
        )
        mean = torch.tensor((0.485, 0.456, 0.406), dtype=tensor.dtype)[None, :, None, None]
        std = torch.tensor((0.229, 0.224, 0.225), dtype=tensor.dtype)[None, :, None, None]
        return ((tensor - mean) / std).to(self.device)

    def encode_images(self, images: np.ndarray) -> np.ndarray:
        import torch

        inputs = self._prepare(images)
        with torch.inference_mode():
            output = self.model.forward_features(inputs)
        if self.spec.feature_key not in output:
            raise ValueError(f"DINOv2 output is missing {self.spec.feature_key}")
        features = output[self.spec.feature_key].detach().cpu().numpy().astype(np.float32)
        expected_patches = (self.spec.input_size // 14) ** 2
        if (
            features.ndim != 3
            or features.shape[0] != len(images)
            or features.shape[1] != expected_patches
            or not np.isfinite(features).all()
        ):
            raise ValueError("DINOv2 returned an invalid spatial feature tensor")
        return features


def resolve_dinov2_checkpoint(model_name: str = "dinov2_vits14") -> Path:
    """Resolve the official torch-hub weight file after model construction."""

    import torch

    expected = Path(torch.hub.get_dir()) / "checkpoints" / f"{model_name}_pretrain.pth"
    if not expected.is_file() or expected.is_symlink():
        raise ValueError(f"official DINOv2 checkpoint was not found: {expected.name}")
    return expected
