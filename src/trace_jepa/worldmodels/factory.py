from __future__ import annotations

from pathlib import Path

from trace_jepa.worldmodels.adapters import (
    CachedRouteFeatureProvider,
    LinearActionHead,
    VJEPARouteWorldModel,
)


def build_cached_vjepa_route_model(
    checkpoint_path: Path,
    feature_cache_dir: Path,
) -> VJEPARouteWorldModel:
    """Build the runtime adapter without loading the heavyweight encoder.

    Runtime lookup is by the controller belief's ``visual_observation_id``. A
    missing synchronized feature causes a fail-closed prediction in the workbench;
    it never triggers an undeclared surrogate fallback.
    """

    head = LinearActionHead.load(checkpoint_path)
    provider = CachedRouteFeatureProvider(
        feature_cache_dir,
        encoder_version=str(head.metadata["encoder_version"]),
        encoder_checkpoint_sha256=str(head.metadata["encoder_checkpoint_sha256"]),
    )
    return VJEPARouteWorldModel(provider, head)
