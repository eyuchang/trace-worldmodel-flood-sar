from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from trace_jepa.perception.download import (
    clean_backbone_state_dict,
    load_official_vjepa21,
)
from trace_jepa.util import sha256_file


VJEPA21_SOURCE_REPOSITORY = "https://github.com/facebookresearch/vjepa2"
VJEPA21_SOURCE_COMMIT = "204698b45b3712590f06245fbfba32d3be539812"
VJEPA21_VITB_CHECKPOINT_SHA256 = (
    "848a77c33cc9e6649ed2119c9bea1e2c569bcdab9539ff3e7c02ccc2959ddf4d"
)


@dataclass(frozen=True)
class VJEPA21PredictiveSpec:
    model_name: str = "vjepa2_1_vit_base_384"
    crop_size: int = 384
    total_frames: int = 64
    context_frames: int = 48
    patch_size: int = 16
    tubelet_size: int = 2
    source_commit: str = VJEPA21_SOURCE_COMMIT
    checkpoint_sha256: str = VJEPA21_VITB_CHECKPOINT_SHA256

    @property
    def target_frames(self) -> int:
        return self.total_frames - self.context_frames

    @property
    def spatial_token_count(self) -> int:
        return (self.crop_size // self.patch_size) ** 2

    @property
    def context_token_count(self) -> int:
        return (self.context_frames // self.tubelet_size) * self.spatial_token_count

    @property
    def target_token_count(self) -> int:
        return (self.target_frames // self.tubelet_size) * self.spatial_token_count

    def validate(self) -> None:
        if self.total_frames <= 0 or self.context_frames <= 0:
            raise ValueError("V-JEPA frame counts must be positive")
        if self.context_frames >= self.total_frames:
            raise ValueError("V-JEPA predictive masking requires at least one target frame")
        if self.total_frames % self.tubelet_size or self.context_frames % self.tubelet_size:
            raise ValueError("V-JEPA frame windows must align to complete tubelets")
        if self.crop_size % self.patch_size:
            raise ValueError("V-JEPA crop size must align to complete spatial patches")
        if len(self.checkpoint_sha256) != 64:
            raise ValueError("V-JEPA checkpoint identity must be a SHA-256 digest")


class VJEPA21FuturePredictor:
    """Official V-JEPA 2.1 encoder and masked latent predictor adapter.

    The model receives real context frames and placeholder target frames.  Only
    context-token indices reach the encoder; the official predictor fills the
    declared future tubelets.  No Flood-SAR action enters this path because
    dispatch actions do not causally alter the exogenous flood imagery.
    """

    def __init__(
        self,
        *,
        encoder: Any,
        predictor: Any,
        processor: Any,
        device: str,
        checkpoint_path: Path,
        spec: VJEPA21PredictiveSpec | None = None,
    ):
        try:
            import torch
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("V-JEPA requires the optional ML dependencies") from exc

        self.torch = torch
        self.spec = spec or VJEPA21PredictiveSpec()
        self.spec.validate()
        self.encoder = encoder.to(device).eval()
        self.predictor = predictor.to(device).eval()
        self.processor = processor
        self.device = device
        self.checkpoint_path = Path(checkpoint_path)
        if not self.checkpoint_path.is_file() or self.checkpoint_path.is_symlink():
            raise ValueError("official V-JEPA checkpoint is absent or unsafe")
        if sha256_file(self.checkpoint_path) != self.spec.checkpoint_sha256:
            raise ValueError("official V-JEPA checkpoint hash mismatch")
        for module in (self.encoder, self.predictor):
            for parameter in module.parameters():
                parameter.requires_grad_(False)

    @classmethod
    def from_official_checkpoint(
        cls,
        *,
        checkpoint_dir: Path,
        device: str = "cuda",
        local_repo: Path | None = None,
        spec: VJEPA21PredictiveSpec | None = None,
    ) -> "VJEPA21FuturePredictor":
        """Strict-load both official encoder and predictor state dictionaries."""

        import torch

        spec = spec or VJEPA21PredictiveSpec()
        spec.validate()
        source = "local" if local_repo is not None else "github"
        encoder, predictor, processor, checkpoint_path = load_official_vjepa21(
            model_name=spec.model_name,
            crop_size=spec.crop_size,
            checkpoint_dir=checkpoint_dir,
            hub_repo=f"facebookresearch/vjepa2:{spec.source_commit}",
            source=source,
            local_repo=local_repo,
            device=device,
        )
        if predictor is None:
            raise ValueError("official V-JEPA hub entry did not return its predictor")
        if sha256_file(checkpoint_path) != spec.checkpoint_sha256:
            raise ValueError("official V-JEPA checkpoint hash mismatch")
        payload = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        if "predictor" not in payload:
            raise ValueError("official V-JEPA checkpoint omits predictor weights")
        state = clean_backbone_state_dict(payload["predictor"])
        predictor.load_state_dict(state, strict=True)
        return cls(
            encoder=encoder,
            predictor=predictor,
            processor=processor,
            device=device,
            checkpoint_path=checkpoint_path,
            spec=spec,
        )

    def masks(self, batch_size: int = 1):
        if batch_size < 1:
            raise ValueError("V-JEPA mask batch size must be positive")
        context = self.torch.arange(
            self.spec.context_token_count,
            device=self.device,
            dtype=self.torch.long,
        )
        target = self.torch.arange(
            self.spec.context_token_count,
            self.spec.context_token_count + self.spec.target_token_count,
            device=self.device,
            dtype=self.torch.long,
        )
        return context.repeat(batch_size, 1), target.repeat(batch_size, 1)

    def prepare_model_clip(
        self,
        frames: np.ndarray,
        *,
        target_fill: int = 0,
    ):
        """Resample available context and append masked placeholder frames."""

        torch = self.torch
        values = np.asarray(frames)
        if values.ndim != 4 or values.shape[-1] != 3 or values.dtype != np.uint8:
            raise ValueError("V-JEPA frames must be uint8 [T,H,W,3]")
        if len(values) < 2:
            raise ValueError("V-JEPA future prediction requires at least two context frames")
        if not 0 <= target_fill <= 255:
            raise ValueError("V-JEPA target placeholder must be an unsigned-byte value")
        indices = np.rint(
            np.linspace(0, len(values) - 1, self.spec.context_frames)
        ).astype(np.int64)
        context = values[indices]
        target = np.full(
            (self.spec.target_frames, *values.shape[1:]),
            target_fill,
            dtype=np.uint8,
        )
        clip = np.concatenate([context, target], axis=0)
        tensor = torch.from_numpy(np.ascontiguousarray(clip)).permute(0, 3, 1, 2)
        transformed = self.processor(tensor)
        if isinstance(transformed, (list, tuple)):
            if len(transformed) != 1:
                raise ValueError("V-JEPA preprocessor returned multiple undeclared views")
            transformed = transformed[0]
        if transformed.ndim == 4:
            transformed = transformed.unsqueeze(0)
        if transformed.ndim != 5 or transformed.shape[2] != self.spec.total_frames:
            raise ValueError("V-JEPA preprocessor returned an incompatible video tensor")
        return transformed.to(self.device)

    @staticmethod
    def _tensor_output(value: Any):
        if isinstance(value, dict):
            for key in ("last_hidden_state", "x", "features"):
                if key in value:
                    value = value[key]
                    break
        if isinstance(value, (list, tuple)):
            tensors = [item for item in value if hasattr(item, "ndim")]
            if not tensors:
                raise TypeError("V-JEPA encoder output contains no tensor")
            value = tensors[-1]
        if not hasattr(value, "ndim") or value.ndim != 3:
            raise ValueError("V-JEPA encoder output must be [B,N,D]")
        return value

    def predict_future_tokens(
        self,
        frames: np.ndarray,
        *,
        target_fill: int = 0,
    ) -> np.ndarray:
        transformed = self.prepare_model_clip(frames, target_fill=target_fill)
        context_mask, target_mask = self.masks(len(transformed))
        with self.torch.inference_mode():
            encoded = self.encoder(transformed, [context_mask])
            encoded = self._tensor_output(encoded)
            prediction = self.predictor(
                encoded,
                [context_mask],
                [target_mask],
                mod="video",
            )
            if isinstance(prediction, tuple):
                prediction = prediction[0]
            prediction = self._tensor_output(prediction)
        if prediction.shape[1] != self.spec.target_token_count:
            raise ValueError("V-JEPA predictor returned the wrong target-token count")
        values = prediction.detach().cpu().float().numpy()
        if not np.isfinite(values).all():
            raise ValueError("V-JEPA predictor returned non-finite latent tokens")
        return values

    def encode_context_tokens(self, frames: np.ndarray) -> np.ndarray:
        transformed = self.prepare_model_clip(frames, target_fill=0)
        context_mask, _ = self.masks(len(transformed))
        with self.torch.inference_mode():
            encoded = self.encoder(transformed, [context_mask])
            encoded = self._tensor_output(encoded)
        values = encoded.detach().cpu().float().numpy()
        if values.shape[1] != self.spec.context_token_count or not np.isfinite(values).all():
            raise ValueError("V-JEPA encoder returned invalid context tokens")
        return values
