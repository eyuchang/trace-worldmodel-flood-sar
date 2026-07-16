from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import httpx
import networkx as nx
import yaml


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


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_json(value: Any) -> str:
    return hashlib.sha256(
        canonical_json(value).encode("utf-8")
    ).hexdigest()


def query_overpass(
    endpoints: list[str],
    query: str,
    timeout_s: float,
) -> tuple[dict[str, Any], str]:
    headers = {
        "User-Agent": (
            "TRACE-JEPA-Flood-SAR-research/0.4 "
            "(cached geography builder)"
        )
    }

    errors: list[str] = []

    for endpoint in endpoints:
        try:
            with httpx.Client(
                timeout=timeout_s,
                headers=headers,
                follow_redirects=True,
            ) as client:
                response = client.post(
                    endpoint,
                    data={"data": query},
                )
                response.raise_for_status()
                return response.json(), endpoint
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{endpoint}: {exc}")

    raise RuntimeError(
        "All configured Overpass endpoints failed:\n"
        + "\n".join(errors)
    )


def network_query(
    *,
    south: float,
    west: float,
    north: float,
    east: float,
    timeout_s: int,
) -> str:
    bbox = f"{south},{west},{north},{east}"

    return f"""
[out:json][timeout:{timeout_s}][bbox:{bbox}];
(
  way["waterway"~"^(river|canal|fairway)$"];
  way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|service)$"];
);
out body;
>;
out skel qt;
""".strip()


def facility_query(
    *,
    south: float,
    west: float,
    north: float,
    east: float,
    timeout_s: int,
) -> str:
    bbox = f"{south},{west},{north},{east}"

    return f"""
[out:json][timeout:{timeout_s}][bbox:{bbox}];
(
  nwr["amenity"="hospital"];
  nwr["man_made"="pier"];
  nwr["amenity"="ferry_terminal"];
  nwr["leisure"="marina"];
  nwr["waterway"="dock"];
);
out center;
""".strip()


def node_coordinates(
    elements: Iterable[dict[str, Any]],
) -> dict[int, tuple[float, float]]:
    result: dict[int, tuple[float, float]] = {}

    for element in elements:
        if element.get("type") != "node":
            continue

        if "lon" not in element or "lat" not in element:
            continue

        result[int(element["id"])] = (
            float(element["lon"]),
            float(element["lat"]),
        )

    return result


def way_is_allowed(
    tags: dict[str, str],
    *,
    mode: str,
    accepted: set[str],
    prohibited_access: set[str],
) -> bool:
    if tags.get("access") in prohibited_access:
        return False

    if mode == "water":
        if tags.get("waterway") not in accepted:
            return False

        if tags.get("boat") in prohibited_access:
            return False

        if tags.get("motorboat") in prohibited_access:
            return False

        return True

    return tags.get("highway") in accepted


def build_graph(
    *,
    elements: list[dict[str, Any]],
    mode: str,
    accepted: set[str],
    prohibited_access: set[str],
) -> nx.Graph | nx.DiGraph:
    coordinates = node_coordinates(elements)

    graph: nx.Graph | nx.DiGraph

    if mode == "road":
        graph = nx.DiGraph()
    else:
        graph = nx.Graph()

    for element in elements:
        if element.get("type") != "way":
            continue

        tags = {
            str(key): str(value)
            for key, value in element.get("tags", {}).items()
        }

        if not way_is_allowed(
            tags,
            mode=mode,
            accepted=accepted,
            prohibited_access=prohibited_access,
        ):
            continue

        node_ids = [
            int(node_id)
            for node_id in element.get("nodes", [])
            if int(node_id) in coordinates
        ]

        if len(node_ids) < 2:
            continue

        for node_id in node_ids:
            longitude, latitude = coordinates[node_id]

            graph.add_node(
                str(node_id),
                longitude=longitude,
                latitude=latitude,
            )

        for edge_index, (first, second) in enumerate(
            zip(node_ids[:-1], node_ids[1:])
        ):
            first_point = coordinates[first]
            second_point = coordinates[second]

            attributes = {
                "edge_id": (
                    f"osm-{mode}-{element['id']}-{edge_index}"
                ),
                "osm_way_id": int(element["id"]),
                "length_m": haversine_m(
                    first_point,
                    second_point,
                ),
                "mode": mode,
                "name": tags.get("name"),
                "tags": tags,
                "open": True,
                "congestion": 0.0,
                "closure_reason": None,
                "coordinates": [
                    list(first_point),
                    list(second_point),
                ],
            }

            first_id = str(first)
            second_id = str(second)

            if mode == "water":
                graph.add_edge(
                    first_id,
                    second_id,
                    **attributes,
                )
                continue

            oneway = tags.get("oneway", "").lower()

            if oneway == "-1":
                graph.add_edge(
                    second_id,
                    first_id,
                    **attributes,
                )
            elif oneway in {"yes", "1", "true"}:
                graph.add_edge(
                    first_id,
                    second_id,
                    **attributes,
                )
            else:
                graph.add_edge(
                    first_id,
                    second_id,
                    **attributes,
                )
                graph.add_edge(
                    second_id,
                    first_id,
                    **attributes,
                )

    return retain_largest_component(graph)


