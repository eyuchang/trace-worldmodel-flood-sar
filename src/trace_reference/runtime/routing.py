"""Deterministic routing from public reports and public physical state."""

from __future__ import annotations

import hashlib
import heapq
import math
from dataclasses import dataclass

from pyproj import Transformer
from shapely.geometry import Point

from trace_jepa.support import canonical_json_bytes
from trace_reference.domain.observations import ReferenceRawReport
from trace_reference.domain.resources import (
    ReferencePublicResourceCatalog,
    ReferencePublicResourceDefinition,
    ReferenceResourceClass,
)
from trace_reference.domain.routing import (
    ReferencePublicRouteCatalog,
    ReferencePublicRoutePlan,
    ReferencePublicTargetAssignment,
    ReferenceRouteMode,
    ReferenceRouteStatus,
)
from trace_reference.geography.catalog_models import ReferenceMetricPoint, ReferenceRouteEdge
from trace_reference.geography.runtime_geometry import boundary_metric_geometry

from .scenario_index import ReferencePublicPhysicalView, ReferenceScenarioIndex

_TO_METRIC = Transformer.from_crs(4326, 26910, always_xy=True)
_AIR_CLASSES = frozenset(
    {
        ReferenceResourceClass.ROTARY_HOIST,
        ReferenceResourceClass.ROTARY_RECON,
        ReferenceResourceClass.SMALL_UAS,
    }
)
_WATER_CLASSES = frozenset({ReferenceResourceClass.RESCUE_BOAT, ReferenceResourceClass.AIRBOAT})


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


@dataclass(frozen=True)
class _Path:
    edge_ids: tuple[str, ...]
    length_m: int


@dataclass(frozen=True)
class _RouteDisposition:
    mode: ReferenceRouteMode
    path: _Path
    crossing_ids: tuple[str, ...]
    status: ReferenceRouteStatus
    reason: str


