"""Fail-closed loading for frozen Reference calibration artifacts."""

from __future__ import annotations

from pathlib import Path

from trace_jepa.support import ArtifactLocator

from .models import ReferenceTruthCoefficientSet
from .observation_models import ReferenceObservationCoefficientSet

_MAX_COEFFICIENT_BYTES = 1_000_000


def load_reference_truth_coefficients(
    trusted_root: Path,
    relative_name: Path,
) -> ReferenceTruthCoefficientSet:
    """Load a digest-validated coefficient set beneath an explicit trusted root."""

    path = ArtifactLocator(
        root=trusted_root,
        relative_name=relative_name,
        maximum_bytes=_MAX_COEFFICIENT_BYTES,
        label="Reference truth coefficients",
    ).resolve()
    try:
        return ReferenceTruthCoefficientSet.model_validate_json(path.read_text("utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("Reference truth coefficients are invalid") from exc


def load_reference_observation_coefficients(
    trusted_root: Path,
    relative_name: Path,
) -> ReferenceObservationCoefficientSet:
    """Load digest-validated observation coefficients beneath a trusted root."""

    path = ArtifactLocator(
        root=trusted_root,
        relative_name=relative_name,
        maximum_bytes=_MAX_COEFFICIENT_BYTES,
        label="Reference observation coefficients",
    ).resolve()
    try:
        return ReferenceObservationCoefficientSet.model_validate_json(path.read_text("utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("Reference observation coefficients are invalid") from exc
