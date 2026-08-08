from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, cast

import numpy as np
from numpy.typing import NDArray

from trace_jepa.contracts import PlanPrediction
from trace_jepa.experimental.profile import AdequacyStatus
from trace_jepa.predictor.protocol import (
    PredictorModel,
    PredictorProvenance,
    PredictorRequest,
    request_feature_vector,
)
from trace_jepa.predictor.qualification import (
    QualificationBinding,
    VerifiedQualification,
    load_qualification_artifact,
    verify_qualification_binding,
)
from trace_jepa.predictor.safe_files import ArtifactLocator, validate_npz_container
from trace_jepa.util import sha256_file


class CalibratedMLPBackend(Protocol):
    def infer(self, request: PredictorRequest) -> list[float]: ...


class MLPCalibrationArtifact(PredictorModel):
    """Separate, content-addressed transformation contract for MLP outputs."""

    schema_version: Literal["mlp-calibration-v1"]
    predictor_version: str
    calibration_version: str
    feature_schema_version: str
    action_schema_version: str
    output_link_version: Literal["delta-plan-prediction-links-v1"]


@dataclass(frozen=True)
class NumpyMLPBackend:
    """Pickle-free two-layer MLP checkpoint used by the runtime adapter."""

    weight_1: NDArray[np.float64]
    bias_1: NDArray[np.float64]
    weight_2: NDArray[np.float64]
    bias_2: NDArray[np.float64]
    action_names: tuple[str, ...]

    @classmethod
    def load(cls, locator: ArtifactLocator) -> tuple[NumpyMLPBackend, dict[str, object]]:
        path = locator.resolve()
        required = {
            "weight_1",
            "bias_1",
            "weight_2",
            "bias_2",
            "action_names",
            "metadata_json",
        }
        validate_npz_container(
            path,
            expected_arrays=required,
            maximum_uncompressed_bytes=100_000_000,
            label="MLP checkpoint",
        )
        try:
            with np.load(path, allow_pickle=False) as payload:
                if set(payload.files) != required:
                    raise ValueError("MLP checkpoint does not satisfy the frozen schema")
                backend = cls(
                    weight_1=payload["weight_1"].astype(np.float64),
                    bias_1=payload["bias_1"].astype(np.float64),
                    weight_2=payload["weight_2"].astype(np.float64),
                    bias_2=payload["bias_2"].astype(np.float64),
                    action_names=tuple(str(value) for value in payload["action_names"]),
                )
                metadata = json.loads(str(payload["metadata_json"].item()))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("MLP checkpoint is malformed") from exc
        backend.validate()
        return backend, metadata

    def validate(self) -> None:
        if self.weight_1.ndim != 2:
            raise ValueError("MLP input weights must be a matrix")
        if self.bias_1.shape != (self.weight_1.shape[1],):
            raise ValueError("MLP hidden bias does not match hidden width")
        if self.weight_2.shape != (self.weight_1.shape[1], 7):
            raise ValueError("MLP output weights must have seven outputs")
        if self.bias_2.shape != (7,):
            raise ValueError("MLP output bias must have seven outputs")
        if not all(
            np.isfinite(value).all()
            for value in (self.weight_1, self.bias_1, self.weight_2, self.bias_2)
        ):
            raise ValueError("MLP checkpoint contains non-finite values")

    def infer(self, request: PredictorRequest) -> list[float]:
        features = np.asarray(
            request_feature_vector(request, action_names=self.action_names),
            dtype=np.float64,
        )
        if features.shape != (self.weight_1.shape[0],):
            raise ValueError("MLP request feature dimension does not match checkpoint")
        hidden = np.maximum(0.0, features @ self.weight_1 + self.bias_1)
        return cast(list[float], (hidden @ self.weight_2 + self.bias_2).tolist())


@dataclass(frozen=True)
class MLPPredictorSpec:
    """Immutable identity and schema surface for one calibrated MLP."""

    predictor_version: str
    calibration_version: str
    training_snapshot: str
    model_hash: str
    calibration_hash: str
    adequacy_status: AdequacyStatus = AdequacyStatus.UNQUALIFIED
    supported_action_types: tuple[str, ...] = (
        "dispatch_rescue_boat",
        "deploy_ground_team",
        "perform_welfare_check",
        "inspect_levee",
    )
    feature_schema_version: str = "action-prefix-features-v2"
    action_schema_version: str = "delta-response-actions-v2"