class ReferenceRouteService:
    """Build one public, resource-specific route catalog for a delivered report."""

    route_service_version = "delta-reference-route-service-v1"

    def __init__(self, index: ReferenceScenarioIndex) -> None:
        self.index = index
        self._island_geometry = {
            item.island_id: boundary_metric_geometry(item.boundary)
            for item in index.geography.islands
        }

    def build_catalog(
        self,
        report: ReferenceRawReport,
        resources: ReferencePublicResourceCatalog,
        *,
        at_s: int,
    ) -> ReferencePublicRouteCatalog:
        physical = self.index.physical_at(at_s)
        target = self._assign_target(report)
        routes = tuple(
            self._route(resource, report, target, physical) for resource in resources.resources
        )
        body = {
            "schema_version": "delta-reference-public-route-catalog-v1",
            "call_id": report.call_id,
            "at_s": physical.at_s,
            "target_assignment": target.model_dump(mode="json"),
            "routes": [item.model_dump(mode="json") for item in routes],
        }
        return ReferencePublicRouteCatalog(
            **body,
            route_catalog_digest=_digest(body),
        )

    def _assign_target(self, report: ReferenceRawReport) -> ReferencePublicTargetAssignment:
        point = Point(
            report.location.easting_mm_epsg26910 / 1_000,
            report.location.northing_mm_epsg26910 / 1_000,
        )
        containing = tuple(
            sorted(
                island_id
                for island_id, geometry in self._island_geometry.items()
                if geometry.covers(point)
            )
        )
        if containing:
            island_id, distance_m, method = containing[0], 0, "inside-source-bound-footprint"
        else:
            distance, island_id = min(
                (geometry.distance(point), island_id)
                for island_id, geometry in self._island_geometry.items()
            )
            distance_m, method = round(distance), "nearest-source-bound-footprint"
        body = {
            "schema_version": "delta-reference-public-target-assignment-v1",
            "call_id": report.call_id,
            "destination_node_id": island_id,
            "assignment_method": method,
            "distance_to_footprint_m": distance_m,
        }
        return ReferencePublicTargetAssignment(**body, assignment_digest=_digest(body))

    def _route(
        self,
        resource: ReferencePublicResourceDefinition,
        report: ReferenceRawReport,
        target: ReferencePublicTargetAssignment,
        physical: ReferencePublicPhysicalView,
    ) -> ReferencePublicRoutePlan:
        mode = _route_mode(resource)
        if "compatible-watercraft-or-access-required" in resource.constraints:
            return self._unavailable_plan(
                resource,
                report,
                target,
                physical,
                mode,
                "paired watercraft/access is outside the single-resource proposal grammar",
            )
        if mode == ReferenceRouteMode.AIR:
            return self._air_plan(resource, report, target, physical)
        if mode == ReferenceRouteMode.WATER:
            return self._water_plan(resource, report, target, physical)
        return self._road_plan(resource, report, target, physical)

    def _road_plan(
        self,
        resource: ReferencePublicResourceDefinition,
        report: ReferenceRawReport,
        target: ReferencePublicTargetAssignment,
        physical: ReferencePublicPhysicalView,
    ) -> ReferencePublicRoutePlan:
        path = self._shortest_path(
            resource.staged_node_id,
            target.destination_node_id,
            mode="road-crossing",
        )
        if path is None:
            return self._unavailable_plan(
                resource,
                report,
                target,
                physical,
                ReferenceRouteMode.ROAD,
                "no road path exists in the registered simulation topology",
            )
        crossing_ids = tuple(path.edge_ids)
        state = {item.crossing_id: item.status for item in physical.crossings}
        statuses = tuple(state[item] for item in crossing_ids)
        if any(item in {"closed", "suspended"} for item in statuses):
            status = ReferenceRouteStatus.BLOCKED
            reason = "one or more modeled road crossings are closed or suspended"
        elif any(item == "unavailable-unresolved" for item in statuses):
            status = ReferenceRouteStatus.UNKNOWN
            reason = "one or more crossing types or operative states are unresolved"
        else:
            status = ReferenceRouteStatus.OPEN
            reason = "all crossings on the registered road path are model-open"
        return self._plan(
            resource,
            report,
            target,
            physical,
            _RouteDisposition(
                ReferenceRouteMode.ROAD,
                path,
                crossing_ids,
                status,
                reason,
            ),
        )

    def _water_plan(
        self,
        resource: ReferencePublicResourceDefinition,
        report: ReferenceRawReport,
        target: ReferencePublicTargetAssignment,
        physical: ReferencePublicPhysicalView,
    ) -> ReferencePublicRoutePlan:
        path = self._shortest_path(
            resource.staged_node_id,
            target.destination_node_id,
            mode="water-transfer",
        )
        if path is None:
            path = _Path(
                (),
                _node_distance_m(self.index, resource.staged_node_id, target.destination_node_id),
            )
            status = ReferenceRouteStatus.UNKNOWN
            reason = "direct water ingress is a simulation fallback requiring current verification"
        else:
            status = ReferenceRouteStatus.OPEN
            reason = "registered simulation water links are model-open"
        return self._plan(
            resource,
            report,
            target,
            physical,
            _RouteDisposition(
                ReferenceRouteMode.WATER,
                path,
                (),
                status,
                reason,
            ),
        )

    def _air_plan(
        self,
        resource: ReferencePublicResourceDefinition,
        report: ReferenceRawReport,
        target: ReferencePublicTargetAssignment,
        physical: ReferencePublicPhysicalView,
    ) -> ReferencePublicRoutePlan:
        if physical.weather.air_operability == "grounded":
            status = ReferenceRouteStatus.BLOCKED
            reason = "model weather grounds aviation resources"
        elif physical.weather.air_operability == "reduced":
            status = ReferenceRouteStatus.UNKNOWN
            reason = "model weather indicates reduced aviation operability"
        else:
            status = ReferenceRouteStatus.OPEN
            reason = "model weather permits normal aviation operation"
        return self._plan(
            resource,
            report,
            target,
            physical,
            _RouteDisposition(
                ReferenceRouteMode.AIR,
                _Path(
                    (),
                    _node_distance_m(
                        self.index,
                        resource.staged_node_id,
                        target.destination_node_id,
                    ),
                ),
                (),
                status,
                reason,
            ),
        )

    def _unavailable_plan(
        self,
        resource: ReferencePublicResourceDefinition,
        report: ReferenceRawReport,
        target: ReferencePublicTargetAssignment,
        physical: ReferencePublicPhysicalView,
        mode: ReferenceRouteMode,
        reason: str,
    ) -> ReferencePublicRoutePlan:
        return self._plan(
            resource,
            report,
            target,
            physical,
            _RouteDisposition(
                mode,
                _Path((), 0),
                (),
                ReferenceRouteStatus.UNAVAILABLE,
                reason,
            ),
        )

    def _plan(
        self,
        resource: ReferencePublicResourceDefinition,
        report: ReferenceRawReport,
        target: ReferencePublicTargetAssignment,
        physical: ReferencePublicPhysicalView,
        disposition: _RouteDisposition,
    ) -> ReferencePublicRoutePlan:
        focal = _focal_crossing(
            self.index,
            disposition.crossing_ids,
            target.destination_node_id,
        )
        gauge_id = _nearest_gauge(self.index, focal, target.destination_node_id)
        route_key = {
            "service": self.route_service_version,
            "resource_id": resource.resource_id,
            "call_id": report.call_id,
            "origin": resource.staged_node_id,
            "destination": target.destination_node_id,
            "mode": disposition.mode.value,
            "edges": disposition.path.edge_ids,
            "sample_time_s": physical.at_s,
        }
        route_id = f"REF-ROUTE-{_digest(route_key)[:20]}"
        body = {
            "schema_version": "delta-reference-public-route-plan-v1",
            "route_plan_id": route_id,
            "resource_id": resource.resource_id,
            "call_id": report.call_id,
            "origin_node_id": resource.staged_node_id,
            "destination_node_id": target.destination_node_id,
            "route_mode": disposition.mode.value,
            "edge_ids": disposition.path.edge_ids,
            "crossing_ids": disposition.crossing_ids,
            "focal_crossing_id": focal,
            "gauge_id": gauge_id,
            "status": disposition.status.value,
            "status_reason": disposition.reason,
            "estimated_travel_s": (
                None
                if disposition.status == ReferenceRouteStatus.UNAVAILABLE
                else resource.nominal_travel_s
            ),
            "route_length_m": disposition.path.length_m,
            "sample_time_s": physical.at_s,
        }
        return ReferencePublicRoutePlan(**body, route_plan_digest=_digest(body))

    def _shortest_path(self, start: str, target: str, *, mode: str) -> _Path | None:
        if start == target:
            return _Path((), 0)
        adjacency: dict[str, list[tuple[str, ReferenceRouteEdge]]] = {}
        for edge in self.index.geography.route_edges:
            if edge.mode != mode:
                continue
            adjacency.setdefault(edge.from_node_id, []).append((edge.to_node_id, edge))
            adjacency.setdefault(edge.to_node_id, []).append((edge.from_node_id, edge))
        frontier: list[tuple[int, tuple[str, ...], str]] = [(0, (), start)]
        best: dict[str, tuple[int, tuple[str, ...]]] = {start: (0, ())}
        while frontier:
            length, edge_ids, node = heapq.heappop(frontier)
            if best.get(node) != (length, edge_ids):
                continue
            if node == target:
                return _Path(edge_ids, length)
            for next_node, edge in sorted(
                adjacency.get(node, ()), key=lambda item: item[1].edge_id
            ):
                candidate = (length + edge.length_m, (*edge_ids, edge.edge_id))
                if next_node not in best or candidate < best[next_node]:
                    best[next_node] = candidate
                    heapq.heappush(frontier, (*candidate, next_node))
        return None


