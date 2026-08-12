"""Source-bound, simulation-grade geography contracts for Reference."""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel

CoordinateE6: TypeAlias = tuple[int, int]
LinearRingE6: TypeAlias = tuple[CoordinateE6, ...]
PolygonE6: TypeAlias = tuple[LinearRingE6, ...]
MultiPolygonE6: TypeAlias = tuple[PolygonE6, ...]


class ReferenceMetricPoint(DeltaModel):
    """One source-derived point in both frozen runtime coordinate systems."""

    longitude_e6: int = Field(ge=-180_000_000, le=180_000_000)
    latitude_e6: int = Field(ge=-90_000_000, le=90_000_000)
    easting_mm_epsg26910: int
    northing_mm_epsg26910: int


class ReferenceBoundary(DeltaModel):
    """Quantized WGS84 polygons and an independently computed metric area."""

    polygons_e6: MultiPolygonE6 = Field(min_length=1)
    area_m2_epsg26910: int = Field(gt=0)
    repair_status: Literal["unchanged-valid", "repaired-with-make-valid"]


class ReferenceSourceBinding(DeltaModel):
    source_id: str = Field(pattern=r"^REF-GEO-SRC-[0-9]{2}$")
    feature_identifiers: tuple[str, ...] = Field(min_length=1)
    use: Literal["primary-boundary", "cross-check", "identity-point", "crossing-point"]


class ReferenceIsland(DeltaModel):
    island_id: str = Field(pattern=r"^ISL-0[1-8]$")
    name: str = Field(min_length=3)
    boundary: ReferenceBoundary
    anchor: ReferenceMetricPoint
    source_bindings: tuple[ReferenceSourceBinding, ...] = Field(min_length=1)
    boundary_semantics: Literal[
        "union-of-county-reclamation-district-footprints",
        "dwr-local-maintenance-area-footprint",
    ]
    limitation: str = Field(min_length=20)


class ReferenceCommunity(DeltaModel):
    community_id: str = Field(pattern=r"^TWN-0[1-4]$")
    name: str = Field(min_length=3)
    anchor: ReferenceMetricPoint
    boundary: ReferenceBoundary | None
    geometry_semantics: Literal[
        "census-administrative-boundary-not-exposure-footprint",
        "gnis-official-point-no-boundary",
    ]
    source_bindings: tuple[ReferenceSourceBinding, ...] = Field(min_length=1)
    limitation: str = Field(min_length=20)


class ReferenceCrossing(DeltaModel):
    crossing_id: str = Field(pattern=r"^XNG-(0[1-9]|10)$")
    name: str = Field(min_length=3)
    anchor: ReferenceMetricPoint
    crossing_type: Literal[
        "fixed-bridge",
        "movable-bascule",
        "movable-lift",
        "hydraulic-ferry",
        "cable-ferry",
        "crossing-type-unresolved",
    ]
    source_bindings: tuple[ReferenceSourceBinding, ...] = Field(min_length=1)
    evidence_status: Literal[
        "official-inventory-verified", "official-identity-current-type-unresolved"
    ]
    topology_role: Literal["exposure-network", "boundary-connector"]
    limitation: str = Field(min_length=20)


class ReferenceRouteNode(DeltaModel):
    node_id: str = Field(pattern=r"^(ISL-0[1-8]|BND-[A-Z0-9-]+)$")
    anchor: ReferenceMetricPoint
    exposure_node: bool


class ReferenceRouteEdge(DeltaModel):
    edge_id: str = Field(pattern=r"^(XNG-(0[1-9]|10)|WTR-[0-9]{2})$")
    from_node_id: str
    to_node_id: str
    mode: Literal["road-crossing", "water-transfer"]
    crossing_id: str | None = Field(default=None, pattern=r"^XNG-(0[1-9]|10)$")
    length_m: int = Field(gt=0)
    provenance: Literal[
        "official-crossing-point-with-protocol-endpoints",
        "source-anchor-derived-simulation-water-link",
    ]
    operative_claim: Literal["simulation-topology-only"]

    @model_validator(mode="after")
    def validate_mode_binding(self) -> ReferenceRouteEdge:
        if (self.mode == "road-crossing") != (self.crossing_id is not None):
            raise ValueError("only road-crossing edges bind a crossing identifier")
        return self


