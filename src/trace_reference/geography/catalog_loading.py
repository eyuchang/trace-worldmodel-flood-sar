"""Fail-closed loading for the committed Reference geography catalog."""

from __future__ import annotations

import json
from pathlib import Path

from trace_jepa.support import ArtifactLocator, sha256_file

from .builder import SOURCE_RELATIVE_NAMES
from .catalog_models import ReferenceGeographyBuildManifest, ReferenceGeographyCatalog


def _json_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Reference geography artifact is not valid bounded JSON") from exc
    if not isinstance(value, dict):
        raise TypeError("Reference geography artifact root must be an object")
    return value


def load_reference_geography(
    *,
    geography_root: Path,
    manifest_relative_name: Path = Path("derived/reference_geography_build_manifest_v1.json"),
) -> ReferenceGeographyCatalog:
    """Load the exact offline catalog and verify every bound source snapshot."""

    manifest_path = ArtifactLocator(
        root=geography_root,
        relative_name=manifest_relative_name,
        maximum_bytes=1_000_000,
        label="Reference geography build manifest",
    ).resolve()
    manifest = ReferenceGeographyBuildManifest.model_validate(_json_object(manifest_path))
    catalog_path = ArtifactLocator(
        root=manifest_path.parent,
        relative_name=Path(manifest.catalog_relative_path),
        maximum_bytes=25_000_000,
        label="Reference geography catalog",
    ).resolve()
    if sha256_file(catalog_path) != manifest.catalog_sha256:
        raise ValueError("Reference geography catalog digest mismatch")
    sources_root = geography_root / "sources"
    for source_id, expected_digest in manifest.source_snapshot_sha256.items():
        relative_name = SOURCE_RELATIVE_NAMES.get(source_id)
        if relative_name is None:
            raise ValueError(f"Reference geography manifest contains unknown source {source_id}")
        source_path = ArtifactLocator(
            root=sources_root,
            relative_name=Path(relative_name),
            maximum_bytes=25_000_000,
            label=f"Reference geography source {source_id}",
        ).resolve()
        if sha256_file(source_path) != expected_digest:
            raise ValueError(f"Reference geography source digest mismatch: {source_id}")
    catalog = ReferenceGeographyCatalog.model_validate(_json_object(catalog_path))
    if {item.source_id: item.committed_snapshot_sha256 for item in catalog.sources} != (
        manifest.source_snapshot_sha256
    ):
        raise ValueError("Reference catalog and build manifest source bindings disagree")
    return catalog
