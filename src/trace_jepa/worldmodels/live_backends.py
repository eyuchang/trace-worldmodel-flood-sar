from __future__ import annotations

from typing import Any

import numpy as np

from trace_jepa.worldmodels.contracts import (
    ModelArtifactIdentity,
    RouteWorldModelRequestV2,
)
from trace_jepa.worldmodels.dinowm import DINOWMPredictorConfig
from trace_jepa.worldmodels.live_service import LiveBackendOutput


def simple_visual_features(frames: np.ndarray) -> np.ndarray:
    """Return a fixed ten-dimensional, nonlearned visual representation."""

    values = np.asarray(frames, dtype=np.float64) / 255.0
    if values.ndim != 4 or values.shape[-1] != 3 or len(values) < 2:
        raise ValueError("simple visual control requires at least two RGB frames")
    means = values.mean(axis=(0, 1, 2))
    standard_deviations = values.std(axis=(0, 1, 2))
    temporal = np.abs(np.diff(values, axis=0)).mean(axis=(0, 1, 2))
    grayscale = values.mean(axis=-1)
    gradient_y, gradient_x = np.gradient(grayscale, axis=(1, 2))
    edge = np.sqrt(gradient_x**2 + gradient_y**2).mean()
    result = np.concatenate([means, standard_deviations, temporal, [edge]])
    if result.shape != (10,) or not np.isfinite(result).all():
        raise ValueError("simple visual control produced an invalid vector")
    return result.astype(np.float32)


class DeterministicFeatureControlBackend:
    """Verified live-chain control that contains no fitted parameters."""

    device_type = "cpu"
    precision = "float32"

    def __init__(
        self,
        *,
        control: str,
        identity: ModelArtifactIdentity,
        environment_manifest_sha256: str,
    ):
        if control not in {"structured", "simple_visual"}:
            raise ValueError("unsupported deterministic feature control")
        if identity.integration_kind != "deterministic-control":
            raise ValueError("feature control requires a deterministic-control identity")
        self.control = control
        self._identity = identity
        self._environment_manifest_sha256 = environment_manifest_sha256

    @property
    def identity(self) -> ModelArtifactIdentity:
        return self._identity

    @property
    def environment_manifest_sha256(self) -> str:
        return self._environment_manifest_sha256

    def synchronize(self) -> None:
        return None

    def infer(
        self, *, frames: np.ndarray, request: RouteWorldModelRequestV2
    ) -> LiveBackendOutput:
        if self.control == "simple_visual":
            values = simple_visual_features(frames)
        else:
            values = np.asarray(request.structured_features, dtype=np.float32)
            if values.ndim != 1 or not np.isfinite(values).all():
                raise ValueError("structured control produced an invalid vector")
        return LiveBackendOutput(
            semantic_state=None,
            latent_tokens=values[None, None, :],
            diagnostics={
                "control": self.control,
                "fitted_parameters": False,
                "supporting_only": True,
                "feature_dimension": int(len(values)),
            },
        )


class VJEPAPredictiveLatentBackend:
    """Official V-JEPA future-token inference for supporting TRACE evidence."""

    device_type = "cuda"
    precision = "float32"

    def __init__(
        self,
        *,
        predictor: Any,
        identity: ModelArtifactIdentity,
        environment_manifest_sha256: str,
    ):
        if identity.integration_kind != "official-upstream":
            raise ValueError("V-JEPA live inference requires an official-upstream identity")
        if identity.dynamics_checkpoint_sha256 is None:
            raise ValueError("V-JEPA identity must bind the predictor checkpoint")
        self.predictor = predictor
        self._identity = identity
        self._environment_manifest_sha256 = environment_manifest_sha256
        declared_device = str(getattr(predictor, "device", "cuda"))
        self.device_type = declared_device.split(":", 1)[0]

    @property
    def identity(self) -> ModelArtifactIdentity:
        return self._identity

    @property
    def environment_manifest_sha256(self) -> str:
        return self._environment_manifest_sha256

    def synchronize(self) -> None:
        if self.device_type == "cuda":
            import torch

            torch.cuda.synchronize(getattr(self.predictor, "device", None))

    def infer(
        self, *, frames: np.ndarray, request: RouteWorldModelRequestV2
    ) -> LiveBackendOutput:
        prediction = np.asarray(
            self.predictor.predict_future_tokens(frames),
            dtype=np.float32,
        )
        if prediction.ndim != 3 or len(prediction) != 1:
            raise ValueError("V-JEPA live predictor returned an invalid latent tensor")
        return LiveBackendOutput(
            semantic_state=None,
            latent_tokens=prediction,
            diagnostics={
                "action_conditioned": False,
                "supporting_only": True,
                "target_token_count": int(prediction.shape[1]),
                "feature_dimension": int(prediction.shape[2]),
            },
        )


