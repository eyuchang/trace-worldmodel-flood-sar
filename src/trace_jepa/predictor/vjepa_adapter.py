from __future__ import annotations

import json
import math
import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

from trace_jepa.contracts import PlanPrediction
from trace_jepa.experimental.profile import AdequacyStatus
from trace_jepa.predictor.protocol import (
    PredictorProvenance,
    PredictorRequest,
    request_feature_vector,
)
from trace_jepa.predictor.qualification import (
    VerifiedQualification,
    verify_qualification_binding,
)
from trace_jepa.predictor.safe_files import safe_regular_file, validate_npz_container
from trace_jepa.util import sha256_file


class PredictorInputUnavailable(RuntimeError):
    """Raised when a declared learned-model input cannot be verified."""


def _npy_bytes(value: NDArray[Any]) -> bytes:
    stream = BytesIO()
    np.save(stream, value, allow_pickle=False)
    return stream.getvalue()


def write_deterministic_npz(path: Path, arrays: dict[str, NDArray[Any]]) -> None:
    """Write byte-stable, pickle-free arrays with fixed ZIP metadata."""
    path = Path(path)
    if path.parent.is_symlink():
        raise ValueError("NPZ output parent must not be a symlink")
    try:
        resolved_parent = path.parent.resolve(strict=True)
    except OSError as exc:
        raise ValueError("NPZ output parent is absent") from exc
    if not resolved_parent.is_dir():
        raise ValueError("NPZ output parent must be a directory")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("NPZ output must be a safe regular file")
    with (
        path.open("wb") as destination,
        zipfile.ZipFile(
            destination,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive,
    ):
        for name, value in sorted(arrays.items()):
            file_name = name if name.endswith(".npy") else f"{name}.npy"
            metadata = zipfile.ZipInfo(file_name, date_time=(1980, 1, 1, 0, 0, 0))
            metadata.compress_type = zipfile.ZIP_DEFLATED
            metadata.external_attr = 0o600 << 16
            archive.writestr(
                metadata,
                _npy_bytes(value),
                compress_type=zipfile.ZIP_DEFLATED,
            )


def write_deterministic_feature_cache(
    path: Path,
    *,
    feature: NDArray[Any],
    observation_sha256: str,
    encoder_version: str,
    encoder_checkpoint_hash: str,
    feature_schema_version: str = "vjepa-frozen-feature-v1",
) -> None:
    """Write a byte-stable, pickle-free V-JEPA feature-cache record."""
    write_deterministic_npz(
        path,
        {
            "encoder_checkpoint_hash": np.asarray(encoder_checkpoint_hash),
            "encoder_version": np.asarray(encoder_version),
            "feature": np.asarray(feature, dtype=np.float32),
            "feature_schema_version": np.asarray(feature_schema_version),
            "observation_sha256": np.asarray(observation_sha256),
        },
    )


@dataclass(frozen=True)
class VJEPAFeatureObservation:
    vector: NDArray[np.float32]
    observation_sha256: str
    encoder_version: str
    encoder_checkpoint_hash: str
    feature_schema_version: str

    def __post_init__(self) -> None:
        vector = np.asarray(self.vector, dtype=np.float32)
        if vector.ndim != 1 or not np.isfinite(vector).all():
            raise ValueError("V-JEPA feature vector must be one-dimensional and finite")
        object.__setattr__(self, "vector", vector)


class CachedVJEPAFeatureProvider:
    """Load verified offline V-JEPA features without pickle or implicit fallback."""

    _safe_identifier = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

    def __init__(
        self,
        cache_dir: Path,
        *,
        encoder_version: str,
        encoder_checkpoint_hash: str,
        feature_schema_version: str = "vjepa-frozen-feature-v1",
        maximum_age_s: int = 300,
    ) -> None:
        candidate_root = Path(cache_dir)
        if candidate_root.is_symlink():
            raise ValueError("V-JEPA feature-cache root must not be a symlink")
        try:
            resolved_root = candidate_root.resolve(strict=True)
        except OSError as exc:
            raise ValueError("V-JEPA feature-cache root is absent") from exc
        if not resolved_root.is_dir():
            raise ValueError("V-JEPA feature-cache root must be a directory")
        self.cache_dir = candidate_root
        self.encoder_version = encoder_version
        self.encoder_checkpoint_hash = encoder_checkpoint_hash
        self.feature_schema_version = feature_schema_version
        self.maximum_age_s = maximum_age_s

    def features(self, request: PredictorRequest) -> VJEPAFeatureObservation:
        reference = request.observation.context.visual_feature
        if reference is None:
            raise PredictorInputUnavailable("prediction has no visual feature reference")
        if not self._safe_identifier.fullmatch(reference.observation_id):
            raise PredictorInputUnavailable("visual observation identifier is unsafe")
        if reference.captured_at_s > request.observation.context.simulation_time_s:
            raise PredictorInputUnavailable("visual feature timestamp is in the future")
        age_s = request.observation.context.simulation_time_s - reference.captured_at_s
        if age_s > self.maximum_age_s:
            raise PredictorInputUnavailable("visual feature is stale")
        if reference.encoder_version != self.encoder_version:
            raise PredictorInputUnavailable("visual encoder version mismatch")
        if reference.encoder_checkpoint_hash != self.encoder_checkpoint_hash:
            raise PredictorInputUnavailable("visual encoder checkpoint mismatch")
        if reference.feature_schema_version != self.feature_schema_version:
            raise PredictorInputUnavailable("visual feature schema mismatch")
        path = self.cache_dir / f"{reference.observation_id}.npz"
        required = {
            "feature",
            "observation_sha256",
            "encoder_version",
            "encoder_checkpoint_hash",
            "feature_schema_version",
        }
        try:
            path = safe_regular_file(
                path,
                declared_root=self.cache_dir,
                maximum_bytes=100_000_000,
                label="cached V-JEPA feature",
            )
            validate_npz_container(
                path,
                expected_arrays=required,
                maximum_uncompressed_bytes=500_000_000,
                label="cached V-JEPA feature",
            )
        except ValueError as exc:
            raise PredictorInputUnavailable(str(exc)) from exc
        if sha256_file(path) != reference.feature_cache_sha256:
            raise PredictorInputUnavailable("visual feature-cache digest mismatch")
        try:
            with np.load(path, allow_pickle=False) as payload:
                if set(payload.files) != required:
                    raise PredictorInputUnavailable(
                        "cached V-JEPA feature does not satisfy the frozen schema"
                    )
                feature = payload["feature"].astype(np.float32)
                observation_sha256 = str(payload["observation_sha256"].item())
                encoder_version = str(payload["encoder_version"].item())
                encoder_checkpoint_hash = str(payload["encoder_checkpoint_hash"].item())
                feature_schema_version = str(payload["feature_schema_version"].item())
        except (OSError, ValueError) as exc:
            raise PredictorInputUnavailable("cached V-JEPA feature is malformed") from exc
        if observation_sha256 != reference.observation_sha256:
            raise PredictorInputUnavailable("visual observation digest mismatch")
        if encoder_version != self.encoder_version:
            raise PredictorInputUnavailable("visual encoder version mismatch")
        if encoder_checkpoint_hash != self.encoder_checkpoint_hash:
            raise PredictorInputUnavailable("visual encoder checkpoint mismatch")
        if feature_schema_version != self.feature_schema_version:
            raise PredictorInputUnavailable("visual feature schema mismatch")
        return VJEPAFeatureObservation(
            vector=feature,
            observation_sha256=observation_sha256,
            encoder_version=encoder_version,
            encoder_checkpoint_hash=encoder_checkpoint_hash,
            feature_schema_version=feature_schema_version,
        )


@dataclass(frozen=True)
class CalibratedVJEPAHead:
    """Small auditable flood head over frozen visual and structured features."""

    weights: NDArray[np.float64]
    bias: NDArray[np.float64]
    feature_mean: NDArray[np.float64]
    feature_std: NDArray[np.float64]
    action_names: tuple[str, ...]
    metadata: dict[str, object]
    checkpoint_hash: str

    @classmethod
    def load(cls, path: Path) -> CalibratedVJEPAHead:
        path = Path(path)
        required = {
            "weights",
            "bias",
            "feature_mean",
            "feature_std",
            "action_names",
            "metadata_json",
        }
        try:
            path = safe_regular_file(
                path,
                declared_root=path.parent,
                maximum_bytes=100_000_000,
                label="V-JEPA flood head",
            )
            validate_npz_container(
                path,
                expected_arrays=required,
                maximum_uncompressed_bytes=500_000_000,
                label="V-JEPA flood head",
            )
        except ValueError as exc:
            raise PredictorInputUnavailable(str(exc)) from exc
        try:
            with np.load(path, allow_pickle=False) as payload:
                if set(payload.files) != required:
                    raise PredictorInputUnavailable(
                        "V-JEPA flood head does not satisfy the frozen schema"
                    )
                metadata = json.loads(str(payload["metadata_json"].item()))
                instance = cls(
                    weights=payload["weights"].astype(np.float64),
                    bias=payload["bias"].astype(np.float64),
                    feature_mean=payload["feature_mean"].astype(np.float64),
                    feature_std=payload["feature_std"].astype(np.float64),
                    action_names=tuple(str(value) for value in payload["action_names"]),
                    metadata=metadata,
                    checkpoint_hash=sha256_file(path),
                )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise PredictorInputUnavailable("V-JEPA flood head is malformed") from exc
        instance.validate()
        return instance

    def validate(self) -> None:
        if self.weights.ndim != 2 or self.weights.shape[1] != 7:
            raise ValueError("V-JEPA flood-head weights must have seven outputs")
        if self.bias.shape != (7,):
            raise ValueError("V-JEPA flood-head bias must have seven outputs")
        if self.feature_mean.shape != (self.weights.shape[0],):
            raise ValueError("V-JEPA feature mean does not match head input")
        if self.feature_std.shape != self.feature_mean.shape:
            raise ValueError("V-JEPA feature scale does not match head input")
        if np.any(self.feature_std <= 0.0):
            raise ValueError("V-JEPA feature scales must be positive")
        if not all(
            np.isfinite(value).all()
            for value in (self.weights, self.bias, self.feature_mean, self.feature_std)
        ):
            raise ValueError("V-JEPA flood head contains non-finite values")
        required_metadata = {
            "predictor_version",
            "calibration_version",
            "calibration_hash",
            "training_snapshot",
            "encoder_version",
            "encoder_checkpoint_hash",
            "feature_schema_version",
            "action_schema_version",
        }
        if required_metadata - set(self.metadata):
            raise ValueError("V-JEPA flood-head metadata is incomplete")

    def infer(
        self,
        request: PredictorRequest,
        visual: NDArray[Any],
    ) -> NDArray[np.float64]:
        structured = np.asarray(
            request_feature_vector(request, action_names=self.action_names),
            dtype=np.float64,
        )
        inputs = np.concatenate([structured, np.asarray(visual, dtype=np.float64)])
        if inputs.shape != self.feature_mean.shape:
            raise ValueError("V-JEPA runtime feature dimension does not match head")
        normalized = (inputs - self.feature_mean) / self.feature_std
        return cast(NDArray[np.float64], normalized @ self.weights + self.bias)


class VJEPABackedActionPrefixPredictor:
    """Versioned V-JEPA feature adapter with a separately calibrated flood head."""

    def __init__(
        self,
        feature_provider: CachedVJEPAFeatureProvider,
        flood_head: CalibratedVJEPAHead,
        *,
        adequacy_status: AdequacyStatus = AdequacyStatus.UNQUALIFIED,
        qualification: VerifiedQualification | None = None,
    ) -> None:
        self._feature_provider = feature_provider
        self._flood_head = flood_head
        metadata = flood_head.metadata
        self.predictor_version = str(metadata["predictor_version"])
        self.calibration_version = str(metadata["calibration_version"])
        self.training_snapshot = str(metadata["training_snapshot"])
        self.model_hash = flood_head.checkpoint_hash
        self.calibration_hash = str(metadata["calibration_hash"])
        self.encoder_version = str(metadata["encoder_version"])
        self.encoder_checkpoint_hash = str(metadata["encoder_checkpoint_hash"])
        self.feature_schema_version = str(metadata["feature_schema_version"])
        self.action_schema_version = str(metadata["action_schema_version"])
        self.supported_action_types = flood_head.action_names
        if feature_provider.encoder_version != self.encoder_version:
            raise ValueError("feature provider encoder version disagrees with flood head")
        if feature_provider.encoder_checkpoint_hash != self.encoder_checkpoint_hash:
            raise ValueError("feature provider encoder hash disagrees with flood head")
        if feature_provider.feature_schema_version != "vjepa-frozen-feature-v1":
            raise ValueError("feature provider cache schema is unsupported")
        if adequacy_status == AdequacyStatus.QUALIFIED and qualification is None:
            raise ValueError("learned V-JEPA qualification requires a verified artifact")
        if qualification is None:
            self.adequacy_status = adequacy_status
            self.qualified_action_types: tuple[str, ...] = ()
            self.qualification_artifact_sha256: str | None = None
        else:
            self.qualified_action_types = verify_qualification_binding(
                qualification,
                predictor_version=self.predictor_version,
                model_hash=self.model_hash,
                calibration_version=self.calibration_version,
                calibration_hash=self.calibration_hash,
                encoder_version=self.encoder_version,
                encoder_checkpoint_hash=self.encoder_checkpoint_hash,
                feature_schema_version=self.feature_schema_version,
                action_schema_version=self.action_schema_version,
                supported_action_types=self.supported_action_types,
            )
            self.adequacy_status = AdequacyStatus.QUALIFIED
            self.qualification_artifact_sha256 = qualification.artifact_sha256

    def provenance(self) -> PredictorProvenance:
        return PredictorProvenance(
            predictor_version=self.predictor_version,
            calibration_version=self.calibration_version,
            training_snapshot=self.training_snapshot,
            model_hash=self.model_hash,
            calibration_hash=self.calibration_hash,
            adequacy_status=self.adequacy_status,
            qualification_artifact_sha256=self.qualification_artifact_sha256,
            encoder_version=self.encoder_version,
            encoder_checkpoint_hash=self.encoder_checkpoint_hash,
            feature_schema_version=self.feature_schema_version,
            action_schema_version=self.action_schema_version,
            supported_action_types=self.supported_action_types,
            qualified_action_types=self.qualified_action_types,
        )

    def predict(self, request: PredictorRequest) -> PlanPrediction:
        action_type = request.plan.first_action.action_type
        if action_type not in self.supported_action_types:
            raise ValueError(f"unsupported V-JEPA action type: {action_type}")
        features = self._feature_provider.features(request)
        values = self._flood_head.infer(request, features.vector)
        probabilities = [_stable_sigmoid(float(value)) for value in values]
        return PlanPrediction(
            plan_id=request.plan.plan_id,
            success_probability=probabilities[0],
            arrival_time_s=math.exp(min(float(values[1]), 20.0)),
            hazard_score=probabilities[2],
            resource_margin=float(values[3]),
            model_support=probabilities[4],
            out_of_distribution_score=probabilities[5],
            uncertainty=probabilities[6],
            rollout_horizon=6,
            assumptions=(
                "frozen_vjepa_visual_encoder",
                "separately_calibrated_flood_head",
                "controller_visible_inputs_only",
            ),
        )


def _stable_sigmoid(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("V-JEPA head output contains a non-finite value")
    if value >= 0.0:
        return 1.0 / (1.0 + math.exp(-value))
    exponent = math.exp(value)
    return exponent / (1.0 + exponent)
