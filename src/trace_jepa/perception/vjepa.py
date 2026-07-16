from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from trace_jepa.perception.download import load_official_vjepa21


class VJEPA2Encoder:
    """Adapter around the official V-JEPA 2.1 encoder and preprocessing code.

    The course uses the returned encoder as a frozen representation backbone. The
    self-supervised pretraining predictor is retained only for provenance and is not
    treated as the flood-domain action model.
    """

    def __init__(
        self,
        *,
        model_name: str = "vjepa2_1_vit_base_384",
        crop_size: int = 384,
        device: str | None = None,
        hub_repo: str = "facebookresearch/vjepa2:204698b45b3712590f06245fbfba32d3be539812",
        source: str = "github",
        local_repo: Path | None = None,
        checkpoint_dir: Path = Path("models/external/vjepa2"),
    ):
        try:
            import torch
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("Install the 'jepa' optional dependencies first") from exc

        self.torch = torch
        self.model_name = model_name
        self.crop_size = crop_size
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        (
            self.encoder,
            self.pretraining_predictor,
            self.processor,
            self.checkpoint_path,
        ) = load_official_vjepa21(
            model_name=model_name,
            crop_size=crop_size,
            checkpoint_dir=checkpoint_dir,
            hub_repo=hub_repo,
            source=source,
            local_repo=local_repo,
            device=self.device,
        )

    @staticmethod
    def _normalize_output(output: Any):
        if isinstance(output, dict):
            for key in ("last_hidden_state", "x", "features"):
                if key in output:
                    output = output[key]
                    break
        if isinstance(output, (list, tuple)):
            tensors = [item for item in output if hasattr(item, "ndim")]
            if not tensors:
                raise TypeError("V-JEPA output did not contain a tensor")
            output = tensors[-1]
        return output

    @staticmethod
    def pool_features(features):
        if features.ndim == 3:
            return features.mean(dim=1)
        if features.ndim == 2:
            return features
        if features.ndim > 3:
            # Preserve the batch axis and average every token-like axis.
            return features.flatten(start_dim=1).mean(dim=1, keepdim=True)
        raise ValueError(f"unexpected V-JEPA feature shape: {tuple(features.shape)}")

    def encode_frames(self, frames: np.ndarray) -> np.ndarray:
        """Encode RGB frames shaped ``[T,H,W,C]`` or ``[T,C,H,W]``.

        The official transform accepts a clip in ``[T,C,H,W]`` and returns the
        model-ready video tensor. The encoder receives a leading batch dimension.
        """
        torch = self.torch
        if frames.ndim != 4:
            raise ValueError("frames must have four dimensions")
        tensor = torch.from_numpy(frames)
        if tensor.shape[-1] in (1, 3, 4):
            tensor = tensor[..., :3].permute(0, 3, 1, 2)
        elif tensor.shape[1] not in (1, 3):
            raise ValueError("cannot infer channel dimension")
        transformed = self.processor(tensor)
        if transformed.ndim == 4:
            transformed = transformed.unsqueeze(0)
        if transformed.ndim != 5:
            raise ValueError(
                "official preprocessor should return [C,T,H,W] or [B,C,T,H,W]; "
                f"received {tuple(transformed.shape)}"
            )
        transformed = transformed.to(self.device)
        with torch.inference_mode():
            output = self.encoder(transformed)
            features = self._normalize_output(output)
            pooled = self.pool_features(features)
        return pooled.detach().cpu().float().numpy()