class DINOWMPredictiveLatentBackend:
    """Frozen DINOv2 encoder plus trained action-conditioned DINO-WM predictor."""

    precision = "float32"

    def __init__(
        self,
        *,
        encoder: Any,
        predictor: Any,
        predictor_config: DINOWMPredictorConfig,
        action_names: tuple[str, ...],
        identity: ModelArtifactIdentity,
        environment_manifest_sha256: str,
        device: str = "cuda",
        frame_index: int = -1,
    ):
        if identity.dynamics_checkpoint_sha256 is None:
            raise ValueError("DINO-WM identity must bind the dynamics checkpoint")
        if tuple(sorted(set(action_names))) != tuple(sorted(action_names)):
            raise ValueError("DINO-WM action names must be unique")
        if set(action_names) != set(identity.supported_action_types):
            raise ValueError("DINO-WM actions do not match the model identity")
        self.encoder = encoder
        self.predictor = predictor.to(device).eval()
        self.predictor_config = predictor_config
        self.action_names = action_names
        self._identity = identity
        self._environment_manifest_sha256 = environment_manifest_sha256
        self.device = device
        self.device_type = device.split(":", 1)[0]
        self.frame_index = frame_index
        for parameter in self.predictor.parameters():
            parameter.requires_grad_(False)

    @property
    def identity(self) -> ModelArtifactIdentity:
        return self._identity

    @property
    def environment_manifest_sha256(self) -> str:
        return self._environment_manifest_sha256

    def synchronize(self) -> None:
        if self.device_type == "cuda":
            import torch

            torch.cuda.synchronize(self.device)

    def infer(
        self, *, frames: np.ndarray, request: RouteWorldModelRequestV2
    ) -> LiveBackendOutput:
        import torch

        frame_index = self.frame_index
        if frame_index < 0:
            frame_index += len(frames)
        if frame_index < 0 or frame_index >= len(frames):
            raise ValueError("DINO-WM frame index is outside the delivered clip")
        current = np.asarray(
            self.encoder.encode_images(frames[frame_index : frame_index + 1]),
            dtype=np.float32,
        )
        expected = (
            1,
            self.predictor_config.patch_count,
            self.predictor_config.feature_dim,
        )
        if current.shape != expected:
            raise ValueError("DINOv2 live features do not match the predictor checkpoint")
        try:
            action_index = self.action_names.index(request.action_type)
        except ValueError as exc:
            raise ValueError("DINO-WM request uses an unsupported action") from exc
        current_tensor = torch.from_numpy(current).to(self.device)
        action_tensor = torch.tensor([action_index], dtype=torch.long, device=self.device)
        with torch.inference_mode():
            predicted = self.predictor(current_tensor, action_tensor)
        values = predicted.detach().cpu().float().numpy()
        if values.shape != expected or not np.isfinite(values).all():
            raise ValueError("DINO-WM live predictor returned invalid future tokens")
        return LiveBackendOutput(
            semantic_state=None,
            latent_tokens=values,
            diagnostics={
                "action_conditioned": True,
                "supporting_only": True,
                "action_index": action_index,
                "patch_count": int(values.shape[1]),
                "feature_dimension": int(values.shape[2]),
                "frame_index": frame_index,
            },
        )
