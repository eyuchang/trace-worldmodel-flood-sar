"""Safe loader for the synthetic Reference resource design fixture."""

from __future__ import annotations

from pathlib import Path

import yaml

from trace_jepa.support import ArtifactLocator

from .domain.resources import ReferenceResourceParameters


def load_reference_resource_parameters(
    root: Path,
    relative_name: Path,
) -> ReferenceResourceParameters:
    path = ArtifactLocator(
        root=root,
        relative_name=relative_name,
        maximum_bytes=1_000_000,
        label="Reference resource parameters",
    ).resolve()
    try:
        payload = yaml.safe_load(path.read_text("utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError("Reference resource parameters are not valid bounded YAML") from exc
    return ReferenceResourceParameters.model_validate(payload)