def retain_largest_component(
    graph: nx.Graph | nx.DiGraph,
) -> nx.Graph | nx.DiGraph:
    if graph.number_of_nodes() == 0:
        raise RuntimeError("Downloaded navigation graph is empty.")

    if graph.is_directed():
        components = list(
            nx.weakly_connected_components(graph)
        )
    else:
        components = list(
            nx.connected_components(graph)
        )

    largest = max(components, key=len)
    return graph.subgraph(largest).copy()


def facility_point(
    element: dict[str, Any],
) -> tuple[float, float] | None:
    if "lon" in element and "lat" in element:
        return (
            float(element["lon"]),
            float(element["lat"]),
        )

    center = element.get("center")

    if center and "lon" in center and "lat" in center:
        return (
            float(center["lon"]),
            float(center["lat"]),
        )

    return None


def parse_facilities(
    elements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    for element in elements:
        point = facility_point(element)

        if point is None:
            continue

        tags = {
            str(key): str(value)
            for key, value in element.get("tags", {}).items()
        }

        if tags.get("amenity") == "hospital":
            kind = "hospital"
        elif tags.get("man_made") == "pier":
            kind = "pier"
        elif tags.get("amenity") == "ferry_terminal":
            kind = "ferry_terminal"
        elif tags.get("leisure") == "marina":
            kind = "marina"
        elif tags.get("waterway") == "dock":
            kind = "dock"
        else:
            continue

        result.append(
            {
                "facility_id": (
                    f"osm-{element['type']}-{element['id']}"
                ),
                "osm_type": element["type"],
                "osm_id": int(element["id"]),
                "kind": kind,
                "name": tags.get("name")
                or f"Unnamed {kind}",
                "longitude": point[0],
                "latitude": point[1],
                "tags": tags,
            }
        )

    return result


def nearest_node(
    graph: nx.Graph | nx.DiGraph,
    point: tuple[float, float],
) -> tuple[str, float]:
    if graph.number_of_nodes() == 0:
        raise RuntimeError("Navigation graph has no nodes.")

    node_id = min(
        graph.nodes,
        key=lambda candidate: haversine_m(
            point,
            (
                float(graph.nodes[candidate]["longitude"]),
                float(graph.nodes[candidate]["latitude"]),
            ),
        ),
    )

    node_point = (
        float(graph.nodes[node_id]["longitude"]),
        float(graph.nodes[node_id]["latitude"]),
    )

    return node_id, haversine_m(point, node_point)


def path_exists(
    graph: nx.Graph | nx.DiGraph,
    start: str,
    end: str,
) -> bool:
    try:
        return nx.has_path(graph, start, end)
    except nx.NodeNotFound:
        return False


def graph_node_record(
    graph: nx.Graph | nx.DiGraph,
    node_id: str,
) -> dict[str, Any]:
    attributes = graph.nodes[node_id]

    return {
        "node_id": node_id,
        "longitude": float(attributes["longitude"]),
        "latitude": float(attributes["latitude"]),
    }


def choose_hospital_and_transfer_port(
    *,
    facilities: list[dict[str, Any]],
    water_graph: nx.Graph,
    road_graph: nx.DiGraph,
) -> tuple[dict[str, Any], dict[str, Any]]:
    hospitals = [
        facility
        for facility in facilities
        if facility["kind"] == "hospital"
    ]

    if not hospitals:
        raise RuntimeError(
            "No hospital was found in the configured area."
        )

    ports = [
        facility
        for facility in facilities
        if facility["kind"]
        in {
            "pier",
            "ferry_terminal",
            "marina",
            "dock",
        }
    ]

    best: tuple[
        float,
        dict[str, Any],
        dict[str, Any] | None,
        str,
        str,
        str,
    ] | None = None

    for hospital in hospitals:
        hospital_point = (
            hospital["longitude"],
            hospital["latitude"],
        )

        hospital_road_node, hospital_road_snap = nearest_node(
            road_graph,
            hospital_point,
        )

        candidate_ports = ports or [
            {
                "facility_id": "derived-transfer-port",
                "kind": "derived_water_transfer",
                "name": "Derived River Transfer Port",
                "longitude": hospital_point[0],
                "latitude": hospital_point[1],
            }
        ]

        for port in candidate_ports:
            port_point = (
                port["longitude"],
                port["latitude"],
            )

            water_node, water_snap = nearest_node(
                water_graph,
                port_point,
            )

            water_point = (
                float(water_graph.nodes[water_node]["longitude"]),
                float(water_graph.nodes[water_node]["latitude"]),
            )

            transfer_road_node, transfer_road_snap = nearest_node(
                road_graph,
                water_point,
            )

            if not path_exists(
                road_graph,
                transfer_road_node,
                hospital_road_node,
            ):
                continue

            score = (
                haversine_m(hospital_point, port_point)
                + water_snap
                + transfer_road_snap
                + hospital_road_snap
            )

            candidate = (
                score,
                hospital,
                None if port["facility_id"] == "derived-transfer-port" else port,
                water_node,
                transfer_road_node,
                hospital_road_node,
            )

            if best is None or candidate[0] < best[0]:
                best = candidate

    if best is None:
        raise RuntimeError(
            "Could not select a connected hospital/port pair."
        )

    (
        _,
        hospital,
        port,
        water_node,
        transfer_road_node,
        hospital_road_node,
    ) = best

    water_point = (
        float(water_graph.nodes[water_node]["longitude"]),
        float(water_graph.nodes[water_node]["latitude"]),
    )

    hospital_result = {
        **hospital,
        "road_node": hospital_road_node,
    }

    transfer_result = {
        "facility_id": (
            port["facility_id"]
            if port
            else "derived-transfer-port"
        ),
        "kind": (
            port["kind"]
            if port
            else "derived_water_transfer"
        ),
        "name": (
            port["name"]
            if port
            else "Derived River Transfer Port"
        ),
        "source_facility": port,
        "longitude": water_point[0],
        "latitude": water_point[1],
        "water_node": water_node,
        "road_node": transfer_road_node,
        "derived": port is None,
    }

    return hospital_result, transfer_result


def connected_nodes(
    graph: nx.Graph | nx.DiGraph,
    anchor: str,
) -> set[str]:
    undirected = graph.to_undirected()

    return set(
        nx.node_connected_component(
            undirected,
            anchor,
        )
    )


def choose_spread_nodes(
    *,
    graph: nx.Graph | nx.DiGraph,
    anchor: str,
    count: int,
    minimum_spacing_m: float,
) -> list[str]:
    available = connected_nodes(graph, anchor)
    selected = [anchor]

    while len(selected) < count:
        remaining = available.difference(selected)

        if not remaining:
            break

        def separation(candidate: str) -> float:
            point = (
                float(graph.nodes[candidate]["longitude"]),
                float(graph.nodes[candidate]["latitude"]),
            )

            return min(
                haversine_m(
                    point,
                    (
                        float(graph.nodes[existing]["longitude"]),
                        float(graph.nodes[existing]["latitude"]),
                    ),
                )
                for existing in selected
            )

        candidate = max(remaining, key=separation)

        if separation(candidate) < minimum_spacing_m:
            break

        selected.append(candidate)

    while len(selected) < count:
        selected.append(selected[-1])

    return selected


def farthest_node(
    graph: nx.Graph | nx.DiGraph,
    anchor: str,
    *,
    exclude: set[str] | None = None,
) -> str:
    exclude = exclude or set()

    candidates = [
        node_id
        for node_id in connected_nodes(graph, anchor)
        if node_id not in exclude
    ]

    anchor_point = (
        float(graph.nodes[anchor]["longitude"]),
        float(graph.nodes[anchor]["latitude"]),
    )

    return max(
        candidates,
        key=lambda node_id: haversine_m(
            anchor_point,
            (
                float(graph.nodes[node_id]["longitude"]),
                float(graph.nodes[node_id]["latitude"]),
            ),
        ),
    )


def serialize_graph(
    graph: nx.Graph | nx.DiGraph,
    *,
    mode: str,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "directed": graph.is_directed(),
        "nodes": [
            {
                "node_id": str(node_id),
                "longitude": float(attributes["longitude"]),
                "latitude": float(attributes["latitude"]),
            }
            for node_id, attributes in graph.nodes(data=True)
        ],
        "edges": [
            {
                "start": str(start),
                "end": str(end),
                **attributes,
            }
            for start, end, attributes
            in graph.edges(data=True)
        ],
    }


def graph_geojson(
    graph: nx.Graph | nx.DiGraph,
) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": attributes["edge_id"],
                "geometry": {
                    "type": "LineString",
                    "coordinates": attributes["coordinates"],
                },
                "properties": {
                    "edge_id": attributes["edge_id"],
                    "mode": attributes["mode"],
                    "name": attributes.get("name"),
                    "open": bool(attributes.get("open", True)),
                    "congestion": float(
                        attributes.get("congestion", 0.0)
                    ),
                },
            }
            for _, _, attributes in graph.edges(data=True)
        ],
    }


