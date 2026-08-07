from __future__ import annotations

import hashlib
import json
import logging
import os
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

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
BUILDER_VERSION = "delta-small-geography-builder-v3"
RETRIEVED_UTC = datetime.fromisoformat("2026-08-05T16:00:00+00:00")
FROZEN_V3_BUILD_UTC = datetime.fromisoformat("2026-08-07T05:35:00+00:00")
COORDINATE_REFERENCE = "EPSG:4326+EPSG:26910-fixed-point-v1"
SIMPLIFICATION_TOLERANCE_M = 10.0
DEM_ARCHIVE_MEMBER = "dem_delta_10m_20250312.tif"
DEM_EXTRACTION_COMMAND = "unzip -p dem_delta_10m_20250312.zip dem_delta_10m_20250312.tif"
MAXIMUM_SOURCE_BYTES = 25_000_000


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


class GeographyBuildSecurityError(ValueError):
    """Raised before unsafe or malformed external data can enter the frozen bundle."""


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


def _safe_regular_input(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise GeographyBuildSecurityError(f"{label} must not be a symlink: {path}")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise GeographyBuildSecurityError(f"{label} must be a regular file: {resolved}")
    return resolved


def _safe_output_path(path: Path) -> Path:
    if path.is_symlink():
        raise GeographyBuildSecurityError(f"output must not be a symlink: {path}")
    parent = path.parent
    if parent.is_symlink():
        raise GeographyBuildSecurityError(f"output parent must not be a symlink: {parent}")
    parent.mkdir(parents=True, exist_ok=True)
    if not parent.is_dir():
        raise GeographyBuildSecurityError(f"output parent must be a directory: {parent}")
    return path


def _atomic_write(path: Path, payload: bytes) -> None:
    destination = _safe_output_path(path)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_name = stream.name
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary = Path(temporary_name)
        if temporary.is_symlink() or not temporary.is_file():
            raise GeographyBuildSecurityError("temporary geography output is not regular")
        os.replace(temporary, destination)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def _validate_snapshot_payload(
    definition: GeographySourceDefinition,
    payload: bytes,
    media_type: str,
) -> None:
    if not payload:
        raise GeographyBuildSecurityError(f"empty response for {definition.source_id}")
    if len(payload) > MAXIMUM_SOURCE_BYTES:
        raise GeographyBuildSecurityError(
            f"response for {definition.source_id} exceeds {MAXIMUM_SOURCE_BYTES} bytes"
        )
    normalized_media_type = media_type.partition(";")[0].strip().lower()
    accepted = {item.partition(";")[0].strip().lower() for item in definition.expected_media_types}
    if normalized_media_type not in accepted:
        raise GeographyBuildSecurityError(
            f"unexpected media type for {definition.source_id}: {media_type!r}"
        )
    if definition.snapshot_format not in {"json", "geojson"}:
        raise GeographyBuildSecurityError(
            f"{definition.source_id} has no machine-readable refresh contract"
        )
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GeographyBuildSecurityError(
            f"machine-readable response is invalid JSON for {definition.source_id}"
        ) from exc
    if definition.snapshot_format == "geojson":
        if not isinstance(value, dict) or value.get("type") != "FeatureCollection":
            raise GeographyBuildSecurityError(
                f"GeoJSON FeatureCollection required for {definition.source_id}"
            )
        if not isinstance(value.get("features"), list):
            raise GeographyBuildSecurityError(
                f"GeoJSON features array required for {definition.source_id}"
            )


def _source_record_from_frozen(
    definition: GeographySourceDefinition,
    snapshot: Path,
) -> SourceRecord:
    media_type = {
        "geojson": "application/geo+json",
        "json": "application/json",
        "html": "text/html",
    }[definition.snapshot_format]
    return SourceRecord(
        source_id=definition.source_id,
        title=definition.title,
        locator=definition.landing_page_locator,
        landing_page_locator=definition.landing_page_locator,
        retrieval_locator=definition.retrieval_locator,
        media_type=media_type,
        snapshot_format=definition.snapshot_format,
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


def _fetch_source(
    client: httpx.Client,
    definition: GeographySourceDefinition,
    source_root: Path,
) -> SourceRecord:
    if definition.retrieval_locator is None:
        raise GeographyBuildSecurityError(
            f"{definition.source_id} has no validated machine-readable retrieval endpoint"
        )
    if source_root.is_symlink():
        raise GeographyBuildSecurityError(f"source root must not be a symlink: {source_root}")
    destination = _safe_output_path(source_root / definition.file_name)
    if destination.parent.resolve(strict=True) != source_root.resolve(strict=True):
        raise GeographyBuildSecurityError(f"source output escapes source root: {destination}")
    temporary_name: str | None = None
    try:
        try:
            with client.stream("GET", definition.retrieval_locator) as response:
                response.raise_for_status()
                media_type = response.headers.get("content-type", "")
                total_bytes = 0
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=source_root,
                    prefix=f".{definition.file_name}.",
                    suffix=".download",
                    delete=False,
                ) as stream:
                    temporary_name = stream.name
                    for chunk in response.iter_bytes():
                        total_bytes += len(chunk)
                        if total_bytes > MAXIMUM_SOURCE_BYTES:
                            raise GeographyBuildSecurityError(
                                f"response for {definition.source_id} exceeds "
                                f"{MAXIMUM_SOURCE_BYTES} bytes"
                            )
                        stream.write(chunk)
                    stream.flush()
                    os.fsync(stream.fileno())
        except httpx.HTTPError as exc:
            raise RuntimeError(f"failed to retrieve {definition.source_id}") from exc
        if temporary_name is None:
            raise GeographyBuildSecurityError(
                f"retrieval did not produce a temporary file for {definition.source_id}"
            )
        temporary = _safe_regular_input(Path(temporary_name), "downloaded source")
        _validate_snapshot_payload(definition, temporary.read_bytes(), media_type)
        os.replace(temporary, destination)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
    return SourceRecord(
        source_id=definition.source_id,
        title=definition.title,
        locator=definition.landing_page_locator,
        landing_page_locator=definition.landing_page_locator,
        retrieval_locator=definition.retrieval_locator,
        media_type=media_type.partition(";")[0].strip().lower(),
        snapshot_format=definition.snapshot_format,
        snapshot_file_name=f"sources/{definition.file_name}",
        retrieved_utc=datetime.now(timezone.utc),
        source_tier=definition.source_tier,
        status=definition.status,
        use=definition.use,
        license_name=definition.license_name,
        license_locator=definition.license_locator,
        redistribution_status=definition.redistribution_status,
        sha256=_sha256_file(destination),
        byte_length=destination.stat().st_size,
    )


def _verify_archive_member(
    dem_archive_path: Path,
    dem_raster_path: Path,
    member_name: str,
) -> str:
    archive = _safe_regular_input(dem_archive_path, "DEM archive")
    raster = _safe_regular_input(dem_raster_path, "DEM raster")
    raster_digest = _sha256_file(raster)
    try:
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                member = PurePosixPath(info.filename)
                unix_mode = info.external_attr >> 16
                if member.is_absolute() or ".." in member.parts:
                    raise GeographyBuildSecurityError(f"unsafe DEM archive member: {info.filename}")
                if stat.S_ISLNK(unix_mode):
                    raise GeographyBuildSecurityError(
                        f"DEM archive symlink rejected: {info.filename}"
                    )
            try:
                selected = bundle.getinfo(member_name)
            except KeyError as exc:
                raise GeographyBuildSecurityError(
                    f"declared DEM archive member is absent: {member_name}"
                ) from exc
            if selected.is_dir() or selected.file_size != raster.stat().st_size:
                raise GeographyBuildSecurityError("declared DEM archive member size mismatch")
            digest = hashlib.sha256()
            with bundle.open(selected) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != raster_digest:
                raise GeographyBuildSecurityError("declared DEM archive member digest mismatch")
    except zipfile.BadZipFile as exc:
        raise GeographyBuildSecurityError(f"malformed DEM archive: {archive}") from exc
    return raster_digest


def _dem_records(dem_archive_path: Path, dem_raster_path: Path) -> list[SourceRecord]:
    archive_path = _safe_regular_input(dem_archive_path, "DEM archive")
    raster_path = _safe_regular_input(dem_raster_path, "DEM raster")
    raster_digest = _verify_archive_member(archive_path, raster_path, DEM_ARCHIVE_MEMBER)
    common = {
        "locator": DWR_DEM_ARCHIVE_URL,
        "landing_page_locator": (
            "https://data.cnra.ca.gov/dataset/"
            "san-francisco-bay-and-sacramento-san-joaquin-delta-dem-for-modeling-"
            "version-4-3"
        ),
        "retrieval_locator": DWR_DEM_ARCHIVE_URL,
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
            snapshot_format="zip",
            media_type="application/zip",
            sha256=_sha256_file(archive_path),
            byte_length=archive_path.stat().st_size,
            **common,
        ),
        SourceRecord(
            source_id="dwr-bay-delta-dem-v4.3-delta-10m-raster",
            title="DWR Bay-Delta DEM v4.3 extracted Delta 10 m GeoTIFF",
            snapshot_file_name="upstream:dem_delta_10m_20250312.tif",
            status="verified-extracted-archive-member",
            use="clipped island elevation summaries",
            archive_member=DEM_ARCHIVE_MEMBER,
            archive_member_sha256=raster_digest,
            archive_member_verification="streamed-sha256-equals-extracted-raster",
            extraction_command=DEM_EXTRACTION_COMMAND,
            snapshot_format="geotiff",
            media_type="image/tiff",
            sha256=raster_digest,
            byte_length=raster_path.stat().st_size,
            **common,
        ),
    ]


