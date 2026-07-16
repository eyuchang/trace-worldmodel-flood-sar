from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Iterable

from trace_jepa.contracts import ActionInstance
from trace_jepa.workbench.models import PathSegment, Position, RouteTruth, WorkbenchState


class NavigationError(RuntimeError):
    pass


def distance(a: Position, b: Position) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _key(position: Position) -> tuple[float, float]:
    return (round(position.x, 6), round(position.y, 6))


@dataclass(frozen=True)
class Edge:
    route_id: str
    edge_index: int
    start: Position
    end: Position
    length: float
    direction: str
    mode: str
    weight: float


@dataclass(frozen=True)
class NavigationPlan:
    points: tuple[Position, ...]
    segments: tuple[PathSegment, ...]
    target: Position
    total_distance: float
    summary: str


def route_edges(route: RouteTruth, *, reverse: bool = False) -> list[Edge]:
    edges: list[Edge] = []
    points = route.waypoints
    for index in range(len(points) - 1):
        start = points[index]
        end = points[index + 1]
        if reverse:
            start, end = end, start
        edges.append(
            Edge(
                route_id=route.route_id,
                edge_index=index,
                start=start,
                end=end,
                length=distance(start, end),
                direction="reverse" if reverse else "forward",
                mode=route.mode,
                weight=distance(start, end),
            )
        )
    if reverse:
        edges.reverse()
    return edges


def truth_edge_open(route: RouteTruth, edge_index: int) -> bool:
    if route.edge_open and 0 <= edge_index < len(route.edge_open):
        return bool(route.edge_open[edge_index])
    return bool(route.open)


def controller_edge_open(state: WorkbenchState, route_id: str) -> bool:
    belief = state.controller.route_beliefs.get(route_id)
    return belief is None or belief.status != "blocked"


def _edge_weight(state: WorkbenchState, edge: Edge, *, view: str) -> float:
    if view == "truth":
        route = state.truth.routes[edge.route_id]
        if not truth_edge_open(route, edge.edge_index):
            return math.inf
        return edge.length

    belief = state.controller.route_beliefs.get(edge.route_id)
    if belief and belief.status == "blocked":
        if belief.blocked_segment_index is None or belief.blocked_segment_index == edge.edge_index:
            return math.inf
    uncertainty_penalty = 1.0
    if belief is None or belief.status == "unknown":
        uncertainty_penalty = 1.45
    elif belief.confidence < 0.65:
        uncertainty_penalty = 1.18
    return edge.length * uncertainty_penalty


def _all_graph_edges(
    state: WorkbenchState,
    *,
    mode: str,
    view: str,
    exclude_routes: set[str] | None = None,
) -> list[Edge]:
    exclude_routes = exclude_routes or set()
    result: list[Edge] = []
    for route in state.truth.routes.values():
        if route.route_id in exclude_routes or route.mode != mode:
            continue
        for edge in route_edges(route) + route_edges(route, reverse=True):
            weight = _edge_weight(state, edge, view=view)
            if math.isfinite(weight):
                result.append(
                    Edge(
                        route_id=edge.route_id,
                        edge_index=edge.edge_index,
                        start=edge.start,
                        end=edge.end,
                        length=edge.length,
                        direction=edge.direction,
                        mode=edge.mode,
                        weight=weight,
                    )
                )
    return result


def _nearest_node(position: Position, nodes: Iterable[Position]) -> Position:
    node_list = list(nodes)
    if not node_list:
        raise NavigationError("navigation graph has no nodes")
    return min(node_list, key=lambda node: distance(position, node))


def _dijkstra(
    state: WorkbenchState,
    *,
    start: Position,
    goal: Position,
    mode: str,
    view: str,
    exclude_routes: set[str] | None = None,
) -> list[Edge]:
    edges = _all_graph_edges(
        state,
        mode=mode,
        view=view,
        exclude_routes=exclude_routes,
    )
    nodes: dict[tuple[float, float], Position] = {}
    adjacency: dict[tuple[float, float], list[Edge]] = {}
    for edge in edges:
        s_key, e_key = _key(edge.start), _key(edge.end)
        nodes[s_key] = edge.start
        nodes[e_key] = edge.end
        adjacency.setdefault(s_key, []).append(edge)

    start_node = _nearest_node(start, nodes.values())
    goal_node = _nearest_node(goal, nodes.values())
    start_key, goal_key = _key(start_node), _key(goal_node)
    if start_key == goal_key:
        return []

    queue: list[tuple[float, tuple[float, float]]] = [(0.0, start_key)]
    best: dict[tuple[float, float], float] = {start_key: 0.0}
    previous: dict[tuple[float, float], tuple[tuple[float, float], Edge]] = {}

    while queue:
        cost, node_key = heapq.heappop(queue)
        if node_key == goal_key:
            break
        if cost > best.get(node_key, math.inf):
            continue
        for edge in adjacency.get(node_key, []):
            next_key = _key(edge.end)
            next_cost = cost + edge.weight
            if next_cost < best.get(next_key, math.inf):
                best[next_key] = next_cost
                previous[next_key] = (node_key, edge)
                heapq.heappush(queue, (next_cost, next_key))

    if goal_key not in previous:
        raise NavigationError(
            f"no {mode} path from ({start.x:.1f},{start.y:.1f}) "
            f"to ({goal.x:.1f},{goal.y:.1f}) in {view} graph"
        )

    path: list[Edge] = []
    cursor = goal_key
    while cursor != start_key:
        parent, edge = previous[cursor]
        path.append(edge)
        cursor = parent
    path.reverse()
    return path


