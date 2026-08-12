"""Safe loading for versioned Reference physical parameters."""

from __future__ import annotations

from pathlib import Path

import yaml

from trace_jepa.support import ArtifactLocator

from .domain.physical import ReferencePhysicalParameters


def load_reference_physical_parameters(
    root: Path,
    relative_name: Path,
) -> ReferencePhysicalParameters:
    path = ArtifactLocator(
        root=root,
        relative_name=relative_name,
        maximum_bytes=1_000_000,
        label="Reference physical parameters",
    ).resolve()
    try:
        value = yaml.safe_load(path.read_text("utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError("Reference physical parameters are not valid bounded YAML") from exc
    return ReferencePhysicalParameters.model_validate(value)