class MLPActionPrefixPredictor:
    def __init__(
        self,
        backend: CalibratedMLPBackend,
        spec: MLPPredictorSpec | None = None,
        qualification: VerifiedQualification | None = None,
        **legacy_spec: object,
    ) -> None:
        if spec is not None and legacy_spec:
            raise TypeError("provide MLPPredictorSpec or legacy keyword fields, not both")
        if spec is None:
            spec = MLPPredictorSpec(**legacy_spec)  # type: ignore[arg-type]
        self._backend = backend
        self.predictor_version = spec.predictor_version
        self.calibration_version = spec.calibration_version
        self.training_snapshot = spec.training_snapshot
        self.model_hash = spec.model_hash
        self.calibration_hash = spec.calibration_hash
        self.supported_action_types = spec.supported_action_types
        self.feature_schema_version = spec.feature_schema_version
        self.action_schema_version = spec.action_schema_version
        if spec.adequacy_status == AdequacyStatus.QUALIFIED and qualification is None:
            raise ValueError("learned MLP qualification requires a verified artifact")
        if qualification is None:
            self.adequacy_status = spec.adequacy_status
            self.qualified_action_types: tuple[str, ...] = ()
            self.qualification_artifact_sha256: str | None = None
        else:
            self.qualified_action_types = verify_qualification_binding(
                qualification,
                QualificationBinding(
                    predictor_version=self.predictor_version,
                    model_hash=self.model_hash,
                    calibration_version=self.calibration_version,
                    calibration_hash=self.calibration_hash,
                    encoder_version=None,
                    encoder_checkpoint_hash=None,
                    feature_schema_version=self.feature_schema_version,
                    action_schema_version=self.action_schema_version,
                    supported_action_types=self.supported_action_types,
                ),
            )
            self.adequacy_status = AdequacyStatus.QUALIFIED
            self.qualification_artifact_sha256 = qualification.artifact_sha256

    @classmethod
    def from_checkpoint(
        cls,
        path: Path,
        *,
        model_root: Path,
        calibration_path: Path,
        calibration_root: Path,
        qualification_path: Path | None = None,
        qualification_root: Path | None = None,
    ) -> MLPActionPrefixPredictor:
        model_locator = ArtifactLocator.from_path(
            root=model_root,
            path=path,
            maximum_bytes=25_000_000,
            label="MLP checkpoint",
        )
        backend, metadata = NumpyMLPBackend.load(model_locator)
        required = {
            "predictor_version",
            "training_snapshot",
            "feature_schema_version",
            "action_schema_version",
        }
        if set(metadata) != required:
            raise ValueError("MLP checkpoint provenance is incomplete")
        calibration_locator = ArtifactLocator.from_path(
            root=calibration_root,
            path=calibration_path,
            maximum_bytes=1_000_000,
            label="MLP calibration artifact",
        )
        calibration_path = calibration_locator.resolve()
        calibration = MLPCalibrationArtifact.model_validate_json(
            calibration_path.read_text(encoding="utf-8")
        )
        for field_name in (
            "predictor_version",
            "feature_schema_version",
            "action_schema_version",
        ):
            if getattr(calibration, field_name) != str(metadata[field_name]):
                raise ValueError(f"MLP calibration {field_name} mismatch")
        if qualification_path is not None and qualification_root is None:
            raise ValueError("qualification_root is required with qualification_path")
        qualification = None
        if qualification_path is not None and qualification_root is not None:
            qualification = load_qualification_artifact(
                qualification_path, trusted_root=qualification_root
            )
        return cls(
            backend=backend,
            spec=MLPPredictorSpec(
                predictor_version=str(metadata["predictor_version"]),
                calibration_version=calibration.calibration_version,
                training_snapshot=str(metadata["training_snapshot"]),
                model_hash=sha256_file(path),
                calibration_hash=sha256_file(calibration_path),
                adequacy_status=AdequacyStatus.UNQUALIFIED,
                supported_action_types=backend.action_names,
                feature_schema_version=str(metadata["feature_schema_version"]),
                action_schema_version=str(metadata["action_schema_version"]),
            ),
            qualification=qualification,
        )

    def provenance(self) -> PredictorProvenance:
        return PredictorProvenance(
            predictor_version=self.predictor_version,
            calibration_version=self.calibration_version,
            training_snapshot=self.training_snapshot,
            model_hash=self.model_hash,
            calibration_hash=self.calibration_hash,
            adequacy_status=self.adequacy_status,
            qualification_artifact_sha256=self.qualification_artifact_sha256,
            feature_schema_version=self.feature_schema_version,
            action_schema_version=self.action_schema_version,
            supported_action_types=self.supported_action_types,
            qualified_action_types=self.qualified_action_types,
        )

    def predict(self, request: PredictorRequest) -> PlanPrediction:
        if request.plan.first_action.action_type not in self.supported_action_types:
            raise ValueError(
                f"unsupported MLP action type: {request.plan.first_action.action_type}"
            )
        values = self._backend.infer(request)
        if len(values) != 7:
            raise ValueError("calibrated MLP backend must return exactly seven values")
        probabilities = [_stable_sigmoid(value) for value in values]
        return PlanPrediction(
            plan_id=request.plan.plan_id,
            success_probability=probabilities[0],
            arrival_time_s=math.exp(min(values[1], 20.0)),
            hazard_score=probabilities[2],
            resource_margin=values[3],
            model_support=probabilities[4],
            out_of_distribution_score=probabilities[5],
            uncertainty=probabilities[6],
            rollout_horizon=6,
            assumptions=("calibrated_mlp_head",),
        )


def _stable_sigmoid(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("MLP output contains a non-finite value")
    if value >= 0.0:
        return 1.0 / (1.0 + math.exp(-value))
    exponent = math.exp(value)
    return exponent / (1.0 + exponent)
