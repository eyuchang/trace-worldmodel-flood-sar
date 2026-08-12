"""Controller-visible route-assignment contracts for Reference."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel


class ReferenceRouteMode(str, Enum):
    ROAD = "road"
    WATER = "water"
    AIR = "air"


class ReferenceRouteStatus(str, Enum):
    OPEN = "open"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


class ReferencePublicTargetAssignment(DeltaModel):
    """Deterministic map from a noisy public location to the simulation topology."""

    schema_version: Literal["delta-reference-public-target-assignment-v1"]
    call_id: str = Field(pattern=r"^RC-[0-9a-f]{16}$")
    destination_node_id: str = Field(pattern=r"^ISL-0[1-8]$")
    assignment_method: Literal["inside-source-bound-footprint", "nearest-source-bound-footprint"]
    distance_to_footprint_m: int = Field(ge=0)
    assignment_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReferencePublicRoutePlan(DeltaModel):
    """One resource-specific route derived exclusively from public scenario state."""

    schema_version: Literal["delta-reference-public-route-plan-v1"]
    route_plan_id: str = Field(pattern=r"^REF-ROUTE-[0-9a-f]{20}$")
    resource_id: str = Field(pattern=r"^RR-[0-9a-f]{16}$")
    call_id: str = Field(pattern=r"^RC-[0-9a-f]{16}$")
    origin_node_id: str = Field(pattern=r"^(ISL-0[1-8]|BND-[A-Z0-9-]+)$")
    destination_node_id: str = Field(pattern=r"^ISL-0[1-8]$")
    route_mode: ReferenceRouteMode
    edge_ids: tuple[str, ...]
    crossing_ids: tuple[str, ...]
    focal_crossing_id: str | None = Field(default=None, pattern=r"^XNG-(0[1-9]|10)$")
    gauge_id: Literal["FPT", "RVB", "SJJ", "ANH", "MRU", "OLD", "MSD"]
    status: ReferenceRouteStatus
    status_reason: str = Field(min_length=8)
    estimated_travel_s: int | None = Field(default=None, ge=0, le=86_400)
    route_length_m: int = Field(ge=0)
    sample_time_s: int = Field(ge=-172_800, le=345_600)
    route_plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_route_disposition(self) -> ReferencePublicRoutePlan:
        if self.focal_crossing_id is not None and self.focal_crossing_id not in self.crossing_ids:
            raise ValueError("Reference focal crossing must occur in the route")
        if self.status == ReferenceRouteStatus.UNAVAILABLE:
            if self.estimated_travel_s is not None:
                raise ValueError("unavailable Reference route cannot declare travel time")
        elif self.estimated_travel_s is None:
            raise ValueError("routable Reference plan requires an estimated travel time")
        if self.route_mode != ReferenceRouteMode.ROAD and self.crossing_ids:
            raise ValueError("only a road route may bind modeled road crossings")
        return self


class ReferencePublicRouteCatalog(DeltaModel):
    schema_version: Literal["delta-reference-public-route-catalog-v1"]
    call_id: str = Field(pattern=r"^RC-[0-9a-f]{16}$")
    at_s: int = Field(ge=-172_800, le=345_600)
    target_assignment: ReferencePublicTargetAssignment
    routes: tuple[ReferencePublicRoutePlan, ...]
    route_catalog_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_catalog(self) -> ReferencePublicRouteCatalog:
        if self.target_assignment.call_id != self.call_id:
            raise ValueError("Reference route catalog target names another call")
        if self.routes != tuple(sorted(self.routes, key=lambda item: item.resource_id)):
            raise ValueError("Reference routes must use canonical resource order")
        resource_ids = tuple(item.resource_id for item in self.routes)
        if len(set(resource_ids)) != len(resource_ids):
            raise ValueError("Reference route catalog repeats a physical resource")
        if any(
            item.call_id != self.call_id or item.sample_time_s != self.at_s for item in self.routes
        ):
            raise ValueError("Reference route plan does not bind this catalog")
        return self
