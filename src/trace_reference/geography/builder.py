"""Deterministically derive the offline Reference geography catalog."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pyproj
import shapely
import yaml
from pyproj import Transformer
from shapely import make_valid, normalize, orient_polygons, union_all
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
    ReferenceSourceMetadata,
    ReferenceSourceMetadataRegistry,
    ReferenceSourceRecord,
    ReferenceSourceRetrievalRegistry,
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


def _safe_source_path(geography_root: Path, relative_name: str) -> Path:
    """Resolve a bounded source beneath a caller-trusted root before any read or hash."""

    return ArtifactLocator(
        root=geography_root,
        relative_name=Path("sources") / relative_name,
        maximum_bytes=25_000_000,
        label=f"Reference geography source {relative_name}",
    ).resolve()


def _load_geojson(root: Path, relative_name: str, expected_sha256: str) -> dict[str, Any]:
    path = _safe_source_path(root, relative_name)
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


def _require_properties(feature: Mapping[str, Any], expected: Mapping[str, object]) -> None:
    properties = _properties(feature)
    for field, value in expected.items():
        if properties.get(field) != value:
            raise ValueError(f"Reference source semantic mismatch: expected {field}={value!r}")


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
    result = cast(MultiPolygon, orient_polygons(normalize(MultiPolygon(polygons))))
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
    county_andrus_features = _features_by_integer(county, "OBJECTID", (19, 22, 23))
    for feature, district in zip(
        county_andrus_features,
        ("Upper Andrus Island 556", "Lower Andrus Island 317", "Andrus Island 407"),
        strict=True,
    ):
        _require_properties(feature, {"DISTRICT": district})
    county_brannan = _feature_by_integer(county, "OBJECTID", 24)
    _require_properties(county_brannan, {"DISTRICT": "Brannan Island 2067"})
    county_andrus = union_all([_feature_geometry(item) for item in county_andrus_features])
    dwr_expectations = {
        11: ("0341", "Sherman Island"),
        12: ("0003", "Grand Island"),
        20: ("0563", "Tyler Island"),
        23: ("0756", "Bouldin Island"),
        79: ("0556", "Upper Andrus Island"),
        81: ("0038", "Staten Island"),
        96: ("1601", "Twitchell Island"),
        259: ("BALMD", "Brannan-Andrus Island"),
    }
    for object_id, (code, place_name) in dwr_expectations.items():
        _require_properties(
            _feature_by_integer(dwr, "OBJECTID", object_id),
            {"LMA_Code": code, "LMA_Placename": place_name},
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
            _feature_geometry(county_brannan),
            (_source_binding("REF-GEO-SRC-02", ("OBJECTID:24",), "primary-boundary"),),
            "single-county-reclamation-district-footprint",
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
    _require_properties(
        incorporated,
        {"STATE": "06", "PLACE": "36882", "BASENAME": "Isleton"},
    )
    _require_properties(
        cdp,
        {"STATE": "06", "PLACE": "83374", "BASENAME": "Walnut Grove"},
    )
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
        expected_gaz_id = int(identifier.partition(":")[2])
        _require_properties(
            feature,
            {
                "gaz_id": expected_gaz_id,
                "gaz_featureclass": "Populated Place",
                "county_name": "Sacramento",
                "state_alpha": "CA",
            },
        )
        geometry = _feature_geometry(feature)
        is_multipoint = isinstance(geometry, MultiPoint)
        communities.append(
            ReferenceCommunity(
                community_id=community_id,
                name=name,
                anchor=_metric_point(_point_from_geometry(geometry)),
                boundary=None,
                geometry_semantics=(
                    "gnis-derived-centroid-of-official-multipoint-no-boundary"
                    if is_multipoint
                    else "gnis-official-point-no-boundary"
                ),
                source_bindings=(
                    _source_binding(
                        "REF-GEO-SRC-05",
                        (identifier,),
                        "derived-anchor" if is_multipoint else "identity-point",
                    ),
                ),
                limitation=(
                    "GNIS supplies identity/location geometry, not a community or exposure boundary; "
                    "the deterministic multipoint centroid, when used, is a derived simulation anchor."
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
    expected_inventory_names = {
        2061: "SACRAMENTO RIVER (RIO VISTA)",
        2717: "SAN JOAQUIN RIVER (ANTIOCH)",
        2286: "THREE MILE SLOUGH",
        2255: "SACRAMENTO RIVER (ISLETON)",
        29344: "SACRAMENTO RIVER (WALNUT GROVE)",
        2257: "SACRAMENTO RIVER (PAINTERSVILLE)",
        30337: "DUTCH SLOUGH",
        2212: "CACHE SLOUGH FERRY",
        2070: "STEAMBOAT SLOUGH FERRY (J-MACK)",
    }
    crossings: list[ReferenceCrossing] = []
    for crossing_id, name, source_id, object_id, crossing_type, role, evidence in definitions:
        feature = _feature_by_integer(sources[source_id], "OBJECTID", object_id)
        if source_id in {"REF-GEO-SRC-06", "REF-GEO-SRC-07"}:
            _require_properties(feature, {"NAME": expected_inventory_names[object_id]})
        if source_id == "REF-GEO-SRC-08":
            _require_properties(
                feature,
                {
                    "gaz_id": 238175,
                    "gaz_name": "Woodward Island Ferry",
                    "gaz_featureclass": "Crossing",
                    "state_alpha": "CA",
                },
            )
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
    source_metadata: Sequence[ReferenceSourceMetadata], geography_root: Path
) -> tuple[ReferenceSourceRecord, ...]:
    records: list[ReferenceSourceRecord] = []
    for raw in source_metadata:
        source_id = raw.source_id
        relative_name = SOURCE_RELATIVE_NAMES[source_id]
        source_path = _safe_source_path(geography_root, relative_name)
        records.append(
            ReferenceSourceRecord(
                source_id=source_id,
                phase0_requirement_ids=raw.phase0_requirement_ids,
                agency=raw.agency,
                dataset_title=raw.dataset_title,
                landing_page_url=raw.landing_page_url,
                machine_readable_url=raw.machine_readable_url,
                retrieved_at_utc=raw.retrieved_at_utc,
                upstream_response_sha256=raw.upstream_response_sha256,
                committed_snapshot_relative_path=relative_name,
                committed_snapshot_sha256=sha256_file(source_path),
                license_name=raw.license_name,
                license_locator=raw.license_locator,
                redistribution_status=raw.redistribution_status,
                release_inclusion=raw.release_inclusion,
                attribution=raw.attribution,
                limitations=raw.limitations,
            )
        )
    return tuple(records)


def _validate_retrieval_registry(
    *,
    records: Sequence[ReferenceSourceRecord],
    retrieval_registry: ReferenceSourceRetrievalRegistry,
    metadata_registry_sha256: str,
) -> None:
    if retrieval_registry.metadata_registry_sha256 != metadata_registry_sha256:
        raise ValueError("retrieval receipts bind a different metadata registry")
    record_by_id = {item.source_id: item for item in records}
    for receipt in retrieval_registry.receipts:
        record = record_by_id.get(receipt.source_id)
        if record is None:
            raise ValueError(f"retrieval receipt refers to absent source {receipt.source_id}")
        if receipt.endpoint_url != record.machine_readable_url:
            raise ValueError(f"retrieval endpoint mismatch: {receipt.source_id}")
        if receipt.retrieved_at_utc != record.retrieved_at_utc:
            raise ValueError(f"retrieval timestamp mismatch: {receipt.source_id}")
        if receipt.response_sha256 != record.upstream_response_sha256:
            raise ValueError(f"retrieval response digest mismatch: {receipt.source_id}")
        expected_output = f"sources/{record.committed_snapshot_relative_path}"
        if receipt.output_relative_path != expected_output:
            raise ValueError(f"retrieval output path mismatch: {receipt.source_id}")
        if receipt.output_sha256 != record.committed_snapshot_sha256:
            raise ValueError(f"retrieval output digest mismatch: {receipt.source_id}")

    expected_phase0_mapping = {
        "REF-GEO-SRC-01": ("REF-SRC-02",),
        "REF-GEO-SRC-02": ("REF-SRC-01",),
        "REF-GEO-SRC-03": ("REF-SRC-03",),
        "REF-GEO-SRC-04": ("REF-SRC-03",),
        "REF-GEO-SRC-05": ("REF-SRC-03",),
        "REF-GEO-SRC-06": ("REF-SRC-04",),
        "REF-GEO-SRC-07": ("REF-SRC-04",),
        "REF-GEO-SRC-08": ("REF-SRC-04",),
    }
    observed_phase0_mapping = {item.source_id: item.phase0_requirement_ids for item in records}
    if observed_phase0_mapping != expected_phase0_mapping:
        raise ValueError("Phase 0 and Phase 1 source identifiers are not fully reconciled")


def _validate_entity_receipt_bindings(
    catalog: ReferenceGeographyCatalog,
    retrieval_registry: ReferenceSourceRetrievalRegistry,
) -> None:
    receipt_features = {
        item.source_id: set(item.selected_feature_identifiers)
        for item in retrieval_registry.receipts
    }
    bindings = tuple(binding for entity in catalog.islands for binding in entity.source_bindings)
    bindings += tuple(
        binding for entity in catalog.communities for binding in entity.source_bindings
    )
    bindings += tuple(binding for entity in catalog.crossings for binding in entity.source_bindings)
    for binding in bindings:
        absent = set(binding.feature_identifiers) - receipt_features[binding.source_id]
        if absent:
            raise ValueError(
                f"entity binding is absent from source receipt {binding.source_id}: {sorted(absent)}"
            )


def _transformation_source_hashes() -> dict[str, str]:
    package_root = Path(__file__).parent
    names = ("builder.py", "catalog_models.py", "catalog_loading.py", "snapshot.py")
    return {name: sha256_file(_safe_code_path(package_root, name)) for name in names}


def _safe_code_path(package_root: Path, name: str) -> Path:
    return ArtifactLocator(
        root=package_root,
        relative_name=Path(name),
        maximum_bytes=1_000_000,
        label=f"Reference geography transformation source {name}",
    ).resolve()


def _yaml_mapping(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = yaml.safe_load(path.read_text("utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"{label} is not valid bounded YAML") from exc
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} root must be an object")
    return cast(Mapping[str, Any], value)


def build_reference_geography(
    *,
    geography_root: Path,
    output_root: Path,
    metadata_relative_name: Path = Path("source_metadata_v2.yaml"),
    retrieval_relative_name: Path = Path("source_retrieval_receipts_v2.yaml"),
) -> ReferenceGeographyBuildManifest:
    """Build and write a deterministic catalog from exact offline snapshots."""

    metadata_registry_path = ArtifactLocator(
        root=geography_root,
        relative_name=metadata_relative_name,
        maximum_bytes=1_000_000,
        label="Reference geography source metadata",
    ).resolve()
    retrieval_registry_path = ArtifactLocator(
        root=geography_root,
        relative_name=retrieval_relative_name,
        maximum_bytes=1_000_000,
        label="Reference geography retrieval receipts",
    ).resolve()
    metadata_registry = ReferenceSourceMetadataRegistry.model_validate(
        _yaml_mapping(metadata_registry_path, "Reference source metadata")
    )
    retrieval_registry = ReferenceSourceRetrievalRegistry.model_validate(
        _yaml_mapping(retrieval_registry_path, "Reference retrieval receipt registry")
    )
    metadata_registry_sha256 = sha256_file(metadata_registry_path)
    retrieval_registry_sha256 = sha256_file(retrieval_registry_path)
    records = _source_records(metadata_registry.sources, geography_root)
    _validate_retrieval_registry(
        records=records,
        retrieval_registry=retrieval_registry,
        metadata_registry_sha256=metadata_registry_sha256,
    )
    expected = {item.source_id: item.committed_snapshot_sha256 for item in records}
    sources = {
        source_id: _load_geojson(geography_root, relative_name, expected[source_id])
        for source_id, relative_name in SOURCE_RELATIVE_NAMES.items()
    }
    islands = _build_islands(sources)
    communities = _build_communities(sources)
    crossings = _build_crossings(sources)
    nodes, edges = _build_routes(islands, crossings)
    catalog = ReferenceGeographyCatalog(
        catalog_version="delta-reference-geography-v2",
        scientific_status="development-only-simulation-grade-pending-one-source-license-review",
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
            "The Sacramento County-derived clipped fixture is excluded from release until its dataset-specific redistribution terms are verified.",
            "Road and water graph endpoints are protocol design assumptions anchored by official points.",
            "The current Woodward crossing type and operability remain unresolved and non-operative facts.",
        ),
    )
    _validate_entity_receipt_bindings(catalog, retrieval_registry)
    catalog_name = "reference_geography_catalog_v2.json"
    catalog_bytes = canonical_json_bytes(catalog.model_dump(mode="json"))
    atomic_write_bytes(
        output_root / catalog_name,
        catalog_bytes,
        root=output_root,
        label="Reference geography catalog",
    )
    manifest = ReferenceGeographyBuildManifest(
        manifest_version="delta-reference-geography-build-v2",
        catalog_relative_path=catalog_name,
        catalog_sha256=hashlib.sha256(catalog_bytes).hexdigest(),
        source_snapshot_sha256=expected,
        builder_module="trace_reference.geography.builder",
        builder_source_sha256=_transformation_source_hashes()["builder.py"],
        metadata_registry_relative_path=metadata_registry_path.name,
        metadata_registry_sha256=metadata_registry_sha256,
        retrieval_receipts_relative_path=retrieval_registry_path.name,
        retrieval_receipts_sha256=retrieval_registry_sha256,
        transformation_source_sha256=_transformation_source_hashes(),
        environment_versions={
            "pyproj": pyproj.__version__,
            "proj": pyproj.proj_version_str,
            "shapely": shapely.__version__,
            "geos": shapely.geos_version_string,
        },
        release_ready=False,
        transformations=(
            "validate exact offline source digests and GeoJSON FeatureCollection schemas",
            "validate exact retrieval recipes, selections, timestamps, and response/output digests",
            "repair polygonal source geometry only with shapely.make_valid and record every repair",
            "orient polygon exteriors counterclockwise and normalize canonical ring and polygon order",
            "union county RD317/RD407/RD556 for the Andrus simulation footprint",
            "transform WGS84 geometry to EPSG:26910 for area and distance calculations",
            "quantize WGS84 to microdegrees and EPSG:26910 points to millimetres",
            "derive a simulation-only route graph from source anchors and protocol endpoints",
        ),
        unresolved_factual_fields=(
            "RD407 west-levee breach segment survey geometry and legal maintenance responsibility",
            "Woodward Island crossing current type, completion, and operability",
            "road/water edge suitability for field routing",
            "Sacramento County dataset-specific redistribution permission",
        ),
    )
    atomic_write_bytes(
        output_root / "reference_geography_build_manifest_v2.json",
        canonical_json_bytes(manifest.model_dump(mode="json")),
        root=output_root,
        label="Reference geography build manifest",
    )
    return manifest
