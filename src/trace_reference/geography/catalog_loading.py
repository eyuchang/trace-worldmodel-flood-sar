"""Fail-closed loading for the committed Reference geography catalog."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyproj
import shapely
import yaml

from trace_jepa.support import ArtifactLocator, sha256_file

from .builder import SOURCE_RELATIVE_NAMES
from .catalog_models import (
    ReferenceGeographyBuildManifest,
    ReferenceGeographyCatalog,
    ReferenceSourceLifecycleErratum,
    ReferenceSourceRetrievalRegistry,
)


def _json_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Reference geography artifact is not valid bounded JSON") from exc
    if not isinstance(value, dict):
        raise TypeError("Reference geography artifact root must be an object")
    return value


def _yaml_object(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text("utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError("Reference geography provenance is not valid bounded YAML") from exc
    if not isinstance(value, dict):
        raise TypeError("Reference geography provenance root must be an object")
    return value


def _verified_artifact(*, root: Path, relative_name: str, expected_sha256: str, label: str) -> Path:
    path = ArtifactLocator(
        root=root,
        relative_name=Path(relative_name),
        maximum_bytes=1_000_000,
        label=label,
    ).resolve()
    if sha256_file(path) != expected_sha256:
        raise ValueError(f"{label} digest mismatch")
    return path


def _verify_current_provenance(
    geography_root: Path, manifest: ReferenceGeographyBuildManifest
) -> None:
    metadata_name = manifest.metadata_registry_relative_path
    metadata_sha256 = manifest.metadata_registry_sha256
    receipts_name = manifest.retrieval_receipts_relative_path
    receipts_sha256 = manifest.retrieval_receipts_sha256
    if None in {metadata_name, metadata_sha256, receipts_name, receipts_sha256}:
        raise ValueError("current geography provenance is incomplete")
    metadata_path = _verified_artifact(
        root=geography_root,
        relative_name=str(metadata_name),
        expected_sha256=str(metadata_sha256),
        label="Reference geography metadata registry",
    )
    receipts_path = _verified_artifact(
        root=geography_root,
        relative_name=str(receipts_name),
        expected_sha256=str(receipts_sha256),
        label="Reference geography retrieval receipts",
    )
    receipt_registry = ReferenceSourceRetrievalRegistry.model_validate(_yaml_object(receipts_path))
    if receipt_registry.metadata_registry_sha256 != sha256_file(metadata_path):
        raise ValueError("Reference receipt registry metadata binding mismatch")
    lifecycle_name = manifest.source_lifecycle_relative_path
    lifecycle_sha256 = manifest.source_lifecycle_sha256
    if manifest.manifest_version == "delta-reference-geography-build-v3":
        if lifecycle_name is None or lifecycle_sha256 is None:
            raise ValueError("Reference geography source lifecycle binding is incomplete")
        lifecycle_path = _verified_artifact(
            root=geography_root,
            relative_name=lifecycle_name,
            expected_sha256=lifecycle_sha256,
            label="Reference geography source lifecycle erratum",
        )
        ReferenceSourceLifecycleErratum.model_validate(_yaml_object(lifecycle_path))

    package_root = Path(__file__).parent
    for relative_name, expected_digest in manifest.transformation_source_sha256.items():
        _verified_artifact(
            root=package_root,
            relative_name=relative_name,
            expected_sha256=expected_digest,
            label=f"Reference transformation source {relative_name}",
        )
    actual_environment = {
        "pyproj": pyproj.__version__,
        "proj": pyproj.proj_version_str,
        "shapely": shapely.__version__,
        "geos": shapely.geos_version_string,
    }
    if manifest.environment_versions != actual_environment:
        raise ValueError("Reference geography geospatial environment mismatch")


def load_reference_geography(
    *,
    geography_root: Path,
    manifest_relative_name: Path = Path("derived/reference_geography_build_manifest_v3.json"),
) -> ReferenceGeographyCatalog:
    """Load the exact offline catalog and verify every bound source snapshot."""

    manifest_path = ArtifactLocator(
        root=geography_root,
        relative_name=manifest_relative_name,
        maximum_bytes=1_000_000,
        label="Reference geography build manifest",
    ).resolve()
    manifest = ReferenceGeographyBuildManifest.model_validate(_json_object(manifest_path))
    if manifest.manifest_version in {
        "delta-reference-geography-build-v2",
        "delta-reference-geography-build-v3",
    }:
        _verify_current_provenance(geography_root, manifest)
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
