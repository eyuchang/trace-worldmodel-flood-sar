from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.experimental.profile import AdequacyStatus
from trace_jepa.predictor.protocol import PredictorModel
from trace_jepa.predictor.safe_files import safe_regular_file
from trace_jepa.util import sha256_file


class QualificationArtifact(PredictorModel):
    """Frozen evidence binding for action-class-specific predictor qualification."""

    schema_version: Literal["predictor-qualification-v1"]
    qualification_id: str
    qualification_scope: Literal["teaching_fixture", "experimental"]
    predictor_version: str
    model_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    calibration_version: str
    calibration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    encoder_version: str | None = None
    encoder_checkpoint_hash: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    feature_schema_version: str
    action_schema_version: str
    qualified_action_types: tuple[str, ...]
    adequacy_status: AdequacyStatus
    evaluation_protocol_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    issuer_name: str
    issuer_role: str
    issued_at_utc: datetime
    claim_limit: str

    @model_validator(mode="after")
    def validate_qualification(self) -> QualificationArtifact:
        if self.adequacy_status != AdequacyStatus.QUALIFIED:
            raise ValueError("a qualification artifact must declare qualified status")
        if not self.qualified_action_types:
            raise ValueError("a qualification artifact must name at least one action class")
        if (self.encoder_version is None) != (self.encoder_checkpoint_hash is None):
            raise ValueError("encoder version and checkpoint hash must be declared together")
        if len(set(self.qualified_action_types)) != len(self.qualified_action_types):
            raise ValueError("qualified action classes must be unique")
        return self


@dataclass(frozen=True)
class VerifiedQualification:
    artifact: QualificationArtifact
    artifact_sha256: str


def load_qualification_artifact(path: Path) -> VerifiedQualification:
    path = Path(path)
    safe_path = safe_regular_file(
        path,
        declared_root=path.parent,
        maximum_bytes=1_000_000,
        label="qualification artifact",
    )
    artifact = QualificationArtifact.model_validate_json(safe_path.read_text(encoding="utf-8"))
    return VerifiedQualification(artifact=artifact, artifact_sha256=sha256_file(safe_path))


def verify_qualification_binding(
    qualification: VerifiedQualification,
    *,
    predictor_version: str,
    model_hash: str,
    calibration_version: str,
    calibration_hash: str,
    encoder_version: str | None,
    encoder_checkpoint_hash: str | None,
    feature_schema_version: str,
    action_schema_version: str,
    supported_action_types: tuple[str, ...],
) -> tuple[str, ...]:
    artifact = qualification.artifact
    expected = {
        "predictor_version": predictor_version,
        "model_hash": model_hash,
        "calibration_version": calibration_version,
        "calibration_hash": calibration_hash,
        "encoder_version": encoder_version,
        "encoder_checkpoint_hash": encoder_checkpoint_hash,
        "feature_schema_version": feature_schema_version,
        "action_schema_version": action_schema_version,
    }
    for field_name, value in expected.items():
        if getattr(artifact, field_name) != value:
            raise ValueError(f"qualification artifact {field_name} mismatch")
    unsupported = set(artifact.qualified_action_types) - set(supported_action_types)
    if unsupported:
        raise ValueError("qualification artifact names unsupported action classes")
    return artifact.qualified_action_types
