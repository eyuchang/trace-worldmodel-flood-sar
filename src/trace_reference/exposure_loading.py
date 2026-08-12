"""Safe loader for the synthetic Reference exposure profile."""

from __future__ import annotations

from pathlib import Path

import yaml

from trace_jepa.support import ArtifactLocator

from .domain.exposure import ReferenceExposureParameters


def load_reference_exposure_parameters(
    root: Path,
    relative_name: Path,
) -> ReferenceExposureParameters:
    path = ArtifactLocator(
        root=root,
        relative_name=relative_name,
        maximum_bytes=1_000_000,
        label="Reference exposure parameters",
    ).resolve()
    try:
        payload = yaml.safe_load(path.read_text("utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError("Reference exposure parameters are not valid bounded YAML") from exc
    return ReferenceExposureParameters.model_validate(payload)
