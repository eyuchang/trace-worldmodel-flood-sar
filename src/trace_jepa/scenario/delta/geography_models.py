from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GeographyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FixedCoordinate(GeographyModel):
    longitude_e7: int = Field(ge=-1_800_000_000, le=1_800_000_000)
    latitude_e7: int = Field(ge=-900_000_000, le=900_000_000)
    easting_mm: int
    northing_mm: int


class LinearRing(GeographyModel):
    points: list[FixedCoordinate] = Field(min_length=4)

    @model_validator(mode="after")
    def validate_closed(self) -> LinearRing:
        if self.points[0] != self.points[-1]:
            raise ValueError("linear ring must be closed")
        return self


class PolygonGeometry(GeographyModel):
    polygons: list[LinearRing] = Field(min_length=1)


class LineGeometry(GeographyModel):
    points: list[FixedCoordinate] = Field(min_length=2)


class SourceRecord(GeographyModel):
    source_id: str
    title: str
    # ``locator`` is retained so the immutable v2 catalog remains loadable.
    # v3 records distinguish a human landing page from a machine endpoint.
    locator: str
    landing_page_locator: str | None = None
    retrieval_locator: str | None = None
    media_type: str | None = None
    snapshot_format: str | None = None
    snapshot_file_name: str
    retrieved_utc: datetime
    source_tier: str
    status: str
    use: str
    license_name: str
    license_locator: str
    redistribution_status: str = "review-required"
    archive_member: str | None = None
    archive_member_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    archive_member_verification: str | None = None
    extraction_command: str | None = None
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_length: int = Field(gt=0)


class ElevationSummary(GeographyModel):
    vertical_datum: str
    valid_cell_count: int = Field(gt=0)
    minimum_mm: int
    median_mm: int
    maximum_mm: int
    source_id: str


class Island(GeographyModel):
    island_id: str
    name: str
    scenario_acres: int = Field(gt=0)
    source_area_acres: int = Field(gt=0)
    interior_elevation_millifeet_msl: int
    centroid: FixedCoordinate
    geometry: PolygonGeometry
    geometry_status: str
    elevation_summary: ElevationSummary
    source_id: str


class Community(GeographyModel):
    community_id: str
    name: str
    island_id: str
    census_geoid: str
    centroid: FixedCoordinate
    geometry: PolygonGeometry
    source_id: str


class Crossing(GeographyModel):
    crossing_id: str
    name: str
    carries: str
    crossing_type: str
    design_description: str
    source_feature_id: str
    location: FixedCoordinate
    nominal_travel_s: int = Field(gt=0)
    source_id: str


class Gauge(GeographyModel):
    gauge_id: str
    name: str
    location: FixedCoordinate
    baseline_stage_millifeet: int
    action_stage_millifeet: int
    minor_flood_stage_millifeet: int
    threshold_status: str
    source_id: str


class Waterway(GeographyModel):
    waterway_id: str
    name: str
    segments: list[LineGeometry] = Field(min_length=1)
    source_id: str


class Facility(GeographyModel):
    facility_id: str
    name: str
    facility_type: str
    location: FixedCoordinate
    location_precision: str
    operational_for_routing: bool = False
    source_ids: list[str] = Field(min_length=1)


class GovernanceEntity(GeographyModel):
    governance_id: str
    name: str
    governance_type: str
    island_ids: list[str] = Field(min_length=1)
    source_feature_id: str
    source_id: str


class GeographyCatalog(GeographyModel):
    schema_version: str
    coordinate_reference: str
    coordinate_warning: str
    build_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sources: list[SourceRecord] = Field(min_length=1)
    islands: list[Island] = Field(min_length=1)
    communities: list[Community] = Field(min_length=1)
    crossings: list[Crossing] = Field(min_length=1)
    gauges: list[Gauge] = Field(min_length=1)
    waterways: list[Waterway] = Field(min_length=1)
    facilities: list[Facility] = Field(min_length=1)
    governance: list[GovernanceEntity] = Field(min_length=1)
