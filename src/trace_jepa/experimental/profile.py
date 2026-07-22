"""Predictor-version provenance via the experimental-profile extension path.

Core TRACE contracts remain frozen under ``extra=\"forbid\"``. RQ5 provenance
fields that are not yet part of the teaching schema attach here as an optional
extension on ``WorldModelEvidence``, keeping baseline consumers unchanged.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from trace_jepa.contracts.models import FrozenModel
from trace_jepa.util import new_id, sha256_value, utc_now


class AdequacyStatus(str, Enum):
    """Calibration / version adequacy for the declared claim family."""

    QUALIFIED = "qualified"
    UNQUALIFIED = "unqualified"
    SUPERSEDED = "superseded"
    PENDING_REVALIDATION = "pending_revalidation"


class ExperimentalProfileExtension(FrozenModel):
    """Optional experimental-profile provenance block.

    Fields:
    - ``predictor_version``: model identity used for the prediction
    - ``calibration_version``: calibration snapshot tied to that model
    - ``prediction_timestamp``: when the prediction was produced
    - ``claim_family``: semantic family used for class-conditional adequacy
    - ``adequacy_status``: qualified / unqualified / superseded / pending
    """

    profile_id: str = Field(default_factory=lambda: new_id("exp-profile"))
    profile_schema_version: str = "experimental-profile-v1"
    predictor_version: str
    calibration_version: str
    prediction_timestamp: datetime = Field(default_factory=utc_now)
    claim_family: str
    adequacy_status: AdequacyStatus
    model_hash: str | None = None
    calibration_hash: str | None = None
    notes: tuple[str, ...] = ()


class PredictorVersionReplacement(FrozenModel):
    """Structural event recording an explicit mid-mission predictor swap."""

    event_id: str = Field(default_factory=lambda: new_id("model-replace"))
    event_type: str = "predictor_version_replacement"
    old_predictor_version: str
    new_predictor_version: str
    old_model_hash: str
    new_model_hash: str
    new_calibration_version: str
    new_adequacy_status: AdequacyStatus = AdequacyStatus.UNQUALIFIED
    simulation_time_s: float = Field(ge=0.0)
    recorded_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_store_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def build_experimental_profile(
    *,
    predictor_version: str,
    calibration_version: str,
    claim_family: str,
    adequacy_status: AdequacyStatus,
    prediction_timestamp: datetime | None = None,
    model_hash: str | None = None,
    calibration_hash: str | None = None,
    notes: tuple[str, ...] = (),
) -> ExperimentalProfileExtension:
    resolved_hash = model_hash or sha256_value(
        {
            "predictor_version": predictor_version,
            "calibration_version": calibration_version,
        }
    )
    return ExperimentalProfileExtension(
        predictor_version=predictor_version,
        calibration_version=calibration_version,
        prediction_timestamp=prediction_timestamp or utc_now(),
        claim_family=claim_family,
        adequacy_status=adequacy_status,
        model_hash=resolved_hash,
        calibration_hash=calibration_hash,
        notes=notes,
    )
