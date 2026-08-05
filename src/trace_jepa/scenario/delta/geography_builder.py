from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field

from trace_jepa.scenario.delta.geography_derivation import build_geography_catalog
from trace_jepa.scenario.delta.geography_models import GeographyCatalog, SourceRecord
from trace_jepa.scenario.delta.geography_sources import (
    DWR_DEM_ARCHIVE_URL,
    GEOGRAPHY_SOURCE_DEFINITIONS,
    GeographySourceDefinition,
)

LOGGER = logging.getLogger(__name__)
BUILDER_VERSION = "delta-small-geography-builder-v2"
RETRIEVED_UTC = datetime.fromisoformat("2026-08-05T16:00:00+00:00")
COORDINATE_REFERENCE = "EPSG:4326+EPSG:26910-fixed-point-v1"
SIMPLIFICATION_TOLERANCE_M = 10.0
DEM_ARCHIVE_MEMBER = "dem_delta_10m_20250312.tif"
DEM_EXTRACTION_COMMAND = "unzip -p dem_delta_10m_20250312.zip dem_delta_10m_20250312.tif"


class BuildBounds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    south_e7: int
    west_e7: int
    north_e7: int
    east_e7: int


class GeographyBuildManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    builder_version: str
    built_utc: datetime
    coordinate_reference: str
    simplification_tolerance_m: float = Field(gt=0.0)
    raster_crs: str
    raster_vertical_datum: str
    raster_nodata_handling: str
    bounds: BuildBounds
    sources: list[SourceRecord] = Field(min_length=1)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _fetch_source(
    client: httpx.Client,
    definition: GeographySourceDefinition,
    source_root: Path,
) -> SourceRecord:
    try:
        response = client.get(definition.locator)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"failed to retrieve {definition.source_id}") from exc
    destination = source_root / definition.file_name
    destination.write_bytes(response.content)
    return SourceRecord(
        source_id=definition.source_id,
        title=definition.title,
        locator=definition.locator,
        snapshot_file_name=f"sources/{definition.file_name}",
        retrieved_utc=RETRIEVED_UTC,
        source_tier=definition.source_tier,
        status=definition.status,
        use=definition.use,
        license_name=definition.license_name,
        license_locator=definition.license_locator,
        redistribution_status=definition.redistribution_status,
        sha256=_sha256_file(destination),
        byte_length=destination.stat().st_size,
    )


def _dem_records(dem_archive_path: Path, dem_raster_path: Path) -> list[SourceRecord]:
    common = {
        "locator": DWR_DEM_ARCHIVE_URL,
        "retrieved_utc": RETRIEVED_UTC,
        "source_tier": "authoritative-state-elevation-product",
        "license_name": "Public access with required source citation",
        "license_locator": (
            "https://data.cnra.ca.gov/dataset/"
            "san-francisco-bay-and-sacramento-san-joaquin-delta-dem-for-modeling-"
            "version-4-3"
        ),
        "redistribution_status": "upstream-binary-not-committed-derived-summary-only",
    }
    return [
        SourceRecord(
            source_id="dwr-bay-delta-dem-v4.3-delta-10m-archive",
            title="DWR Bay-Delta DEM v4.3 Delta 10 m raster archive",
            snapshot_file_name="upstream:dem_delta_10m_20250312.zip",
            status="version-4.3-delta-10m-archive",
            use="authoritative container for the extracted elevation raster",
            sha256=_sha256_file(dem_archive_path),
            byte_length=dem_archive_path.stat().st_size,
            **common,
        ),
        SourceRecord(
            source_id="dwr-bay-delta-dem-v4.3-delta-10m-raster",
            title="DWR Bay-Delta DEM v4.3 extracted Delta 10 m GeoTIFF",
            snapshot_file_name="upstream:dem_delta_10m_20250312.tif",
            status="verified-extracted-archive-member",
            use="clipped island elevation summaries",
            archive_member=DEM_ARCHIVE_MEMBER,
            extraction_command=DEM_EXTRACTION_COMMAND,
            sha256=_sha256_file(dem_raster_path),
            byte_length=dem_raster_path.stat().st_size,
            **common,
        ),
    ]


def _write_manifest(manifest: GeographyBuildManifest, manifest_path: Path) -> str:
    payload = _canonical_json_bytes(manifest.model_dump(mode="json"))
    manifest_path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def build_delta_small_geography(
    source_root: Path,
    geography_path: Path,
    manifest_path: Path,
    dem_archive_path: Path,
    dem_raster_path: Path,
    *,
    refresh_sources: bool = False,
) -> GeographyCatalog:
    """Build the frozen Small catalog, using local snapshots unless refreshed explicitly."""
    source_root.mkdir(parents=True, exist_ok=True)
    source_records: list[SourceRecord] = []
    if refresh_sources:
        with httpx.Client(
            follow_redirects=True,
            timeout=60.0,
            headers={"User-Agent": "TRACE-Delta-Research/1.0 (reproducible GIS build)"},
        ) as client:
            source_records = [
                _fetch_source(client, definition, source_root)
                for definition in GEOGRAPHY_SOURCE_DEFINITIONS
            ]
    else:
        for definition in GEOGRAPHY_SOURCE_DEFINITIONS:
            snapshot = source_root / definition.file_name
            if not snapshot.is_file() or snapshot.is_symlink():
                raise FileNotFoundError(f"missing safe frozen source snapshot: {snapshot}")
            source_records.append(
                SourceRecord(
                    source_id=definition.source_id,
                    title=definition.title,
                    locator=definition.locator,
                    snapshot_file_name=f"sources/{definition.file_name}",
                    retrieved_utc=RETRIEVED_UTC,
                    source_tier=definition.source_tier,
                    status=definition.status,
                    use=definition.use,
                    license_name=definition.license_name,
                    license_locator=definition.license_locator,
                    redistribution_status=definition.redistribution_status,
                    sha256=_sha256_file(snapshot),
                    byte_length=snapshot.stat().st_size,
                )
            )
    source_records.extend(_dem_records(dem_archive_path, dem_raster_path))
    source_records.sort(key=lambda source: source.source_id)
    manifest = GeographyBuildManifest(
        schema_version="delta-small-geography-build-manifest-v2",
        builder_version=BUILDER_VERSION,
        built_utc=RETRIEVED_UTC,
        coordinate_reference=COORDINATE_REFERENCE,
        simplification_tolerance_m=SIMPLIFICATION_TOLERANCE_M,
        raster_crs="EPSG:26910",
        raster_vertical_datum="NAVD88 metres",
        raster_nodata_handling="masked raster cells excluded before integer-mm summaries",
        bounds=BuildBounds(
            south_e7=380_500_000,
            west_e7=-1_217_500_000,
            north_e7=382_500_000,
            east_e7=-1_214_500_000,
        ),
        sources=source_records,
    )
    manifest_sha256 = _write_manifest(manifest, manifest_path)
    catalog = build_geography_catalog(source_root, dem_raster_path, manifest_sha256, source_records)
    geography_path.write_text(
        yaml.safe_dump(catalog.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    LOGGER.info("Built %s with manifest %s", geography_path, manifest_sha256)
    return catalog
