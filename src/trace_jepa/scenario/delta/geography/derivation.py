"""Deterministic derivation and spatial QA for the runtime geography fixture."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol, cast

import numpy as np
import rasterio
from numpy.typing import NDArray
from pyproj import Transformer
from rasterio.mask import mask
from shapely import transform
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from trace_jepa.scenario.delta.geography.models import (
    Community,
    Crossing,
    ElevationSummary,
    Facility,
    FixedCoordinate,
    Gauge,
    GeographyCatalog,
    GovernanceEntity,
    Island,
    LinearRing,
    LineGeometry,
    PolygonGeometry,
    SourceRecord,
    Waterway,
)


class _CompressibleRasterBand(Protocol):
    """Typed surface guaranteed by rasterio.mask when ``filled=False``."""

    def compressed(self) -> NDArray[Any]: ...


SIMPLIFICATION_TOLERANCE_M = 10.0
ACRES_PER_SQUARE_METER = 1.0 / 4046.8564224


def _load_json_object(path: Path) -> object:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _features(path: Path) -> list[Mapping[str, object]]:
    payload = _load_json_object(path)
    if not isinstance(payload, Mapping):
        raise TypeError(f"expected GeoJSON object in {path}")
    value = payload.get("features")
    if not isinstance(value, Sequence):
        raise TypeError(f"GeoJSON features missing from {path}")
    features: list[Mapping[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise TypeError(f"invalid GeoJSON feature in {path}")
        features.append(item)
    return features


def _properties(feature: Mapping[str, object]) -> Mapping[str, object]:
    value = feature.get("properties")
    if not isinstance(value, Mapping):
        raise TypeError("GeoJSON feature is missing properties")
    return value


def _property_text(feature: Mapping[str, object], names: list[str]) -> str:
    properties = _properties(feature)
    for name in names:
        value = properties.get(name)
        if isinstance(value, (str, int, float)):
            return str(value)
    raise ValueError(f"feature properties {names!r} are missing")


def _select_feature(
    features: list[Mapping[str, object]],
    property_names: list[str],
    expected_value: str,
) -> Mapping[str, object]:
    matches = [
        feature for feature in features if _property_text(feature, property_names) == expected_value
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one {property_names}={expected_value!r}, found {len(matches)}")
    return matches[0]


def _feature_geometry(feature: Mapping[str, object]) -> BaseGeometry:
    value = feature.get("geometry")
    if not isinstance(value, Mapping):
        raise TypeError("GeoJSON feature is missing geometry")
    return shape(value)


def _fixed_coordinate(
    longitude: float,
    latitude: float,
    to_utm: Transformer,
) -> FixedCoordinate:
    easting_m, northing_m = to_utm.transform(longitude, latitude)
    return FixedCoordinate(
        longitude_e7=round(longitude * 10_000_000),
        latitude_e7=round(latitude * 10_000_000),
        easting_mm=round(easting_m * 1000),
        northing_mm=round(northing_m * 1000),
    )


def _polygon_geometry(
    source_geometry: BaseGeometry,
    to_utm: Transformer,
    to_wgs84: Transformer,
) -> PolygonGeometry:
    projected = transform(source_geometry, to_utm.transform, interleaved=False)
    repaired = projected if projected.is_valid else projected.buffer(0)
    simplified = repaired.simplify(SIMPLIFICATION_TOLERANCE_M, preserve_topology=True)
    wgs84 = transform(simplified, to_wgs84.transform, interleaved=False)
    if isinstance(wgs84, Polygon):
        polygons = [wgs84]
    elif isinstance(wgs84, MultiPolygon):
        polygons = sorted(wgs84.geoms, key=lambda polygon: polygon.area, reverse=True)
    else:
        raise TypeError(f"expected polygon geometry, received {wgs84.geom_type}")
    return PolygonGeometry(
        polygons=[
            LinearRing(
                points=[
                    _fixed_coordinate(float(longitude), float(latitude), to_utm)
                    for longitude, latitude in polygon.exterior.coords
                ]
            )
            for polygon in polygons
        ]
    )


def _line_segments(
    geometry: BaseGeometry,
    to_utm: Transformer,
    to_wgs84: Transformer,
) -> list[LineGeometry]:
    projected = transform(geometry, to_utm.transform, interleaved=False)
    simplified = projected.simplify(SIMPLIFICATION_TOLERANCE_M, preserve_topology=True)
    wgs84 = transform(simplified, to_wgs84.transform, interleaved=False)
    if isinstance(wgs84, LineString):
        lines = [wgs84]
    elif isinstance(wgs84, MultiLineString):
        lines = list(wgs84.geoms)
    else:
        raise TypeError(f"expected line geometry, received {wgs84.geom_type}")
    return [
        LineGeometry(
            points=[
                _fixed_coordinate(float(longitude), float(latitude), to_utm)
                for longitude, latitude in line.coords
            ]
        )
        for line in lines
    ]


def _source_area_acres(geometry_wgs84: BaseGeometry, to_utm: Transformer) -> int:
    projected = transform(geometry_wgs84, to_utm.transform, interleaved=False)
    return cast(int, round(projected.area * ACRES_PER_SQUARE_METER))


def _elevation_summary(
    geometry_wgs84: BaseGeometry,
    raster_path: Path,
    to_utm: Transformer,
) -> ElevationSummary:
    geometry_utm = transform(geometry_wgs84, to_utm.transform, interleaved=False)
    with rasterio.open(raster_path) as dataset:
        values, _ = mask(dataset, [geometry_utm.__geo_interface__], crop=True, filled=False)
    compressed = cast(_CompressibleRasterBand, values[0]).compressed()
    if compressed.size == 0:
        raise ValueError("DWR DEM has no valid cells within island geometry")
    return ElevationSummary(
        vertical_datum="NAVD88",
        valid_cell_count=int(compressed.size),
        minimum_mm=round(float(np.min(compressed)) * 1000),
        median_mm=round(float(np.median(compressed)) * 1000),
        maximum_mm=round(float(np.max(compressed)) * 1000),
        source_id="dwr-bay-delta-dem-v4.3-delta-10m-raster",
    )


def _read_fire_coordinate(path: Path, to_utm: Transformer) -> FixedCoordinate:
    payload = _load_json_object(path)
    if not isinstance(payload, Sequence) or len(payload) != 1:
        raise ValueError("expected one Nominatim fire-station match")
    item = payload[0]
    if not isinstance(item, Mapping):
        raise TypeError("invalid Nominatim fire-station response")
    longitude = item.get("lon")
    latitude = item.get("lat")
    if not isinstance(longitude, str) or not isinstance(latitude, str):
        raise TypeError("Nominatim response is missing coordinates")
    return _fixed_coordinate(float(longitude), float(latitude), to_utm)


def _validate_official_facility_records(source_root: Path) -> None:
    fire_record = _load_json_object(source_root / "isleton_fire_department_record.json")
    if not isinstance(fire_record, Mapping):
        raise TypeError("invalid project-authored Isleton fire factual extract")
    fire_facts = fire_record.get("facts")
    if not isinstance(fire_facts, Mapping):
        raise TypeError("Isleton fire factual extract is missing facts")
    apparatus = fire_facts.get("apparatus_classes")
    if not isinstance(apparatus, Sequence) or not {
        "Type 1 Engine",
        "25 Foot Defender Series Safe Boat",
    }.issubset(apparatus):
        raise ValueError("official Isleton fire record no longer confirms required assets")
    dbw_record = _load_json_object(source_root / "dbw_sacramento_boating_facilities_record.json")
    if not isinstance(dbw_record, Mapping):
        raise TypeError("invalid project-authored DBW factual extract")
    dbw_facts = dbw_record.get("facts")
    if not isinstance(dbw_facts, Mapping) or (
        dbw_facts.get("facility_name"),
        dbw_facts.get("facility_type"),
    ) != ("Brannan Island SRA", "Marina/Launch"):
        raise ValueError("official DBW record no longer confirms Brannan launch capability")


def _waterways(
    source_root: Path,
    to_utm: Transformer,
    to_wgs84: Transformer,
) -> list[Waterway]:
    features = _features(source_root / "usgs_nhd_flowlines.geojson")
    names = {
        "Sacramento River": "WTR-SAC",
        "Threemile Slough": "WTR-TMS",
        "Three Mile Slough": "WTR-TMS",
        "Georgiana Slough": "WTR-GEO",
    }
    waterways: list[Waterway] = []
    for canonical_name, waterway_id in [
        ("Sacramento River", "WTR-SAC"),
        ("Threemile Slough", "WTR-TMS"),
        ("Georgiana Slough", "WTR-GEO"),
    ]:
        matching = [
            feature
            for feature in features
            if names.get(_property_text(feature, ["GNIS_NAME", "GNIS_Name", "gnis_name"]))
            == waterway_id
        ]
        if not matching:
            raise ValueError(f"USGS NHD snapshot lacks {canonical_name}")
        segments = [
            segment
            for feature in matching
            for segment in _line_segments(_feature_geometry(feature), to_utm, to_wgs84)
        ]
        waterways.append(
            Waterway(
                waterway_id=waterway_id,
                name=canonical_name,
                segments=segments,
                source_id="usgs-nhd-flowlines-2026-08-05",
            )
        )
    return waterways


def build_geography_catalog(
    source_root: Path,
    dem_raster_path: Path,
    manifest_sha256: str,
    source_records: list[SourceRecord],
) -> GeographyCatalog:
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:26910", always_xy=True)
    to_wgs84 = Transformer.from_crs("EPSG:26910", "EPSG:4326", always_xy=True)
    district_features = _features(source_root / "sacramento_county_drainage_districts.geojson")
    andrus_feature = _select_feature(district_features, ["DISTRICT"], "Andrus Island 407")
    lower_andrus_feature = _select_feature(
        district_features, ["DISTRICT"], "Lower Andrus Island 317"
    )
    upper_andrus_feature = _select_feature(
        district_features, ["DISTRICT"], "Upper Andrus Island 556"
    )
    brannan_feature = _select_feature(district_features, ["DISTRICT"], "Brannan Island 2067")
    andrus_geometry = unary_union(
        [
            _feature_geometry(andrus_feature),
            _feature_geometry(lower_andrus_feature),
            _feature_geometry(upper_andrus_feature),
        ]
    )
    brannan_geometry = _feature_geometry(brannan_feature)
    census_feature = _features(source_root / "census_tiger_isleton.geojson")[0]
    census_geometry = _feature_geometry(census_feature)
    bridge_features = _features(source_root / "caltrans_state_highway_bridges.geojson")
    xng03_feature = _select_feature(bridge_features, ["OBJECTID"], "2286")
    xng04_feature = _select_feature(bridge_features, ["OBJECTID"], "2255")
    park_geometry = _feature_geometry(_features(source_root / "state_parks_brannan.geojson")[0])
    _validate_official_facility_records(source_root)
    dwr_metadata = _load_json_object(source_root / "dwr_local_maintenance_areas_metadata.json")
    if not isinstance(dwr_metadata, Mapping):
        raise TypeError("DWR LMA metadata is not a JSON object")
    dwr_description = dwr_metadata.get("description")
    if not isinstance(dwr_description, str) or "flood" not in dwr_description.lower():
        raise ValueError("DWR LMA metadata does not describe flood management boundaries")
    return GeographyCatalog(
        schema_version="delta-small-geography-v3",
        coordinate_reference="EPSG:4326+EPSG:26910-fixed-point-v1",
        coordinate_warning=(
            "Government GIS anchors are simulation-grade and preserve source boundary "
            "limitations; they are not cadastral, survey, emergency-navigation, or "
            "hydraulic-model geometries."
        ),
        build_manifest_sha256=manifest_sha256,
        sources=source_records,
        islands=[
            Island(
                island_id="ISL-01",
                name="Andrus Island",
                scenario_acres=7600,
                source_area_acres=_source_area_acres(andrus_geometry, to_utm),
                interior_elevation_millifeet_msl=-5000,
                centroid=_fixed_coordinate(
                    andrus_geometry.centroid.x, andrus_geometry.centroid.y, to_utm
                ),
                geometry=_polygon_geometry(andrus_geometry, to_utm, to_wgs84),
                geometry_status="operational-drainage-district-footprint",
                elevation_summary=_elevation_summary(andrus_geometry, dem_raster_path, to_utm),
                source_id="sacramento-county-drainage-districts-2026-08-05",
            ),
            Island(
                island_id="ISL-02",
                name="Brannan Island",
                scenario_acres=8600,
                source_area_acres=_source_area_acres(brannan_geometry, to_utm),
                interior_elevation_millifeet_msl=-8000,
                centroid=_fixed_coordinate(
                    brannan_geometry.centroid.x, brannan_geometry.centroid.y, to_utm
                ),
                geometry=_polygon_geometry(brannan_geometry, to_utm, to_wgs84),
                geometry_status="operational-drainage-district-footprint",
                elevation_summary=_elevation_summary(brannan_geometry, dem_raster_path, to_utm),
                source_id="sacramento-county-drainage-districts-2026-08-05",
            ),
        ],
        communities=[
            Community(
                community_id="TWN-01",
                name="Isleton",
                island_id="ISL-01",
                census_geoid=_property_text(census_feature, ["GEOID"]),
                centroid=_fixed_coordinate(
                    census_geometry.centroid.x, census_geometry.centroid.y, to_utm
                ),
                geometry=_polygon_geometry(census_geometry, to_utm, to_wgs84),
                source_id="census-tiger-isleton-2025",
            )
        ],
        crossings=[
            _crossing(
                xng03_feature,
                "XNG-03",
                "Three Mile Slough Bridge",
                "movable_lift_bridge",
                1800,
                to_utm,
            ),
            _crossing(
                xng04_feature,
                "XNG-04",
                "Isleton Bridge",
                "movable_bascule_bridge",
                900,
                to_utm,
            ),
        ],
        gauges=_gauges(to_utm),
        waterways=_waterways(source_root, to_utm, to_wgs84),
        facilities=[
            Facility(
                facility_id="FAC-FIRE-01",
                name="Isleton Fire Department",
                facility_type="local_fire_and_rescue_base",
                location=_read_fire_coordinate(
                    source_root / "osm_isleton_fire_geocode.json", to_utm
                ),
                location_precision="secondary-address-geocode",
                operational_for_routing=True,
                source_ids=[
                    "isleton-fire-department-2026-08-05",
                    "osm-isleton-fire-geocode-2026-08-05",
                ],
            ),
            Facility(
                facility_id="FAC-RAMP-01",
                name="Brannan Island State Recreation Area launch",
                facility_type="boat_launch",
                location=_fixed_coordinate(
                    park_geometry.centroid.x, park_geometry.centroid.y, to_utm
                ),
                location_precision="state-park-unit-centroid-not-ramp-survey",
                operational_for_routing=False,
                source_ids=[
                    "california-state-parks-brannan-2026-08-05",
                    "california-dbw-sacramento-facilities-2026-08-05",
                ],
            ),
        ],
        governance=[
            GovernanceEntity(
                governance_id="GOV-RD-407",
                name="Andrus Island Reclamation District 407",
                governance_type="reclamation_district",
                island_ids=["ISL-01"],
                source_feature_id=_property_text(andrus_feature, ["OBJECTID", "FID"]),
                source_id="sacramento-county-drainage-districts-2026-08-05",
            ),
            GovernanceEntity(
                governance_id="GOV-RD-317",
                name="Lower Andrus Island Reclamation District 317",
                governance_type="reclamation_district",
                island_ids=["ISL-01"],
                source_feature_id=_property_text(lower_andrus_feature, ["OBJECTID", "FID"]),
                source_id="sacramento-county-drainage-districts-2026-08-05",
            ),
            GovernanceEntity(
                governance_id="GOV-RD-556",
                name="Upper Andrus Island Reclamation District 556",
                governance_type="reclamation_district",
                island_ids=["ISL-01"],
                source_feature_id=_property_text(upper_andrus_feature, ["OBJECTID", "FID"]),
                source_id="sacramento-county-drainage-districts-2026-08-05",
            ),
            GovernanceEntity(
                governance_id="GOV-RD-2067",
                name="Brannan Island Reclamation District 2067",
                governance_type="reclamation_district",
                island_ids=["ISL-02"],
                source_feature_id=_property_text(brannan_feature, ["OBJECTID", "FID"]),
                source_id="sacramento-county-drainage-districts-2026-08-05",
            ),
        ],
    )


def _crossing(
    feature: Mapping[str, object],
    crossing_id: str,
    name: str,
    crossing_type: str,
    nominal_travel_s: int,
    to_utm: Transformer,
) -> Crossing:
    geometry = _feature_geometry(feature)
    return Crossing(
        crossing_id=crossing_id,
        name=name,
        carries="SR-160",
        crossing_type=crossing_type,
        design_description=_property_text(feature, ["DESIGN_MAIN"]),
        source_feature_id=_property_text(feature, ["OBJECTID"]),
        location=_fixed_coordinate(geometry.x, geometry.y, to_utm),
        nominal_travel_s=nominal_travel_s,
        source_id="caltrans-state-highway-bridges-2024",
    )


def _gauges(to_utm: Transformer) -> list[Gauge]:
    return [
        Gauge(
            gauge_id="RVB",
            name="Sacramento River at Rio Vista Bridge",
            location=_fixed_coordinate(-121.686355, 38.159737, to_utm),
            baseline_stage_millifeet=3200,
            action_stage_millifeet=7400,
            minor_flood_stage_millifeet=11900,
            threshold_status="verified-cdec-2026-08-05",
            source_id="cdec-rvb-metadata-2026-08-05",
        ),
        Gauge(
            gauge_id="MRU",
            name="Middle River at Undine Road",
            location=_fixed_coordinate(-121.386000, 37.833900, to_utm),
            baseline_stage_millifeet=3400,
            action_stage_millifeet=-1,
            minor_flood_stage_millifeet=-1,
            threshold_status="unavailable-non-operative",
            source_id="cdec-mru-metadata-2026-08-05",
        ),
        Gauge(
            gauge_id="FPT",
            name="Sacramento River at Freeport",
            location=_fixed_coordinate(-121.500300, 38.456112, to_utm),
            baseline_stage_millifeet=4000,
            action_stage_millifeet=-1,
            minor_flood_stage_millifeet=-1,
            threshold_status="unavailable-non-operative",
            source_id="cdec-fpt-metadata-2026-08-05",
        ),
    ]