class ReferenceSourceRecord(DeltaModel):
    source_id: str = Field(pattern=r"^REF-GEO-SRC-[0-9]{2}$")
    agency: str
    dataset_title: str
    landing_page_url: str
    machine_readable_url: str
    retrieved_at_utc: str
    upstream_response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    committed_snapshot_relative_path: str
    committed_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    license_name: str
    license_locator: str
    redistribution_status: Literal[
        "united-states-public-domain",
        "california-government-public-use",
        "creative-commons-attribution",
    ]
    attribution: str
    limitations: tuple[str, ...] = Field(min_length=1)


class ReferenceGeographyCatalog(DeltaModel):
    """Complete offline runtime geography; no network access is required."""

    catalog_version: Literal["delta-reference-geography-v1"]
    scientific_status: Literal["simulation-grade-curated-from-authoritative-sources"]
    source_crs: Literal["EPSG:4326"]
    metric_crs: Literal["EPSG:26910"]
    coordinate_quantization: Literal["wgs84-microdegrees-and-epsg26910-millimetres"]
    runtime_network_access: Literal["forbidden"]
    sources: tuple[ReferenceSourceRecord, ...] = Field(min_length=6)
    islands: tuple[ReferenceIsland, ...] = Field(min_length=8, max_length=8)
    communities: tuple[ReferenceCommunity, ...] = Field(min_length=4, max_length=4)
    crossings: tuple[ReferenceCrossing, ...] = Field(min_length=10, max_length=10)
    route_nodes: tuple[ReferenceRouteNode, ...] = Field(min_length=9)
    route_edges: tuple[ReferenceRouteEdge, ...] = Field(min_length=10)
    limitations: tuple[str, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_entity_and_graph_coverage(self) -> ReferenceGeographyCatalog:
        expected_islands = tuple(f"ISL-{index:02d}" for index in range(1, 9))
        expected_communities = tuple(f"TWN-{index:02d}" for index in range(1, 5))
        expected_crossings = tuple(f"XNG-{index:02d}" for index in range(1, 11))
        if tuple(item.island_id for item in self.islands) != expected_islands:
            raise ValueError("Reference island coverage/order is incomplete")
        if tuple(item.community_id for item in self.communities) != expected_communities:
            raise ValueError("Reference community coverage/order is incomplete")
        if tuple(item.crossing_id for item in self.crossings) != expected_crossings:
            raise ValueError("Reference crossing coverage/order is incomplete")
        node_ids = {item.node_id for item in self.route_nodes}
        if len(node_ids) != len(self.route_nodes):
            raise ValueError("Reference route node identifiers are not unique")
        if not set(expected_islands).issubset(node_ids):
            raise ValueError("each exposed island requires a route node")
        for edge in self.route_edges:
            if edge.from_node_id not in node_ids or edge.to_node_id not in node_ids:
                raise ValueError(f"route edge {edge.edge_id} references an absent node")
        expected_crossing_set = set(expected_crossings)
        graph_crossings = {item.crossing_id for item in self.route_edges if item.crossing_id}
        if expected_crossing_set != graph_crossings:
            raise ValueError("each Reference crossing must appear in the route graph")
        return self


class ReferenceGeographyBuildManifest(DeltaModel):
    manifest_version: Literal["delta-reference-geography-build-v1"]
    catalog_relative_path: str
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_snapshot_sha256: dict[str, str]
    builder_module: Literal["trace_reference.geography.builder"]
    builder_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    transformations: tuple[str, ...] = Field(min_length=3)
    unresolved_factual_fields: tuple[str, ...]