def facilities_geojson(
    facilities: list[dict[str, Any]],
    hospital: dict[str, Any],
    transfer_port: dict[str, Any],
    boat_bases: list[dict[str, Any]],
    drone_bases: list[dict[str, Any]],
) -> dict[str, Any]:
    display = [
        *facilities,
        {
            **hospital,
            "kind": "selected_hospital",
        },
        {
            **transfer_port,
            "kind": "selected_transfer_port",
        },
        *[
            {
                **base,
                "facility_id": f"boat-base-{index + 1}",
                "kind": "boat_base",
                "name": f"Boat Base {index + 1}",
            }
            for index, base in enumerate(boat_bases)
        ],
        *[
            {
                **base,
                "facility_id": f"drone-base-{index + 1}",
                "kind": "drone_base",
                "name": f"Drone Base {index + 1}",
            }
            for index, base in enumerate(drone_bases)
        ],
    ]

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        item["longitude"],
                        item["latitude"],
                    ],
                },
                "properties": {
                    key: value
                    for key, value in item.items()
                    if key not in {"longitude", "latitude", "tags"}
                },
            }
            for item in display
        ],
    }


def write_json(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {path}")


def build_geography(config_path: Path) -> Path:
    config = yaml.safe_load(
        config_path.read_text(encoding="utf-8")
    )

    output_directory = Path(
        config["output_directory"]
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    bbox = config["bbox"]
    overpass = config["overpass"]

    network_payload, network_endpoint = query_overpass(
        list(overpass["endpoints"]),
        network_query(
            south=float(bbox["south"]),
            west=float(bbox["west"]),
            north=float(bbox["north"]),
            east=float(bbox["east"]),
            timeout_s=int(overpass["timeout_s"]),
        ),
        timeout_s=float(overpass["timeout_s"]) + 30.0,
    )

    facility_payload, facility_endpoint = query_overpass(
        list(overpass["endpoints"]),
        facility_query(
            south=float(bbox["south"]),
            west=float(bbox["west"]),
            north=float(bbox["north"]),
            east=float(bbox["east"]),
            timeout_s=int(overpass["timeout_s"]),
        ),
        timeout_s=float(overpass["timeout_s"]) + 30.0,
    )

    water_graph = build_graph(
        elements=list(network_payload["elements"]),
        mode="water",
        accepted=set(
            config["water"]["accepted_waterway_tags"]
        ),
        prohibited_access=set(
            config["water"]["prohibited_access_values"]
        ),
    )

    road_graph = build_graph(
        elements=list(network_payload["elements"]),
        mode="road",
        accepted=set(
            config["road"]["accepted_highway_tags"]
        ),
        prohibited_access=set(
            config["road"]["prohibited_access_values"]
        ),
    )

    facilities = parse_facilities(
        list(facility_payload["elements"])
    )

    hospital, transfer_port = choose_hospital_and_transfer_port(
        facilities=facilities,
        water_graph=water_graph,
        road_graph=road_graph,
    )

    boat_base_nodes = choose_spread_nodes(
        graph=water_graph,
        anchor=transfer_port["water_node"],
        count=int(config["fleet"]["boat_count"]),
        minimum_spacing_m=float(
            config["fleet"]["minimum_base_spacing_m"]
        ),
    )

    drone_base_nodes = choose_spread_nodes(
        graph=water_graph,
        anchor=transfer_port["water_node"],
        count=int(config["fleet"]["drone_count"]),
        minimum_spacing_m=0.65
        * float(config["fleet"]["minimum_base_spacing_m"]),
    )

    boat_bases = [
        graph_node_record(water_graph, node_id)
        for node_id in boat_base_nodes
    ]

    drone_bases = [
        graph_node_record(water_graph, node_id)
        for node_id in drone_base_nodes
    ]

    first_demo_node = farthest_node(
        water_graph,
        transfer_port["water_node"],
    )

    second_demo_node = farthest_node(
        water_graph,
        first_demo_node,
        exclude={transfer_port["water_node"]},
    )

    scenario = {
        "scenario_id": config["scenario_id"],
        "bbox": bbox,
        "camera": config["camera"],
        "hospital": hospital,
        "transfer_port": transfer_port,
        "boat_bases": boat_bases,
        "drone_bases": drone_bases,
        "ambulance_bases": [
            {
                "node_id": hospital["road_node"],
                "longitude": hospital["longitude"],
                "latitude": hospital["latitude"],
            }
            for _ in range(int(config["fleet"]["ambulance_count"]))
        ],
        "demo_water_nodes": [
            first_demo_node,
            second_demo_node,
        ],
        "water_maximum_snap_m": float(
            config["water"]["maximum_incident_snap_m"]
        ),
        "road_maximum_snap_m": float(
            config["road"]["maximum_incident_snap_m"]
        ),
        "source": {
            "provider": "OpenStreetMap contributors",
            "query_system": "Overpass API",
            "network_endpoint": network_endpoint,
            "facility_endpoint": facility_endpoint,
            "built_at_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "network_payload_sha256": sha256_json(
                network_payload
            ),
            "facility_payload_sha256": sha256_json(
                facility_payload
            ),
            "configuration_sha256": hashlib.sha256(
                config_path.read_bytes()
            ).hexdigest(),
        },
    }

    write_json(
        output_directory / "osm_network_raw.json",
        network_payload,
    )

    write_json(
        output_directory / "osm_facilities_raw.json",
        facility_payload,
    )

    write_json(
        output_directory / "water_graph.json",
        serialize_graph(water_graph, mode="water"),
    )

    write_json(
        output_directory / "road_graph.json",
        serialize_graph(road_graph, mode="road"),
    )

    write_json(
        output_directory / "waterways.geojson",
        graph_geojson(water_graph),
    )

    write_json(
        output_directory / "roads.geojson",
        graph_geojson(road_graph),
    )

    write_json(
        output_directory / "facilities.geojson",
        facilities_geojson(
            facilities,
            hospital,
            transfer_port,
            boat_bases,
            drone_bases,
        ),
    )

    write_json(
        output_directory / "scenario.json",
        scenario,
    )

    print()
    print(
        f"Water nodes: {water_graph.number_of_nodes()}"
    )
    print(
        f"Water edges: {water_graph.number_of_edges()}"
    )
    print(
        f"Road nodes: {road_graph.number_of_nodes()}"
    )
    print(
        f"Road edges: {road_graph.number_of_edges()}"
    )
    print(f"Hospital: {hospital['name']}")
    print(f"Transfer port: {transfer_port['name']}")

    return output_directory


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Download and cache the real OpenStreetMap geography "
            "used by the TRACE-JEPA D0.4 workbench."
        )
    )

    parser.add_argument(
        "--config",
        default=(
            "configs/geography/"
            "antioch_delta_real_v1.yaml"
        ),
    )

    args = parser.parse_args()

    build_geography(Path(args.config))


if __name__ == "__main__":
    main()
