from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import yaml

from trace_jepa.workbench.models import (
    AssetState,
    ControllerState,
    GroupState,
    Position,
    RouteBelief,
    RouteTruth,
    TruthState,
    WorkbenchState,
)


def _positions(points: list[list[float]]) -> list[Position]:
    return [Position(x=float(x), y=float(y)) for x, y in points]


def _distance_point_to_segment(point: Position, a: Position, b: Position) -> float:
    dx, dy = b.x - a.x, b.y - a.y
    if abs(dx) + abs(dy) < 1e-12:
        return math.hypot(point.x - a.x, point.y - a.y)
    t = ((point.x - a.x) * dx + (point.y - a.y) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    px, py = a.x + t * dx, a.y + t * dy
    return math.hypot(point.x - px, point.y - py)


def _blocked_segment(waypoints: list[Position], blockage: Position | None) -> int | None:
    if blockage is None or len(waypoints) < 2:
        return None
    # When the obstruction is exactly a waypoint, the outbound edge beginning
    # at that waypoint is blocked. This lets a boat reach the hazard point and
    # return along the already traversed prefix without crossing the obstacle.
    for index, waypoint in enumerate(waypoints[:-1]):
        if math.hypot(waypoint.x - blockage.x, waypoint.y - blockage.y) < 1e-6:
            return index
    return min(
        range(len(waypoints) - 1),
        key=lambda index: _distance_point_to_segment(
            blockage, waypoints[index], waypoints[index + 1]
        ),
    )


def load_initial_state(run_id: str, scenario_path: str | Path) -> WorkbenchState:
    payload: dict[str, Any] = yaml.safe_load(Path(scenario_path).read_text(encoding="utf-8"))

    routes: dict[str, RouteTruth] = {}
    for index, (route_id, route) in enumerate(payload["routes"].items()):
        initial_depth = 0.34 if route_id == "north_channel" else 0.22
        waypoints = _positions(route["waypoints"])
        blockage_payload = route.get("blockage_position")
        blockage = (
            Position(x=float(blockage_payload[0]), y=float(blockage_payload[1]))
            if blockage_payload
            else None
        )
        debris_blocked = str(route.get("hidden_status", "open")) == "blocked"
        blocked_index = _blocked_segment(waypoints, blockage) if debris_blocked else None
        edge_open = [True for _ in range(max(0, len(waypoints) - 1))]
        if blocked_index is not None:
            edge_open[blocked_index] = False
        routes[route_id] = RouteTruth(
            route_id=route_id,
            label=str(route["label"]),
            waypoints=waypoints,
            mode=str(route.get("mode", "water")),
            start_location_id=route.get("start_location"),
            end_location_id=route.get("end_location"),
            water_depth=initial_depth,
            debris_blocked=debris_blocked,
            blockage_position=blockage,
            blocked_segment_index=blocked_index,
            edge_open=edge_open,
            open=all(edge_open),
            susceptibility=1.2 if index == 0 else 0.85,
            nominal_travel_s=float(route.get("nominal_travel_s", 600)),
        )

    locations = payload["locations"]
    assets: dict[str, AssetState] = {}
    for asset_id, asset in payload["assets"].items():
        location_id = str(asset["location"])
        x, y = locations[location_id]["position"]
        position = Position(x=float(x), y=float(y))
        asset_type = str(asset["type"])
        speed = {
            "survey_drone": 8.0,
            "rescue_boat": 4.0,
            "helicopter": 12.0,
            "ground_team": 2.0,
        }.get(asset_type, 3.0)
        capacity = int(asset.get("capacity", 0))
        assets[asset_id] = AssetState(
            asset_id=asset_id,
            asset_type=asset_type,
            position=position,
            home_position=position,
            capacity=capacity,
            speed=speed,
            resource=float(asset.get("battery", 1.0)),
            operating_cost=2.0 if asset_type == "survey_drone" else 5.0,
            weather_tolerance=0.70 if asset_type == "survey_drone" else 0.85,
        )

    mission = payload["mission"]
    pickup_id = str(mission["pickup_location"])
    x, y = locations[pickup_id]["position"]
    groups: dict[str, GroupState] = {}
    if bool(mission.get("seed_initial_group", False)):
        people = int(mission["people_to_rescue"])
        groups["group_riverside"] = GroupState(
            group_id="group_riverside",
            label=str(locations[pickup_id]["label"]),
            position=Position(x=float(x), y=float(y)),
            people=people,
            people_waiting=people,
            severity=0.55,
            deadline_s=float(mission["deadline_s"]),
            safe_location_id=str(mission.get("safe_location", "safe_transfer_dock")),
        )

    truth = TruthState(
        routes=routes,
        assets=assets,
        groups=groups,
        weather_severity=float(payload.get("conditions", {}).get("weather_severity", 0.25)),
        global_water_level=0.24,
    )

    route_beliefs: dict[str, RouteBelief] = {}
    for route_id, route in payload["routes"].items():
        initial_report = str(route.get("initial_report", "unknown"))
        route_beliefs[route_id] = RouteBelief(
            route_id=route_id,
            status=initial_report if initial_report in {"unknown", "open", "blocked"} else "unknown",
            confidence=0.82 if initial_report == "open" else 0.0,
            observed_at=0.0 if initial_report != "unknown" else None,
            source="scenario_initial_report" if initial_report != "unknown" else None,
            clearance_valid_until=120.0 if initial_report == "open" else None,
        )

    controller = ControllerState(
        route_beliefs=route_beliefs,
        known_assets={key: value.model_copy(deep=True) for key, value in assets.items()},
        known_groups={key: value.model_copy(deep=True) for key, value in groups.items()},
    )

    state = WorkbenchState(run_id=run_id, truth=truth, controller=controller)
    safe_location_id = str(mission.get("safe_location", "safe_transfer_dock"))
    safe_payload = locations.get(safe_location_id, locations.get("rescue_base"))
    safe_position = None
    if safe_payload and "position" in safe_payload:
        safe_x, safe_y = safe_payload["position"]
        safe_position = Position(x=float(safe_x), y=float(safe_y))
    state.config.rescue.safe_location_id = safe_location_id
    for asset in state.truth.assets.values():
        if asset.asset_type in {"rescue_boat", "helicopter", "ground_team"}:
            asset.safe_location_id = safe_location_id
            asset.safe_position = safe_position or asset.home_position
            if asset.asset_id in state.controller.known_assets:
                state.controller.known_assets[asset.asset_id].safe_location_id = safe_location_id
                state.controller.known_assets[asset.asset_id].safe_position = (
                    safe_position or asset.home_position
                )
    state.metrics.pending_people = sum(
        int(group.people_waiting or 0)
        for group in state.truth.groups.values()
        if not group.cancelled and not group.rescued
    )
    return state
