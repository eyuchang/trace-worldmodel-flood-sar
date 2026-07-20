from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

import numpy as np

from trace_jepa.contracts import PlanPrediction
from trace_jepa.util import sha256_file
from trace_jepa.worldmodels.calibration import IsotonicCalibrator
from trace_jepa.worldmodels.contracts import (
    RouteWorldModelRequest,
    WorldModelInputUnavailable,
    WorldModelProvenance,
)
from trace_jepa.worldmodels.rendering import RenderedRouteObservation


@dataclass(frozen=True)
class FeatureObservation:
    vector: np.ndarray
    observation_hash: str
    encoder_version: str
    encoder_checkpoint_sha256: str

    def __post_init__(self) -> None:
        vector = np.asarray(self.vector, dtype=np.float32)
        if vector.ndim != 1 or not np.isfinite(vector).all():
            raise ValueError("feature vector must be one-dimensional and finite")
        object.__setattr__(self, "vector", vector)


class RouteFeatureProvider(Protocol):
    def features(self, request: RouteWorldModelRequest) -> FeatureObservation: ...


class CachedRouteFeatureProvider:
    """Load hash-addressed offline features named by controller observation ID."""

    _safe_identifier = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

    def __init__(
        self,
        cache_dir: Path,
        *,
        encoder_version: str,
        encoder_checkpoint_sha256: str,
    ):
        self.cache_dir = Path(cache_dir)
        self.encoder_version = encoder_version
        self.encoder_checkpoint_sha256 = encoder_checkpoint_sha256

    def features(self, request: RouteWorldModelRequest) -> FeatureObservation:
        observation_id = request.visual_observation_id
        if observation_id is None:
            raise WorldModelInputUnavailable("route belief has no visual observation identifier")
        if not self._safe_identifier.fullmatch(observation_id):
            raise WorldModelInputUnavailable("visual observation identifier is not cache-safe")
        path = self.cache_dir / f"{observation_id}.npz"
        if not path.is_file():
            raise WorldModelInputUnavailable(f"cached visual feature is absent: {observation_id}")
        with np.load(path, allow_pickle=False) as payload:
            if "feature" not in payload or "observation_hash" not in payload:
                raise WorldModelInputUnavailable("cached feature does not satisfy the cache schema")
            vector = payload["feature"].astype(np.float32)
            observation_hash = str(payload["observation_hash"].item())
        return FeatureObservation(
            vector=vector,
            observation_hash=observation_hash,
            encoder_version=self.encoder_version,
            encoder_checkpoint_sha256=self.encoder_checkpoint_sha256,
        )


class CachedActionRouteFeatureProvider(CachedRouteFeatureProvider):
    """Load a cached action-conditioned future feature for one observation."""

    def features(self, request: RouteWorldModelRequest) -> FeatureObservation:
        observation_id = request.visual_observation_id
        if observation_id is None:
            raise WorldModelInputUnavailable("route belief has no visual observation identifier")
        if not self._safe_identifier.fullmatch(observation_id):
            raise WorldModelInputUnavailable("visual observation identifier is not cache-safe")
        if not self._safe_identifier.fullmatch(request.action_type):
            raise WorldModelInputUnavailable("action type is not cache-safe")
        cache_id = f"{observation_id}--{request.action_type}"
        path = self.cache_dir / f"{cache_id}.npz"
        if not path.is_file() or path.is_symlink():
            raise WorldModelInputUnavailable(
                f"cached action-conditioned feature is absent: {cache_id}"
            )
        with np.load(path, allow_pickle=False) as payload:
            required = {"feature", "observation_hash", "action_type"}
            if required - set(payload.files):
                raise WorldModelInputUnavailable(
                    "cached action-conditioned feature does not satisfy the cache schema"
                )
            if str(payload["action_type"].item()) != request.action_type:
                raise WorldModelInputUnavailable("cached feature action type mismatch")
            vector = payload["feature"].astype(np.float32)
            observation_hash = str(payload["observation_hash"].item())
        return FeatureObservation(
            vector=vector,
            observation_hash=observation_hash,
            encoder_version=self.encoder_version,
            encoder_checkpoint_sha256=self.encoder_checkpoint_sha256,
        )


