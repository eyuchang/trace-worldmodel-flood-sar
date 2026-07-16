from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import networkx as nx


EARTH_RADIUS_M = 6_371_008.8


def haversine_m(
    first: tuple[float, float],
    second: tuple[float, float],
) -> float:
    lon1, lat1 = map(math.radians, first)
    lon2, lat2 = map(math.radians, second)

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    value = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2.0) ** 2
    )

    return 2.0 * EARTH_RADIUS_M * math.asin(
        min(1.0, math.sqrt(value))
    )


class RealNavigationGraph:
    def __init__(
        self,
        payload: dict[str, Any],
    ) -> None:
        self.mode = str(payload["mode"])
        self.directed = bool(payload["directed"])

        self.graph: nx.Graph | nx.DiGraph

        if self.directed:
            self.graph = nx.DiGraph()
        else:
            self.graph = nx.Graph()

        self.nodes: dict[
            str,
            tuple[float, float],
        ] = {}

        for node in payload["nodes"]:
            node_id = str(node["node_id"])

            point = (
                float(node["longitude"]),
                float(node["latitude"]),
            )

            self.nodes[node_id] = point

            self.graph.add_node(
                node_id,
                longitude=point[0],
                latitude=point[1],
            )

        for edge in payload["edges"]:
            attributes = {
                key: value
                for key, value in edge.items()
                if key not in {"start", "end"}
            }

            self.graph.add_edge(
                str(edge["start"]),
                str(edge["end"]),
                **attributes,
            )

    def nearest_node(
        self,
        point: tuple[float, float],
    ) -> tuple[str, float]:
        if not self.nodes:
            raise RuntimeError(
                f"{self.mode} graph contains no nodes."
            )

        node_id = min(
            self.nodes,
            key=lambda candidate: haversine_m(
                point,
                self.nodes[candidate],
            ),
        )

        return (
            node_id,
            haversine_m(
                point,
                self.nodes[node_id],
            ),
        )

    def node_point(
        self,
        node_id: str,
    ) -> tuple[float, float]:
        return self.nodes[node_id]

    def route(
        self,
        start_node: str,
        goal_node: str,
    ) -> list[str] | None:
        def edge_weight(
            start: str,
            end: str,
            attributes: dict[str, Any],
        ) -> float:
            if not bool(attributes.get("open", True)):
                return math.inf

            congestion = float(
                attributes.get("congestion", 0.0)
            )

            return float(
                attributes.get("length_m", 1.0)
            ) * (1.0 + 2.0 * congestion)

        try:
            path = nx.shortest_path(
                self.graph,
                start_node,
                goal_node,
                weight=edge_weight,
            )

            if len(path) < 1:
                return None

            return [str(node_id) for node_id in path]

        except (
            nx.NetworkXNoPath,
            nx.NodeNotFound,
        ):
            return None

    def route_points(
        self,
        current_point: tuple[float, float],
        goal_node: str,
    ) -> tuple[
        list[str],
        list[tuple[float, float]],
    ] | None:
        start_node, _ = self.nearest_node(
            current_point
        )

        node_path = self.route(
            start_node,
            goal_node,
        )

        if not node_path:
            return None

        points = [current_point]

        for node_id in node_path:
            point = self.node_point(node_id)

            if haversine_m(points[-1], point) > 0.5:
                points.append(point)

        return node_path, points

    def close_edge(
        self,
        edge_id: str,
        reason: str,
    ) -> bool:
        for _, _, attributes in self.graph.edges(
            data=True
        ):
            if attributes.get("edge_id") == edge_id:
                attributes["open"] = False
                attributes["closure_reason"] = reason
                return True

        return False

    def open_edge(
        self,
        edge_id: str,
    ) -> bool:
        for _, _, attributes in self.graph.edges(
            data=True
        ):
            if attributes.get("edge_id") == edge_id:
                attributes["open"] = True
                attributes["closure_reason"] = None
                return True

        return False

    def edge_statuses(self) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result: list[dict[str, Any]] = []

        for _, _, attributes in self.graph.edges(data=True):
            edge_id = str(attributes["edge_id"])

            if edge_id in seen:
                continue

            seen.add(edge_id)

            result.append(
                {
                    "edge_id": edge_id,
                    "open": bool(
                        attributes.get("open", True)
                    ),
                    "congestion": float(
                        attributes.get("congestion", 0.0)
                    ),
                    "closure_reason": attributes.get(
                        "closure_reason"
                    ),
                }
            )

        return result


@dataclass(frozen=True)
class RealGeography:
    water: RealNavigationGraph
    road: RealNavigationGraph
    scenario: dict[str, Any]
    waterways_geojson: dict[str, Any]
    roads_geojson: dict[str, Any]
    facilities_geojson: dict[str, Any]


def load_real_geography(
    root: str | Path = (
        "data/geography/"
        "antioch_delta_real_v1"
    ),
) -> RealGeography:
    directory = Path(root)

    def read_json(filename: str) -> dict[str, Any]:
        path = directory / filename

        if not path.exists():
            raise FileNotFoundError(
                f"Missing geography artifact: {path}. "
                "Run `trace-jepa-build-geography` first."
            )

        return json.loads(
            path.read_text(encoding="utf-8")
        )

    return RealGeography(
        water=RealNavigationGraph(
            read_json("water_graph.json")
        ),
        road=RealNavigationGraph(
            read_json("road_graph.json")
        ),
        scenario=read_json("scenario.json"),
        waterways_geojson=read_json(
            "waterways.geojson"
        ),
        roads_geojson=read_json(
            "roads.geojson"
        ),
        facilities_geojson=read_json(
            "facilities.geojson"
        ),
    )
