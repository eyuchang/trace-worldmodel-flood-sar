"""Deterministically derive the offline Reference geography catalog."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from pyproj import Transformer
from shapely import make_valid, union_all
from shapely.geometry import MultiPoint, MultiPolygon, Point, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from trace_jepa.support import (
    ArtifactLocator,
    atomic_write_bytes,
    canonical_json_bytes,
    sha256_file,
)

from .catalog_models import (
    MultiPolygonE6,
    ReferenceBoundary,
    ReferenceCommunity,
    ReferenceCrossing,
    ReferenceGeographyBuildManifest,
    ReferenceGeographyCatalog,
    ReferenceIsland,
    ReferenceMetricPoint,
    ReferenceRouteEdge,
    ReferenceRouteNode,
    ReferenceSourceBinding,
    ReferenceSourceRecord,
)

SOURCE_RELATIVE_NAMES = {
    "REF-GEO-SRC-01": "dwr_lma_target_v1.geojson",
    "REF-GEO-SRC-02": "sacramento_county_andrus_brannan_v1.geojson",
    "REF-GEO-SRC-03": "census_incorporated_places_v1.geojson",
    "REF-GEO-SRC-04": "census_designated_places_v1.geojson",
    "REF-GEO-SRC-05": "usgs_gnis_communities_v1.geojson",
    "REF-GEO-SRC-06": "caltrans_state_crossings_v1.geojson",
    "REF-GEO-SRC-07": "caltrans_local_crossings_v1.geojson",
    "REF-GEO-SRC-08": "usgs_gnis_woodward_crossing_v1.geojson",
}

_TO_METRIC = Transformer.from_crs(4326, 26910, always_xy=True)


def _load_geojson(root: Path, relative_name: str, expected_sha256: str) -> dict[str, Any]:
    path = ArtifactLocator(
        root=root,
        relative_name=Path(relative_name),
        maximum_bytes=25_000_000,
        label=f"Reference geography source {relative_name}",
    ).resolve()
    if sha256_file(path) != expected_sha256:
        raise ValueError(f"Reference geography source digest mismatch: {relative_name}")
    try:
        payload = json.loads(path.read_text("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid Reference GeoJSON: {relative_name}") from exc
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError(f"Reference source is not a FeatureCollection: {relative_name}")
    if not isinstance(payload.get("features"), list):
        raise TypeError(f"Reference source has no feature array: {relative_name}")
    return payload


def _properties(feature: Mapping[str, Any]) -> Mapping[str, Any]:
    value = feature.get("properties")
    if not isinstance(value, Mapping):
        raise TypeError("Reference feature properties must be an object")
    return value


def _feature_by_integer(payload: Mapping[str, Any], field: str, value: int) -> Mapping[str, Any]:
    matches = [item for item in payload["features"] if int(_properties(item)[field]) == value]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {field}={value} feature")
    return cast(Mapping[str, Any], matches[0])


def _features_by_integer(
    payload: Mapping[str, Any], field: str, values: Sequence[int]
) -> tuple[Mapping[str, Any], ...]:
    return tuple(_feature_by_integer(payload, field, value) for value in values)


def _feature_geometry(feature: Mapping[str, Any]) -> BaseGeometry:
    value = feature.get("geometry")
    if not isinstance(value, Mapping):
        raise TypeError("Reference feature geometry must be an object")
    geometry = shape(value)
    if geometry.is_empty:
        raise ValueError("Reference feature geometry is empty")
    return geometry


def _valid_polygonal(geometry: BaseGeometry) -> tuple[MultiPolygon, str]:
    status = "unchanged-valid"
    if not geometry.is_valid:
        geometry = make_valid(geometry)
        status = "repaired-with-make-valid"
    polygons: list[Polygon] = []
    if isinstance(geometry, Polygon):
        polygons = [geometry]
    elif isinstance(geometry, MultiPolygon):
        polygons = list(geometry.geoms)
    else:
        polygons = [item for item in getattr(geometry, "geoms", ()) if isinstance(item, Polygon)]
    if not polygons:
        raise ValueError("Reference boundary has no polygonal component")
    result = MultiPolygon(polygons)
    if not result.is_valid:
        raise ValueError("Reference boundary remains invalid after repair")
    return result, status


def _quantized_geometry(geometry: MultiPolygon) -> MultiPolygonE6:
    def ring(values: Iterable[Sequence[float]]) -> tuple[tuple[int, int], ...]:
        return tuple((round(float(x) * 1_000_000), round(float(y) * 1_000_000)) for x, y in values)

    return tuple(
        (ring(polygon.exterior.coords), *(ring(item.coords) for item in polygon.interiors))
        for polygon in geometry.geoms
    )


def _metric_point(point: Point) -> ReferenceMetricPoint:
    easting, northing = _TO_METRIC.transform(point.x, point.y)
    return ReferenceMetricPoint(
        longitude_e6=round(point.x * 1_000_000),
        latitude_e6=round(point.y * 1_000_000),
        easting_mm_epsg26910=round(easting * 1_000),
        northing_mm_epsg26910=round(northing * 1_000),
    )


def _boundary(geometry: BaseGeometry) -> tuple[ReferenceBoundary, ReferenceMetricPoint]:
    valid, repair_status = _valid_polygonal(geometry)
    metric = transform(_TO_METRIC.transform, valid)
    return (
        ReferenceBoundary(
            polygons_e6=_quantized_geometry(valid),
            area_m2_epsg26910=round(metric.area),
            repair_status=repair_status,
        ),
        _metric_point(valid.representative_point()),
    )


def _source_binding(source_id: str, identifiers: Sequence[str], use: str) -> ReferenceSourceBinding:
    return ReferenceSourceBinding(
        source_id=source_id,
        feature_identifiers=tuple(identifiers),
        use=use,
    )


def _build_islands(sources: Mapping[str, dict[str, Any]]) -> tuple[ReferenceIsland, ...]:
    dwr = sources["REF-GEO-SRC-01"]
    county = sources["REF-GEO-SRC-02"]
    county_andrus = union_all(
        [_feature_geometry(item) for item in _features_by_integer(county, "OBJECTID", (19, 22, 23))]
    )
    definitions = (
        (
            "ISL-01",
            "Andrus Island",
            county_andrus,
            (
                _source_binding(
                    "REF-GEO-SRC-02",
                    ("OBJECTID:19", "OBJECTID:22", "OBJECTID:23"),
                    "primary-boundary",
                ),
                _source_binding("REF-GEO-SRC-01", ("OBJECTID:79", "OBJECTID:259"), "cross-check"),
            ),
            "union-of-county-reclamation-district-footprints",
        ),
        (
            "ISL-02",
            "Brannan Island",
            _feature_geometry(_feature_by_integer(county, "OBJECTID", 24)),
            (
                _source_binding("REF-GEO-SRC-02", ("OBJECTID:24",), "primary-boundary"),
                _source_binding("REF-GEO-SRC-01", ("OBJECTID:259",), "cross-check"),
            ),
            "union-of-county-reclamation-district-footprints",
        ),
        *tuple(
            (
                island_id,
                name,
                _feature_geometry(_feature_by_integer(dwr, "OBJECTID", object_id)),
                (
                    _source_binding(
                        "REF-GEO-SRC-01", (f"OBJECTID:{object_id}",), "primary-boundary"
                    ),
                ),
                "dwr-local-maintenance-area-footprint",
            )
            for island_id, name, object_id in (
                ("ISL-03", "Twitchell Island", 96),
                ("ISL-04", "Sherman Island", 11),
                ("ISL-05", "Tyler Island", 20),
                ("ISL-06", "Grand Island", 12),
                ("ISL-07", "Staten Island", 81),
                ("ISL-08", "Bouldin Island", 23),
            )
        ),
    )
    result: list[ReferenceIsland] = []
    for island_id, name, geometry, bindings, semantics in definitions:
        boundary, anchor = _boundary(geometry)
        result.append(
            ReferenceIsland(
                island_id=island_id,
                name=name,
                boundary=boundary,
                anchor=anchor,
                source_bindings=bindings,
                boundary_semantics=semantics,
                limitation=(
                    "Operational maintenance footprints are simulation-grade proxies for island "
                    "exposure and are not parcel, cadastral, survey, or navigation boundaries."
                ),
            )
        )
    return tuple(result)


def _feature_by_name(payload: Mapping[str, Any], field: str, name: str) -> Mapping[str, Any]:
    matches = [item for item in payload["features"] if _properties(item).get(field) == name]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {field}={name!r} feature")
    return cast(Mapping[str, Any], matches[0])


def _point_from_geometry(geometry: BaseGeometry) -> Point:
    if isinstance(geometry, Point):
        return geometry
    if isinstance(geometry, MultiPoint):
        return geometry.centroid
    return geometry.representative_point()


def _build_communities(sources: Mapping[str, dict[str, Any]]) -> tuple[ReferenceCommunity, ...]:
    incorporated = _feature_by_name(sources["REF-GEO-SRC-03"], "NAME", "Isleton city")
    cdp = _feature_by_name(sources["REF-GEO-SRC-04"], "NAME", "Walnut Grove CDP")
    definitions = (
        ("TWN-01", "Isleton", incorporated, "REF-GEO-SRC-03", "PLACE:36882"),
        ("TWN-02", "Walnut Grove", cdp, "REF-GEO-SRC-04", "PLACE:83374"),
    )
    communities: list[ReferenceCommunity] = []
    for community_id, name, feature, source_id, identifier in definitions:
        boundary, anchor = _boundary(_feature_geometry(feature))
        communities.append(
            ReferenceCommunity(
                community_id=community_id,
                name=name,
                anchor=anchor,
                boundary=boundary,
                geometry_semantics="census-administrative-boundary-not-exposure-footprint",
                source_bindings=(_source_binding(source_id, (identifier,), "primary-boundary"),),
                limitation="The administrative boundary is used only to anchor synthetic exposure.",
            )
        )
    gnis = sources["REF-GEO-SRC-05"]
    for community_id, name, identifier in (
        ("TWN-03", "Locke", "gaz_id:1656136"),
        ("TWN-04", "Ryde", "gaz_id:252785"),
    ):
        feature = _feature_by_name(gnis, "gaz_name", name)
        communities.append(
            ReferenceCommunity(
                community_id=community_id,
                name=name,
                anchor=_metric_point(_point_from_geometry(_feature_geometry(feature))),
                boundary=None,
                geometry_semantics="gnis-official-point-no-boundary",
                source_bindings=(
                    _source_binding("REF-GEO-SRC-05", (identifier,), "identity-point"),
                ),
                limitation=(
                    "GNIS supplies an identity/location point, not a community or exposure boundary; "
                    "any later synthetic exposure footprint must be separately versioned."
                ),
            )
        )
    return tuple(communities)


def _build_crossings(sources: Mapping[str, dict[str, Any]]) -> tuple[ReferenceCrossing, ...]:
    definitions = (
        (
            "XNG-01",
            "Rio Vista Bridge",
            "REF-GEO-SRC-06",
            2061,
            "movable-lift",
            "exposure-network",
            "official-inventory-verified",
        ),
        (
            "XNG-02",
            "Antioch Bridge",
            "REF-GEO-SRC-06",
            2717,
            "fixed-bridge",
            "boundary-connector",
            "official-inventory-verified",
        ),
        (
            "XNG-03",
            "Threemile Slough Bridge",
            "REF-GEO-SRC-06",
            2286,
            "movable-lift",
            "exposure-network",
            "official-inventory-verified",
        ),
        (
            "XNG-04",
            "Isleton Bridge",
            "REF-GEO-SRC-06",
            2255,
            "movable-bascule",
            "exposure-network",
            "official-inventory-verified",
        ),
        (
            "XNG-05",
            "Walnut Grove Bridge",
            "REF-GEO-SRC-07",
            29344,
            "movable-bascule",
            "exposure-network",
            "official-inventory-verified",
        ),
        (
            "XNG-06",
            "Paintersville Bridge",
            "REF-GEO-SRC-06",
            2257,
            "movable-bascule",
            "boundary-connector",
            "official-inventory-verified",
        ),
        (
            "XNG-07",
            "Bethel Island Bridge",
            "REF-GEO-SRC-07",
            30337,
            "fixed-bridge",
            "boundary-connector",
            "official-inventory-verified",
        ),
        (
            "XNG-08",
            "Real McCoy Ferry",
            "REF-GEO-SRC-06",
            2212,
            "hydraulic-ferry",
            "boundary-connector",
            "official-inventory-verified",
        ),
        (
            "XNG-09",
            "J-Mack Ferry",
            "REF-GEO-SRC-06",
            2070,
            "cable-ferry",
            "boundary-connector",
            "official-inventory-verified",
        ),
        (
            "XNG-10",
            "Woodward Island Crossing",
            "REF-GEO-SRC-08",
            1193,
            "crossing-type-unresolved",
            "boundary-connector",
            "official-identity-current-type-unresolved",
        ),
    )
    crossings: list[ReferenceCrossing] = []
    for crossing_id, name, source_id, object_id, crossing_type, role, evidence in definitions:
        feature = _feature_by_integer(sources[source_id], "OBJECTID", object_id)
        crossings.append(
            ReferenceCrossing(
                crossing_id=crossing_id,
                name=name,
                anchor=_metric_point(_point_from_geometry(_feature_geometry(feature))),
                crossing_type=crossing_type,
                source_bindings=(
                    _source_binding(source_id, (f"OBJECTID:{object_id}",), "crossing-point"),
                ),
                evidence_status=evidence,
                topology_role=role,
                limitation=(
                    "Inventory coordinates anchor simulation topology only; they are not survey control, "
                    "current operability, clearance, or emergency-routing evidence."
                ),
            )
        )
    return tuple(crossings)


def _distance_m(left: ReferenceMetricPoint, right: ReferenceMetricPoint) -> int:
    return max(
        1,
        round(
            math.hypot(
                left.easting_mm_epsg26910 - right.easting_mm_epsg26910,
                left.northing_mm_epsg26910 - right.northing_mm_epsg26910,
            )
            / 1_000
        ),
    )


def _build_routes(
    islands: Sequence[ReferenceIsland], crossings: Sequence[ReferenceCrossing]
) -> tuple[tuple[ReferenceRouteNode, ...], tuple[ReferenceRouteEdge, ...]]:
    island_points = {item.island_id: item.anchor for item in islands}
    crossing_points = {item.crossing_id: item.anchor for item in crossings}
    boundary_anchors = {
        "BND-RIO-VISTA": crossing_points["XNG-01"],
        "BND-ANTIOCH": crossing_points["XNG-02"],
        "BND-WALNUT": crossing_points["XNG-05"],
        "BND-NORTH": crossing_points["XNG-06"],
        "BND-BETHEL": crossing_points["XNG-07"],
        "BND-RYER": crossing_points["XNG-09"],
        "BND-WOODWARD": crossing_points["XNG-10"],
    }
    nodes = tuple(
        ReferenceRouteNode(node_id=item.island_id, anchor=item.anchor, exposure_node=True)
        for item in islands
    ) + tuple(
        ReferenceRouteNode(node_id=node_id, anchor=anchor, exposure_node=False)
        for node_id, anchor in sorted(boundary_anchors.items())
    )
    node_points = {item.node_id: item.anchor for item in nodes}
    endpoints = {
        "XNG-01": ("BND-RIO-VISTA", "ISL-02"),
        "XNG-02": ("BND-ANTIOCH", "ISL-04"),
        "XNG-03": ("ISL-02", "ISL-04"),
        "XNG-04": ("ISL-01", "ISL-02"),
        "XNG-05": ("ISL-06", "BND-WALNUT"),
        "XNG-06": ("ISL-06", "BND-NORTH"),
        "XNG-07": ("BND-BETHEL", "BND-ANTIOCH"),
        "XNG-08": ("BND-RYER", "BND-RIO-VISTA"),
        "XNG-09": ("ISL-06", "BND-RYER"),
        "XNG-10": ("BND-WOODWARD", "BND-ANTIOCH"),
    }
    road_edges = tuple(
        ReferenceRouteEdge(
            edge_id=crossing_id,
            from_node_id=left,
            to_node_id=right,
            mode="road-crossing",
            crossing_id=crossing_id,
            length_m=max(
                100,
                _distance_m(crossing_points[crossing_id], node_points[left])
                + _distance_m(crossing_points[crossing_id], node_points[right]),
            ),
            provenance="official-crossing-point-with-protocol-endpoints",
            operative_claim="simulation-topology-only",
        )
        for crossing_id, (left, right) in endpoints.items()
    )
    water_pairs = (
        ("ISL-01", "ISL-03"),
        ("ISL-03", "ISL-05"),
        ("ISL-05", "ISL-06"),
        ("ISL-06", "ISL-07"),
        ("ISL-07", "ISL-08"),
        ("ISL-08", "ISL-04"),
        ("ISL-04", "ISL-02"),
    )
    water_edges = tuple(
        ReferenceRouteEdge(
            edge_id=f"WTR-{index:02d}",
            from_node_id=left,
            to_node_id=right,
            mode="water-transfer",
            crossing_id=None,
            length_m=_distance_m(island_points[left], island_points[right]),
            provenance="source-anchor-derived-simulation-water-link",
            operative_claim="simulation-topology-only",
        )
        for index, (left, right) in enumerate(water_pairs, start=1)
    )
    return nodes, road_edges + water_edges


def _source_records(
    source_metadata: Sequence[Mapping[str, Any]], source_root: Path
) -> tuple[ReferenceSourceRecord, ...]:
    records: list[ReferenceSourceRecord] = []
    for raw in source_metadata:
        source_id = str(raw["source_id"])
        relative_name = SOURCE_RELATIVE_NAMES[source_id]
        records.append(
            ReferenceSourceRecord(
                source_id=source_id,
                agency=raw["agency"],
                dataset_title=raw["dataset_title"],
                landing_page_url=raw["landing_page_url"],
                machine_readable_url=raw["machine_readable_url"],
                retrieved_at_utc=raw["retrieved_at_utc"],
                upstream_response_sha256=raw["upstream_response_sha256"],
                committed_snapshot_relative_path=relative_name,
                committed_snapshot_sha256=sha256_file(source_root / relative_name),
                license_name=raw["license_name"],
                license_locator=raw["license_locator"],
                redistribution_status=raw["redistribution_status"],
                attribution=raw["attribution"],
                limitations=tuple(raw["limitations"]),
            )
        )
    return tuple(records)


def build_reference_geography(
    *,
    source_root: Path,
    source_metadata: Sequence[Mapping[str, Any]],
    output_root: Path,
) -> ReferenceGeographyBuildManifest:
    """Build and write a deterministic catalog from exact offline snapshots."""

    records = _source_records(source_metadata, source_root)
    expected = {item.source_id: item.committed_snapshot_sha256 for item in records}
    sources = {
        source_id: _load_geojson(source_root, relative_name, expected[source_id])
        for source_id, relative_name in SOURCE_RELATIVE_NAMES.items()
    }
    islands = _build_islands(sources)
    communities = _build_communities(sources)
    crossings = _build_crossings(sources)
    nodes, edges = _build_routes(islands, crossings)
    catalog = ReferenceGeographyCatalog(
        catalog_version="delta-reference-geography-v1",
        scientific_status="simulation-grade-curated-from-authoritative-sources",
        source_crs="EPSG:4326",
        metric_crs="EPSG:26910",
        coordinate_quantization="wgs84-microdegrees-and-epsg26910-millimetres",
        runtime_network_access="forbidden",
        sources=records,
        islands=islands,
        communities=communities,
        crossings=crossings,
        route_nodes=nodes,
        route_edges=edges,
        limitations=(
            "The catalog supports a synthetic reduced-order simulator, not navigation or field dispatch.",
            "Maintenance-area boundaries proxy island footprints and do not establish parcel ownership.",
            "Road and water graph endpoints are protocol design assumptions anchored by official points.",
            "The current Woodward crossing type and operability remain unresolved and non-operative facts.",
        ),
    )
    catalog_name = "reference_geography_catalog_v1.json"
    catalog_bytes = canonical_json_bytes(catalog.model_dump(mode="json"))
    atomic_write_bytes(
        output_root / catalog_name,
        catalog_bytes,
        root=output_root,
        label="Reference geography catalog",
    )
    manifest = ReferenceGeographyBuildManifest(
        manifest_version="delta-reference-geography-build-v1",
        catalog_relative_path=catalog_name,
        catalog_sha256=hashlib.sha256(catalog_bytes).hexdigest(),
        source_snapshot_sha256=expected,
        builder_module="trace_reference.geography.builder",
        builder_source_sha256=sha256_file(Path(__file__)),
        transformations=(
            "validate exact offline source digests and GeoJSON FeatureCollection schemas",
            "repair polygonal source geometry only with shapely.make_valid and record every repair",
            "union county RD317/RD407/RD556 for the Andrus simulation footprint",
            "transform WGS84 geometry to EPSG:26910 for area and distance calculations",
            "quantize WGS84 to microdegrees and EPSG:26910 points to millimetres",
            "derive a simulation-only route graph from source anchors and protocol endpoints",
        ),
        unresolved_factual_fields=(
            "RD407 west-levee breach segment survey geometry and legal maintenance responsibility",
            "Woodward Island crossing current type, completion, and operability",
            "road/water edge suitability for field routing",
        ),
    )
    atomic_write_bytes(
        output_root / "reference_geography_build_manifest_v1.json",
        canonical_json_bytes(manifest.model_dump(mode="json")),
        root=output_root,
        label="Reference geography build manifest",
    )
    return manifest