def _route_direction(route: RouteTruth, target: Position) -> tuple[Position, Position, bool]:
    first, last = route.waypoints[0], route.waypoints[-1]
    if distance(last, target) <= distance(first, target):
        return first, last, False
    return last, first, True


def _preferred_route_edges(
    state: WorkbenchState,
    *,
    route_id: str,
    target: Position,
    view: str,
) -> tuple[Position, list[Edge]]:
    route = state.truth.routes[route_id]
    entry, _, reverse = _route_direction(route, target)
    edges = route_edges(route, reverse=reverse)
    usable: list[Edge] = []
    for edge in edges:
        if not math.isfinite(_edge_weight(state, edge, view=view)):
            raise NavigationError(
                f"{route.label} is not traversable in the {view} graph at edge {edge.edge_index}"
            )
        usable.append(edge)
    return entry, usable


def _to_segments(edges: list[Edge]) -> tuple[PathSegment, ...]:
    return tuple(
        PathSegment(
            route_id=edge.route_id,
            edge_index=edge.edge_index,
            direction=edge.direction,
            from_position=edge.start,
            to_position=edge.end,
            mode=edge.mode if edge.mode in {"water", "road", "air", "foot"} else "direct",
        )
        for edge in edges
    )


def plan_route_constrained_action(
    state: WorkbenchState,
    action: ActionInstance,
    *,
    view: str = "controller",
) -> NavigationPlan:
    """Build an asset path without straight-line shortcuts.

    Boats are routed on the waterway graph. If a boat is sitting at a hazard
    point on one channel and a different channel is selected, the connector
    path returns along existing graph edges to a shared junction before taking
    the new route. Drones and helicopters may travel directly because their
    mobility model is aerial.
    """

    asset = state.truth.assets[action.actor_id]
    group_id = action.parameters.get("group_id") or action.destination
    group = state.truth.groups.get(str(group_id)) if group_id else None

    if action.action_type == "verify_route" and action.route_id:
        route = state.truth.routes[action.route_id]
        target = route.blockage_position or route.waypoints[len(route.waypoints) // 2]
        segment = PathSegment(
            route_id=None,
            edge_index=None,
            direction="direct",
            from_position=asset.position,
            to_position=target,
            mode="air",
        )
        return NavigationPlan(
            points=(target,),
            segments=(segment,),
            target=target,
            total_distance=distance(asset.position, target),
            summary=f"aerial survey to {route.label}",
        )

    water_target: Position | None = None
    destination_label = ""
    if action.action_type == "dispatch_rescue_boat" and group:
        water_target = group.position
        destination_label = f"pickup at {group.label}"
    elif action.action_type == "evacuate_to_safety":
        water_target = asset.safe_position or asset.home_position
        if water_target is None:
            raise NavigationError(f"{asset.asset_id} has no declared safe position")
        destination_label = str(
            action.parameters.get("safe_location_label")
            or action.parameters.get("safe_location_id")
            or action.destination
            or "safe transfer dock"
        ).replace("_", " ")
    elif action.action_type == "return_to_base":
        if asset.home_position is None:
            raise NavigationError(f"{asset.asset_id} has no declared home position")
        water_target = asset.home_position
        destination_label = "rescue base"

    if water_target is not None and action.route_id:
        route = state.truth.routes[action.route_id]
        entry, preferred = _preferred_route_edges(
            state,
            route_id=action.route_id,
            target=water_target,
            view=view,
        )
        connector: list[Edge]
        try:
            connector = _dijkstra(
                state,
                start=asset.position,
                goal=entry,
                mode="water",
                view=view,
                exclude_routes={action.route_id},
            )
        except NavigationError:
            connector = _dijkstra(
                state,
                start=asset.position,
                goal=entry,
                mode="water",
                view=view,
            )
        edges = connector + preferred
        segments = _to_segments(edges)
        points = tuple(segment.to_position for segment in segments)
        total = sum(
            distance(segment.from_position, segment.to_position)
            for segment in segments
        )
        via = " -> ".join(
            dict.fromkeys(
                segment.route_id for segment in segments if segment.route_id
            )
        )
        return NavigationPlan(
            points=points,
            segments=segments,
            target=water_target,
            total_distance=total,
            summary=(
                f"waterway path via {via or route.label} to {destination_label}"
            ),
        )

    if group:
        mode = "air" if asset.asset_type in {"survey_drone", "helicopter"} else "foot"
        segment = PathSegment(
            route_id=None,
            edge_index=None,
            direction="direct",
            from_position=asset.position,
            to_position=group.position,
            mode=mode,
        )
        return NavigationPlan(
            points=(group.position,),
            segments=(segment,),
            target=group.position,
            total_distance=distance(asset.position, group.position),
            summary=f"{mode} path to {group.label}",
        )

    return NavigationPlan(
        points=(asset.position,),
        segments=(),
        target=asset.position,
        total_distance=0.0,
        summary="no movement",
    )