def _route_mode(resource: ReferencePublicResourceDefinition) -> ReferenceRouteMode:
    if resource.resource_class in _AIR_CLASSES:
        return ReferenceRouteMode.AIR
    if resource.resource_class in _WATER_CLASSES:
        return ReferenceRouteMode.WATER
    return ReferenceRouteMode.ROAD


def _node_distance_m(index: ReferenceScenarioIndex, first: str, second: str) -> int:
    left = index.nodes[first].anchor
    right = index.nodes[second].anchor
    dx = left.easting_mm_epsg26910 - right.easting_mm_epsg26910
    dy = left.northing_mm_epsg26910 - right.northing_mm_epsg26910
    return round(math.hypot(dx, dy) / 1_000)


def _focal_crossing(
    index: ReferenceScenarioIndex,
    crossing_ids: tuple[str, ...],
    destination_node_id: str,
) -> str | None:
    if not crossing_ids:
        return None
    target = index.nodes[destination_node_id].anchor
    return min(
        crossing_ids,
        key=lambda crossing_id: (
            (index.crossings[crossing_id].anchor.easting_mm_epsg26910 - target.easting_mm_epsg26910)
            ** 2
            + (
                index.crossings[crossing_id].anchor.northing_mm_epsg26910
                - target.northing_mm_epsg26910
            )
            ** 2,
            crossing_id,
        ),
    )


def _nearest_gauge(
    index: ReferenceScenarioIndex,
    focal_crossing_id: str | None,
    destination_node_id: str,
) -> str:
    anchor = (
        index.crossings[focal_crossing_id].anchor
        if focal_crossing_id is not None
        else index.nodes[destination_node_id].anchor
    )
    return min(
        index.gauge_context.gauges,
        key=lambda gauge: (
            _gauge_distance_squared(gauge.longitude_e6, gauge.latitude_e6, anchor),
            gauge.gauge_id,
        ),
    ).gauge_id


def _gauge_distance_squared(
    longitude_e6: int,
    latitude_e6: int,
    anchor: ReferenceMetricPoint,
) -> float:
    transformed = _TO_METRIC.transform(longitude_e6 / 1_000_000, latitude_e6 / 1_000_000)
    easting, northing = float(transformed[0]), float(transformed[1])
    anchor_easting = anchor.easting_mm_epsg26910 / 1_000
    anchor_northing = anchor.northing_mm_epsg26910 / 1_000
    return (easting - anchor_easting) ** 2 + (northing - anchor_northing) ** 2