class FrozenVJEPAFeatureProvider:
    """Offline-friendly wrapper around a frozen V-JEPA encoder.

    The frame source must return a controller-visible observation. The provider
    never receives the simulator state, which makes hidden-truth access harder to
    introduce accidentally.
    """

    def __init__(
        self,
        encoder,
        frame_source: Callable[[RouteWorldModelRequest], RenderedRouteObservation],
        *,
        encoder_version: str,
        encoder_checkpoint_sha256: str,
    ):
        self.encoder = encoder
        self.frame_source = frame_source
        self.encoder_version = encoder_version
        self.encoder_checkpoint_sha256 = encoder_checkpoint_sha256

    def features(self, request: RouteWorldModelRequest) -> FeatureObservation:
        observation = self.frame_source(request)
        encoded = np.asarray(self.encoder.encode_frames(observation.frames), dtype=np.float32)
        if encoded.ndim == 2 and encoded.shape[0] == 1:
            encoded = encoded[0]
        return FeatureObservation(
            vector=encoded,
            observation_hash=observation.observation_hash,
            encoder_version=self.encoder_version,
            encoder_checkpoint_sha256=self.encoder_checkpoint_sha256,
        )


@dataclass(frozen=True)
class LinearActionHead:
    """Auditable flood-domain linear head trained over frozen representations."""

    weights: np.ndarray
    structured_mean: np.ndarray
    structured_std: np.ndarray
    visual_mean: np.ndarray
    visual_std: np.ndarray
    training_min: np.ndarray
    training_max: np.ndarray
    support_center: np.ndarray
    support_scale: np.ndarray
    residual_rmse: np.ndarray
    action_names: tuple[str, ...]
    calibrator: IsotonicCalibrator
    metadata: dict[str, object]
    checkpoint_sha256: str

    @classmethod
    def load(cls, path: Path) -> "LinearActionHead":
        path = Path(path)
        with np.load(path, allow_pickle=False) as payload:
            metadata = json.loads(str(payload["metadata_json"].item()))
            instance = cls(
                weights=payload["weights"].astype(np.float64),
                structured_mean=payload["structured_mean"].astype(np.float64),
                structured_std=payload["structured_std"].astype(np.float64),
                visual_mean=payload["visual_mean"].astype(np.float64),
                visual_std=payload["visual_std"].astype(np.float64),
                training_min=payload["training_min"].astype(np.float64),
                training_max=payload["training_max"].astype(np.float64),
                support_center=payload["support_center"].astype(np.float64),
                support_scale=payload["support_scale"].astype(np.float64),
                residual_rmse=payload["residual_rmse"].astype(np.float64),
                action_names=tuple(str(value) for value in payload["action_names"].tolist()),
                calibrator=IsotonicCalibrator(
                    thresholds=payload["calibration_thresholds"].astype(np.float64),
                    values=payload["calibration_values"].astype(np.float64),
                ),
                metadata=metadata,
                checkpoint_sha256=sha256_file(path),
            )
        instance.validate()
        return instance

    def validate(self) -> None:
        if np.any(self.structured_std <= 0.0) or np.any(self.visual_std <= 0.0):
            raise ValueError("normalization scales must be positive")
        feature_dim = len(self.structured_mean) + len(self.visual_mean) + len(self.action_names)
        if self.weights.shape != (feature_dim + 1, 4):
            raise ValueError("head weights do not match feature/action dimensions")
        if self.training_min.shape != (feature_dim,) or self.training_max.shape != (feature_dim,):
            raise ValueError("support bounds do not match fused feature dimension")
        if self.support_center.shape != (feature_dim,) or self.support_scale.shape != (
            feature_dim,
        ):
            raise ValueError("support moments do not match fused feature dimension")
        if np.any(self.support_scale <= 0.0):
            raise ValueError("support scales must be positive")
        if self.residual_rmse.shape != (4,):
            raise ValueError("residual_rmse must contain four target scales")

    def _design_row(
        self,
        request: RouteWorldModelRequest,
        visual_features: np.ndarray,
    ) -> np.ndarray:
        structured = np.asarray(request.structured_features, dtype=np.float64)
        visual = np.asarray(visual_features, dtype=np.float64).reshape(-1)
        if structured.shape != self.structured_mean.shape:
            raise ValueError("structured feature schema does not match the checkpoint")
        if visual.shape != self.visual_mean.shape:
            raise ValueError("visual feature dimension does not match the checkpoint")
        try:
            action_index = self.action_names.index(request.action_type)
        except ValueError as exc:
            raise ValueError(f"unsupported action type: {request.action_type}") from exc
        action = np.zeros(len(self.action_names), dtype=np.float64)
        action[action_index] = 1.0
        return np.concatenate(
            [
                (structured - self.structured_mean) / self.structured_std,
                (visual - self.visual_mean) / self.visual_std,
                action,
            ]
        )

    def predict(
        self,
        request: RouteWorldModelRequest,
        visual_features: np.ndarray,
    ) -> tuple[np.ndarray, float, float, float]:
        row = self._design_row(request, visual_features)
        raw = np.concatenate([row, np.ones(1, dtype=np.float64)]) @ self.weights
        outside = np.maximum(self.training_min - row, 0.0) + np.maximum(
            row - self.training_max, 0.0
        )
        span = np.maximum(self.training_max - self.training_min, 1e-6)
        outside_distance = np.linalg.norm(outside / span) / np.sqrt(len(row))
        standardized_distance = np.linalg.norm(
            (row - self.support_center) / self.support_scale
        ) / np.sqrt(len(row))
        ood = float(
            np.clip(
                max(outside_distance, (standardized_distance - 1.5) / 2.5),
                0.0,
                1.0,
            )
        )
        support = float(
            np.clip(
                np.exp(-0.5 * (standardized_distance / 1.5) ** 2)
                * (1.0 - 0.5 * min(1.0, outside_distance)),
                0.0,
                1.0,
            )
        )
        uncertainty = float(np.clip(self.residual_rmse[0] + 0.45 * ood, 0.0, 1.0))
        return raw, support, ood, uncertainty