def _write_manifest(manifest: GeographyBuildManifest, manifest_path: Path) -> str:
    payload = _canonical_json_bytes(manifest.model_dump(mode="json"))
    _atomic_write(manifest_path, payload)
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
    if source_root.is_symlink():
        raise GeographyBuildSecurityError(f"source root must not be a symlink: {source_root}")
    source_root.mkdir(parents=True, exist_ok=True)
    source_records: list[SourceRecord] = []
    if refresh_sources:
        with httpx.Client(
            follow_redirects=True,
            timeout=60.0,
            headers={"User-Agent": "TRACE-Delta-Research/1.0 (reproducible GIS build)"},
        ) as client:
            for definition in GEOGRAPHY_SOURCE_DEFINITIONS:
                if definition.retrieval_locator is None:
                    LOGGER.info(
                        "Retaining project-authored/non-machine snapshot for %s",
                        definition.source_id,
                    )
                    snapshot = _safe_regular_input(
                        source_root / definition.file_name,
                        f"frozen source snapshot {definition.source_id}",
                    )
                    source_records.append(_source_record_from_frozen(definition, snapshot))
                else:
                    source_records.append(_fetch_source(client, definition, source_root))
    else:
        for definition in GEOGRAPHY_SOURCE_DEFINITIONS:
            snapshot = _safe_regular_input(
                source_root / definition.file_name,
                f"frozen source snapshot {definition.source_id}",
            )
            source_records.append(_source_record_from_frozen(definition, snapshot))
    source_records.extend(_dem_records(dem_archive_path, dem_raster_path))
    source_records.sort(key=lambda source: source.source_id)
    manifest = GeographyBuildManifest(
        schema_version="delta-small-geography-build-manifest-v3",
        builder_version=BUILDER_VERSION,
        built_utc=FROZEN_V3_BUILD_UTC,
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
    _validate_source_references(catalog)
    _atomic_write(
        geography_path,
        yaml.safe_dump(catalog.model_dump(mode="json"), sort_keys=False).encode("utf-8"),
    )
    LOGGER.info("Built %s with manifest %s", geography_path, manifest_sha256)
    return catalog


def _validate_source_references(catalog: GeographyCatalog) -> None:
    source_ids = [source.source_id for source in catalog.sources]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("geography source IDs must be unique")
    referenced = {
        *(item.source_id for item in catalog.islands),
        *(item.elevation_summary.source_id for item in catalog.islands),
        *(item.source_id for item in catalog.communities),
        *(item.source_id for item in catalog.crossings),
        *(item.source_id for item in catalog.gauges),
        *(item.source_id for item in catalog.waterways),
        *(item.source_id for item in catalog.governance),
        *(source_id for item in catalog.facilities for source_id in item.source_ids),
    }
    missing = sorted(referenced - set(source_ids))
    if missing:
        raise ValueError(f"geography catalog has unknown source references: {missing}")
