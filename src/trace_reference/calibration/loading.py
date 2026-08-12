"""Fail-closed loading for frozen Reference calibration artifacts."""

from __future__ import annotations

from pathlib import Path

from trace_jepa.support import ArtifactLocator

from .models import ReferenceTruthCoefficientSet

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