class VJEPARouteWorldModel:
    def __init__(self, feature_provider: RouteFeatureProvider, head: LinearActionHead):
        self.feature_provider = feature_provider
        self.head = head
        self._last_observation_hash: str | None = None

    @property
    def provenance(self) -> WorldModelProvenance:
        metadata = self.head.metadata
        return WorldModelProvenance(
            encoder_version=str(metadata["encoder_version"]),
            encoder_checkpoint_sha256=str(metadata["encoder_checkpoint_sha256"]),
            predictor_version=str(metadata["predictor_version"]),
            predictor_checkpoint_sha256=self.head.checkpoint_sha256,
            calibration_version=str(metadata["calibration_version"]),
            training_snapshot=str(metadata["training_snapshot"]),
            semantic_probe_versions=tuple(metadata.get("semantic_probe_versions", ())),
            supported_action_types=self.head.action_names,
            feature_schema_version=str(
                metadata.get("feature_schema_version", "route-jepa-fusion-v1")
            ),
        )

    @property
    def last_observation_hash(self) -> str | None:
        return self._last_observation_hash

    def predict(self, request: RouteWorldModelRequest) -> PlanPrediction:
        features = self.feature_provider.features(request)
        provenance = self.provenance
        if features.encoder_version != provenance.encoder_version:
            raise ValueError("runtime encoder version does not match predictor provenance")
        if features.encoder_checkpoint_sha256 != provenance.encoder_checkpoint_sha256:
            raise ValueError("runtime encoder hash does not match predictor provenance")
        raw, support, ood, uncertainty = self.head.predict(request, features.vector)
        visual_freshness_s = float(self.head.metadata.get("visual_freshness_s", 180.0))
        if request.visual_observation_age_s is not None:
            freshness = float(
                np.exp(-request.visual_observation_age_s / max(1.0, visual_freshness_s))
            )
            support = float(np.clip(support * max(0.05, freshness), 0.0, 1.0))
            uncertainty = float(
                np.clip(uncertainty + 0.35 * (1.0 - freshness), 0.0, 1.0)
            )
        success = float(self.head.calibrator.transform(np.clip(raw[0], 0.0, 1.0)))
        self._last_observation_hash = features.observation_hash
        return PlanPrediction(
            plan_id=request.plan_id,
            success_probability=success,
            arrival_time_s=float(max(0.0, raw[1] * 1800.0)),
            hazard_score=float(np.clip(raw[2], 0.0, 1.0)),
            resource_margin=float(raw[3]),
            model_support=support,
            out_of_distribution_score=ood,
            uncertainty=uncertainty,
            rollout_horizon=max(1, int(np.ceil(request.travel_time_s / 180.0))),
            assumptions=tuple(
                self.head.metadata.get(
                    "prediction_assumptions",
                    (
                        "model_conditional_prediction",
                        "frozen_visual_encoder",
                        "controller_visible_inputs_only",
                        "calibrated_on_declared_development_distribution",
                        "visual_freshness_is_gated",
                    ),
                )
            ),
        )


class DINOWMRouteWorldModel(VJEPARouteWorldModel):
    """TRACE adapter over cached DINO-WM action-conditioned future features."""
