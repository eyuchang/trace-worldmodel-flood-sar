"""Companion-package byte guard for the delivered WF-DFLD-01-SMALL evidence."""

from __future__ import annotations

from pathlib import Path

from trace_jepa.support import ArtifactLocator, sha256_file

from .loading import load_small_baseline_registry
from .models import ReferenceSmallBaselineRegistry

DEFAULT_BASELINE_REGISTRY = Path(
    "data/scenario/delta/reference_protocol/small_baseline_v1.json"
)


def verify_small_baseline(
    repository_root: Path,
    registry_relative_name: Path = DEFAULT_BASELINE_REGISTRY,
) -> ReferenceSmallBaselineRegistry:
    """Verify that the Reference branch still contains the delivered Small evidence bytes."""

    registry = load_small_baseline_registry(repository_root, registry_relative_name)
    for item in registry.files:
        resolved = ArtifactLocator(
            root=repository_root,
            relative_name=Path(item.relative_path),
            maximum_bytes=item.maximum_bytes,
            label=f"Small baseline file {item.relative_path}",
        ).resolve()
        if sha256_file(resolved) != item.sha256:
            raise ValueError(f"Small baseline digest mismatch: {item.relative_path}")
    return registry
