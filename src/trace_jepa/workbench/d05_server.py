from __future__ import annotations

import argparse
import asyncio
import math
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import networkx as nx
import uvicorn
from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from trace_jepa.workbench.d04_server import (
    Asset,
    D04Engine,
    Incident,
    MissionTask,
    canonical_json,
)
from trace_jepa.workbench.real_geography import haversine_m


STATIC_DIR = Path(__file__).with_name("d05_static")


@dataclass
class TransferDock:
    dock_id: str
    name: str
    longitude: float
    latitude: float
    water_node: str
    road_node: str
    source: str
    road_from_hospital_m: float
    road_to_hospital_m: float
    water_road_snap_m: float

    @property
    def facility_id(self) -> str:
        return self.dock_id

    def __getitem__(self, key: str) -> Any:
        if key == "facility_id":
            return self.dock_id
        return getattr(self, key)


@dataclass
class ResponsePreparation:
    incident_id: str
    asset_id: str
    asset_kind: str
    probable_mode: str
    prepared_at: float
    route_distance_m: float
    expected_ready_at: float
    status: str = "prepared"
    activated_at: float | None = None
    released_at: float | None = None


@dataclass
class TaskTiming:
    task_id: str
    incident_id: str
    task_kind: str
    asset_id: str
    scheduled_at: float
    dispatched_at: float
    expected_arrival_at: float
    actual_arrival_at: float | None = None
    completed_at: float | None = None
    status: str = "enroute"


@dataclass
class ScheduleEntry:
    schedule_id: str
    incident_id: str
    stage: str
    asset_id: str | None
    planned_at: float
    expected_start_at: float
    expected_finish_at: float | None
    status: str = "planned"


@dataclass
class TransferSchedule:
    transfer_id: str
    incident_id: str
    dock_id: str
    dock_name: str
    boat_id: str
    ambulance_id: str | None
    selected_at: float
    boat_eta_s: float
    ambulance_eta_s: float
    expected_rendezvous_at: float
    expected_hospital_arrival_at: float
    actual_boat_arrival_at: float | None = None
    actual_ambulance_arrival_at: float | None = None
    handoff_started_at: float | None = None
    handoff_completed_at: float | None = None
    status: str = "scheduled"


class D05Engine(D04Engine):
    """D0.5 adds temporal overlap, dynamic docks, and schedule traces."""

    def reset(self) -> None:
        super().reset()

        self.transfer_ports = self._derive_transfer_ports()
        self.preparations: dict[str, ResponsePreparation] = {}
        self.readiness: dict[str, dict[str, Any]] = {}
        self.schedule_entries: list[ScheduleEntry] = []
        self.task_timings: dict[str, TaskTiming] = {}
        self.transfer_schedules: dict[str, TransferSchedule] = {}
        self.transfer_plans: dict[str, dict[str, Any]] = {}
        self.schedule_events: list[dict[str, Any]] = []
        self.asset_docks: dict[str, str] = {}
        self.asset_current_dock = self.asset_docks

        self._place_idle_fleet_at_real_docks()

        self._message(
            "TEMPORAL_SCHEDULER_READY",
            (
                f"Temporal scheduler loaded {len(self.transfer_ports)} "
                "candidate river docks."
            ),
        )

    def _spaced_transfer_docks(self, count: int) -> list[TransferDock]:
        if not self.transfer_ports:
            return []

        selected = [self.transfer_ports[0]]

        while len(selected) < min(count, len(self.transfer_ports)):
            remaining = [
                dock for dock in self.transfer_ports if dock not in selected
            ]

            if not remaining:
                break

            selected.append(
                max(
                    remaining,
                    key=lambda candidate: min(
                        haversine_m(
                            (candidate.longitude, candidate.latitude),
                            (existing.longitude, existing.latitude),
                        )
                        for existing in selected
                    ),
                )
            )

        while len(selected) < count:
            selected.append(selected[-1])

        return selected

    def _place_idle_fleet_at_real_docks(self) -> None:
        boat_docks = self._spaced_transfer_docks(2)
        drone_docks = self._spaced_transfer_docks(3)

        boats = sorted(
            (asset for asset in self.assets.values() if asset.kind == "boat"),
            key=lambda asset: asset.asset_id,
        )
        drones = sorted(
            (asset for asset in self.assets.values() if asset.kind == "drone"),
            key=lambda asset: asset.asset_id,
        )

        for asset, dock in zip(boats, boat_docks):
            asset.point = (dock.longitude, dock.latitude)
            asset.home_longitude = dock.longitude
            asset.home_latitude = dock.latitude
            asset.home_node = dock.water_node
            asset.state = "standby_at_dock"
            self.asset_docks[asset.asset_id] = dock.dock_id

        for asset, dock in zip(drones, drone_docks):
            asset.point = (dock.longitude, dock.latitude)
            asset.home_longitude = dock.longitude
            asset.home_latitude = dock.latitude
            asset.home_node = dock.water_node
            asset.state = "standby_at_dock"
            self.asset_docks[asset.asset_id] = dock.dock_id

    # ------------------------------------------------------------------
    # Geography and timing helpers
    # ------------------------------------------------------------------

    def _graph_path_distance(
        self,
        graph,
        start_node: str,
        goal_node: str,
    ) -> float | None:
        node_path = graph.route(start_node, goal_node)

        if not node_path:
            return None

        distance = 0.0

        for first, second in zip(node_path[:-1], node_path[1:]):
            attributes = graph.graph.get_edge_data(first, second)

            if not attributes or not bool(attributes.get("open", True)):
                return None

            distance += float(attributes.get("length_m", 0.0))

        return distance

    def _route_distance_from_point(
        self,
        graph,
        point: tuple[float, float],
        goal_node: str,
    ) -> float | None:
        start_node, snap_distance = graph.nearest_node(point)
        graph_distance = self._graph_path_distance(
            graph,
            start_node,
            goal_node,
        )

        if graph_distance is None:
            return None

        return snap_distance + graph_distance

    def _route_distance_for_asset(self, asset: Asset) -> float:
        if len(asset.route_points) <= asset.route_index:
            return 0.0

        points = [
            asset.point,
            *asset.route_points[asset.route_index :],
        ]

        return sum(
            haversine_m(first, second)
            for first, second in zip(points[:-1], points[1:])
        )

    def _travel_time_s(self, distance_m: float, asset: Asset) -> float:
        return distance_m / max(0.1, self._movement_speed(asset))

    def _derive_transfer_ports(self) -> list[TransferDock]:
        road_graph = self.road_graph.graph
        hospital_node = str(self.hospital["road_node"])

        from_hospital = nx.single_source_dijkstra_path_length(
            road_graph,
            hospital_node,
            weight="length_m",
        )

        reverse_graph = road_graph.reverse(copy=False)
        to_hospital = nx.single_source_dijkstra_path_length(
            reverse_graph,
            hospital_node,
            weight="length_m",
        )

        candidates: list[TransferDock] = []
        seen_water_nodes: set[str] = set()

        def add_candidate(
            *,
            dock_id: str,
            name: str,
            point: tuple[float, float],
            source: str,
        ) -> None:
            water_node, water_snap = self.water_graph.nearest_node(point)
            water_point = self.water_graph.node_point(water_node)
            road_node, road_snap = self.road_graph.nearest_node(water_point)

            if road_snap > 650.0:
                return

            if road_node not in from_hospital or road_node not in to_hospital:
                return

            if water_node in seen_water_nodes:
                return

            seen_water_nodes.add(water_node)

            candidates.append(
                TransferDock(
                    dock_id=dock_id,
                    name=name,
                    longitude=water_point[0],
                    latitude=water_point[1],
                    water_node=water_node,
                    road_node=road_node,
                    source=source,
                    road_from_hospital_m=float(from_hospital[road_node]),
                    road_to_hospital_m=float(to_hospital[road_node]),
                    water_road_snap_m=float(road_snap + water_snap),
                )
            )

        for feature in self.geography.facilities_geojson.get("features", []):
            properties = feature.get("properties", {})
            kind = str(properties.get("kind", ""))

            if kind not in {
                "pier",
                "ferry_terminal",
                "marina",
                "dock",
                "selected_transfer_port",
            }:
                continue

            coordinates = feature.get("geometry", {}).get("coordinates")

            if not coordinates or len(coordinates) < 2:
                continue

            add_candidate(
                dock_id=str(
                    properties.get("facility_id")
                    or properties.get("id")
                    or f"facility-dock-{len(candidates) + 1}"
                ),
                name=str(properties.get("name") or "Mapped river dock"),
                point=(float(coordinates[0]), float(coordinates[1])),
                source="osm_facility",
            )

        # Derive additional water/road handoff points without O(N*M) scans.
        water_nodes = list(self.water_graph.nodes.items())
        stride = max(1, len(water_nodes) // 240)

        derived: list[tuple[float, str, tuple[float, float]]] = []

        for index, (water_node, water_point) in enumerate(water_nodes):
            if index % stride != 0 or water_node in seen_water_nodes:
                continue

            road_node, road_snap = self.road_graph.nearest_node(water_point)

            if road_snap > 420.0:
                continue

            if road_node not in from_hospital or road_node not in to_hospital:
                continue

            score = (
                float(from_hospital[road_node])
                + float(to_hospital[road_node])
                + 2.0 * float(road_snap)
            )

            derived.append((score, water_node, water_point))

        derived.sort(key=lambda item: item[0])

        for _, water_node, water_point in derived:
            if len(candidates) >= 8:
                break

            if any(
                haversine_m(
                    (existing.longitude, existing.latitude),
                    water_point,
                )
                < 950.0
                for existing in candidates
            ):
                continue

            add_candidate(
                dock_id=f"derived-dock-{len(candidates) + 1}",
                name=f"Derived transfer dock {len(candidates) + 1}",
                point=water_point,
                source="derived_water_road_handoff",
            )

        # Preserve the D0.4 selected port as a guaranteed fallback.
        if not candidates:
            add_candidate(
                dock_id=str(self.transfer_port["facility_id"]),
                name=str(self.transfer_port["name"]),
                point=(
                    float(self.transfer_port["longitude"]),
                    float(self.transfer_port["latitude"]),
                ),
                source="d04_fallback",
            )

        candidates.sort(
            key=lambda dock: (
                dock.road_from_hospital_m + dock.road_to_hospital_m,
                dock.water_road_snap_m,
            )
        )

        return candidates[:8]

    # ------------------------------------------------------------------
    # Preparation and schedule logging
    # ------------------------------------------------------------------

    def _free_assets(self, kind: str) -> list[Asset]:
        return [
            asset
            for asset in self.assets.values()
            if (
                asset.kind == kind
                and not asset.grounded
                and asset.current_task_id is None
                and asset.pending_task_id is None
                and asset.state in {"standby", "standby_at_dock"}
            )
        ]

    def _probable_mode(self, incident: Incident) -> str | None:
        if incident.reported_access_hint in {"water", "land"}:
            return incident.reported_access_hint

        _, water_distance = self.water_graph.nearest_node(incident.point)
        _, road_distance = self.road_graph.nearest_node(incident.point)

        water_limit = float(
            self.geography.scenario["water_maximum_snap_m"]
        )
        road_limit = float(
            self.geography.scenario["road_maximum_snap_m"]
        )

        water_score = water_distance / max(1.0, water_limit)
        road_score = road_distance / max(1.0, road_limit)

        if min(water_score, road_score) > 1.5:
            return None

        return "water" if water_score <= road_score else "land"

    def _soft_prepare_asset(
        self,
        incident: Incident,
        kind: str,
    ) -> tuple[str | None, float | None, float | None]:
        assets = self._free_assets(kind)

        if not assets:
            return None, None, None

        if kind == "boat":
            destination_node, _ = self.water_graph.nearest_node(incident.point)
            graph = self.water_graph
        else:
            destination_node, _ = self.road_graph.nearest_node(incident.point)
            graph = self.road_graph

        scored: list[tuple[float, Asset]] = []

        for asset in assets:
            distance = self._route_distance_from_point(
                graph,
                asset.point,
                destination_node,
            )

            if distance is not None:
                scored.append((distance, asset))

        if not scored:
            return None, None, None

        distance, asset = min(scored, key=lambda item: item[0])
        ready_at = self.simulation_time + min(
            12.0,
            max(2.0, 0.003 * distance),
        )

        return asset.asset_id, distance, ready_at

    def _prepare_parallel_readiness(self, incident: Incident) -> None:
        survey_task = next(
            (
                task
                for task in self.tasks.values()
                if task.incident_id == incident.incident_id
                and task.task_kind == "survey"
                and task.status == "active"
            ),
            None,
        )

        drone_asset_id = (
            survey_task.assigned_asset_id
            if survey_task is not None
            else None
        )

        boat_id, boat_distance, boat_ready_at = self._soft_prepare_asset(
            incident,
            "boat",
        )
        ambulance_id, ambulance_distance, ambulance_ready_at = (
            self._soft_prepare_asset(incident, "ambulance")
        )

        probable_mode = self._probable_mode(incident)
        primary_asset_id = boat_id if probable_mode == "water" else ambulance_id
        primary_kind = "boat" if probable_mode == "water" else "ambulance"
        primary_distance = boat_distance if probable_mode == "water" else ambulance_distance
        primary_ready_at = boat_ready_at if probable_mode == "water" else ambulance_ready_at

        if primary_asset_id and primary_distance is not None and primary_ready_at is not None:
            self.preparations[incident.incident_id] = ResponsePreparation(
                incident_id=incident.incident_id,
                asset_id=primary_asset_id,
                asset_kind=primary_kind,
                probable_mode=probable_mode or "unknown",
                prepared_at=self.simulation_time,
                route_distance_m=primary_distance,
                expected_ready_at=primary_ready_at,
            )

        readiness = {
            "incident_id": incident.incident_id,
            "drone_asset_id": drone_asset_id,
            "boat_asset_id": boat_id,
            "ambulance_asset_id": ambulance_id,
            "prepared_at": self.simulation_time,
            "boat_ready_at": boat_ready_at,
            "ambulance_ready_at": ambulance_ready_at,
            "probable_mode": probable_mode,
        }
        self.readiness[incident.incident_id] = readiness

        self.schedule_entries.extend(
            [
                ScheduleEntry(
                    schedule_id=f"readiness-drone-{incident.incident_id}",
                    incident_id=incident.incident_id,
                    stage="reconnaissance",
                    asset_id=drone_asset_id,
                    planned_at=self.simulation_time,
                    expected_start_at=self.simulation_time,
                    expected_finish_at=None,
                    status="active" if drone_asset_id else "queued",
                ),
                ScheduleEntry(
                    schedule_id=f"readiness-boat-{incident.incident_id}",
                    incident_id=incident.incident_id,
                    stage="boat_readiness",
                    asset_id=boat_id,
                    planned_at=self.simulation_time,
                    expected_start_at=self.simulation_time,
                    expected_finish_at=boat_ready_at,
                    status="prepared" if boat_id else "unavailable",
                ),
                ScheduleEntry(
                    schedule_id=f"readiness-ambulance-{incident.incident_id}",
                    incident_id=incident.incident_id,
                    stage="ambulance_readiness",
                    asset_id=ambulance_id,
                    planned_at=self.simulation_time,
                    expected_start_at=self.simulation_time,
                    expected_finish_at=ambulance_ready_at,
                    status="prepared" if ambulance_id else "unavailable",
                ),
            ]
        )

        preparation = self.preparations.get(incident.incident_id)
        if preparation is not None:
            self._trace(
                event_type="RESPONSE_PREPARATION",
                decision="QUALIFY",
                claim=(
                    f"{preparation.asset_id} should be prepared while the drone "
                    f"verifies {incident.incident_id}."
                ),
                evidence={
                    "probable_mode": preparation.probable_mode,
                    "asset_id": preparation.asset_id,
                    "route_distance_m": round(preparation.route_distance_m, 1),
                    "expected_ready_at": preparation.expected_ready_at,
                    "survey_still_required": True,
                },
                action={
                    "type": "PREPARE_WITHOUT_DISPATCH",
                    "asset_id": preparation.asset_id,
                    "incident_id": incident.incident_id,
                },
            )

        self._trace(
            event_type="PARALLEL_RESPONSE_READINESS",
            decision="QUALIFY",
            claim=(
                f"Reconnaissance, boat readiness, and ambulance readiness "
                f"should proceed in parallel for {incident.incident_id}."
            ),
            evidence=readiness,
            action={
                "type": "PREPARE_PARALLEL_RESPONSE",
                "incident_id": incident.incident_id,
            },
        )

        self._message(
            "PARALLEL_RESPONSE_READY",
            (
                f"Drone {drone_asset_id or 'pending'}, boat "
                f"{boat_id or 'unavailable'}, and ambulance "
                f"{ambulance_id or 'unavailable'} were placed on one temporal plan."
            ),
            incident_id=incident.incident_id,
        )

    def add_incident(self, **kwargs: Any) -> Incident:
        incident = super().add_incident(**kwargs)
        self._prepare_parallel_readiness(incident)
        return incident

    def _free_assets(self, kind: str) -> list[Asset]:
        acceptable_states = {
            "drone": {"standby", "standby_at_dock"},
            "boat": {"standby", "standby_at_dock"},
            "ambulance": {"standby"},
        }

        return [
            asset
            for asset in self.assets.values()
            if asset.kind == kind
            and not asset.grounded
            and asset.current_task_id is None
            and asset.pending_task_id is None
            and asset.state in acceptable_states[kind]
        ]

    def _asset_distance_to_task(self, asset: Asset, task: MissionTask) -> float:
        readiness = self.readiness.get(task.incident_id, {})
        readiness_key = {
            "boat": "boat_asset_id",
            "ambulance": "ambulance_asset_id",
            "drone": "drone_asset_id",
        }[task.required_asset_kind]

        if readiness.get(readiness_key) == asset.asset_id:
            return -1.0

        return super()._asset_distance_to_task(asset, task)

    def _assign_task(
        self,
        task: MissionTask,
        asset: Asset,
        *,
        preemption: bool = False,
    ) -> bool:
        scheduled_at = self.simulation_time
        success = super()._assign_task(task, asset, preemption=preemption)

        if not success:
            return False

        distance = self._route_distance_for_asset(asset)
        expected_arrival = self.simulation_time + self._travel_time_s(
            distance,
            asset,
        )

        timing = TaskTiming(
            task_id=task.task_id,
            incident_id=task.incident_id,
            task_kind=task.task_kind,
            asset_id=asset.asset_id,
            scheduled_at=scheduled_at,
            dispatched_at=self.simulation_time,
            expected_arrival_at=expected_arrival,
        )

        self.task_timings[task.task_id] = timing

        preparation = self.preparations.get(task.incident_id)

        if (
            preparation is not None
            and preparation.asset_id == asset.asset_id
            and task.task_kind == "rescue"
        ):
            preparation.status = "activated"
            preparation.activated_at = self.simulation_time

        self._trace(
            event_type="SCHEDULE_COMMITTED",
            decision="CLEAR",
            claim=(
                f"{asset.asset_id} is scheduled for {task.task_kind} "
                f"task {task.task_id}."
            ),
            evidence={
                "scheduled_at": scheduled_at,
                "dispatched_at": self.simulation_time,
                "expected_arrival_at": expected_arrival,
                "route_distance_m": round(distance, 1),
                "task_kind": task.task_kind,
                "prepared_in_parallel": bool(
                    preparation is not None
                    and preparation.asset_id == asset.asset_id
                ),
            },
            action={
                "type": "COMMIT_TEMPORAL_SLOT",
                "asset_id": asset.asset_id,
                "task_id": task.task_id,
            },
        )

        self.schedule_events.append(
            {
                "event": "dispatch",
                "simulation_time": self.simulation_time,
                "task_id": task.task_id,
                "asset_id": asset.asset_id,
                "expected_arrival_at": expected_arrival,
            }
        )

        if task.task_kind == "hospital_transfer":
            schedule = self.transfer_schedules.get(task.incident_id)

            if schedule is not None:
                schedule.ambulance_id = asset.asset_id
                schedule.ambulance_eta_s = max(
                    0.0,
                    expected_arrival - self.simulation_time,
                )
                schedule.expected_rendezvous_at = max(
                    schedule.selected_at + schedule.boat_eta_s,
                    expected_arrival,
                )
                schedule.expected_hospital_arrival_at = (
                    schedule.expected_rendezvous_at
                    + 5.0
                    + self._road_time_to_hospital(schedule.dock_id, asset)
                )

            self._trace(
                event_type="AMBULANCE_DISPATCHED_EARLY",
                decision="CLEAR",
                claim=(
                    f"{asset.asset_id} should travel to the selected river dock "
                    "while the boat is still carrying patients."
                ),
                evidence={
                    "incident_id": task.incident_id,
                    "patients_at_port_now": self.incidents[
                        task.incident_id
                    ].people_at_transfer,
                    "patients_onboard_boat": self.incidents[
                        task.incident_id
                    ].people_onboard,
                    "expected_arrival_at": expected_arrival,
                },
                action={
                    "type": "DISPATCH_AMBULANCE_TO_RENDEZVOUS",
                    "asset_id": asset.asset_id,
                    "incident_id": task.incident_id,
                },
            )

        return True

    def _complete_survey(self, asset: Asset, task: MissionTask) -> None:
        incident_id = task.incident_id
        super()._complete_survey(asset, task)

        incident = self.incidents[incident_id]
        preparation = self.preparations.get(incident_id)

        if preparation is None:
            return

        verified_kind = (
            "boat"
            if incident.access_mode == "water"
            else "ambulance"
            if incident.access_mode == "land"
            else None
        )

        if verified_kind != preparation.asset_kind:
            preparation.status = "released"
            preparation.released_at = self.simulation_time

            self._trace(
                event_type="PREPARATION_RELEASED",
                decision="REVISE",
                claim=(
                    f"The provisional {preparation.asset_kind} preparation "
                    f"for {incident_id} should be released."
                ),
                evidence={
                    "prepared_asset": preparation.asset_id,
                    "prepared_kind": preparation.asset_kind,
                    "verified_access_mode": incident.access_mode,
                    "released_at": self.simulation_time,
                },
                action={
                    "type": "RELEASE_SOFT_RESERVATION",
                    "asset_id": preparation.asset_id,
                },
            )

    # ------------------------------------------------------------------
    # Dynamic transfer-port selection and concurrent ambulance dispatch
    # ------------------------------------------------------------------

    def _road_time_to_hospital(self, dock_id: str, ambulance: Asset) -> float:
        dock = next(dock for dock in self.transfer_ports if dock.dock_id == dock_id)
        return dock.road_to_hospital_m / max(0.1, ambulance.speed_mps)

    def _select_transfer_schedule(
        self,
        incident: Incident,
        boat: Asset,
    ) -> tuple[TransferSchedule, list[dict[str, Any]]]:
        ambulances = self._free_assets("ambulance")
        fallback_ambulance = next(
            asset
            for asset in self.assets.values()
            if asset.kind == "ambulance"
        )

        scored: list[tuple[float, TransferDock, Asset, float, float, float]] = []

        for dock in self.transfer_ports:
            boat_distance = self._route_distance_from_point(
                self.water_graph,
                boat.point,
                dock.water_node,
            )

            if boat_distance is None:
                continue

            candidate_ambulances = ambulances or [fallback_ambulance]

            for ambulance in candidate_ambulances:
                ambulance_distance = self._route_distance_from_point(
                    self.road_graph,
                    ambulance.point,
                    dock.road_node,
                )

                if ambulance_distance is None:
                    continue

                boat_eta = self._travel_time_s(boat_distance, boat)
                ambulance_eta = self._travel_time_s(
                    ambulance_distance,
                    ambulance,
                )
                hospital_eta = dock.road_to_hospital_m / max(
                    0.1,
                    ambulance.speed_mps,
                )
                total_eta = max(boat_eta, ambulance_eta) + 5.0 + hospital_eta

                scored.append(
                    (
                        total_eta,
                        dock,
                        ambulance,
                        boat_eta,
                        ambulance_eta,
                        hospital_eta,
                    )
                )

        if not scored:
            raise RuntimeError("No connected transfer dock is available.")

        (
            total_eta,
            dock,
            ambulance,
            boat_eta,
            ambulance_eta,
            hospital_eta,
        ) = min(scored, key=lambda item: item[0])

        schedule = TransferSchedule(
            transfer_id=f"transfer-{incident.incident_id}",
            incident_id=incident.incident_id,
            dock_id=dock.dock_id,
            dock_name=dock.name,
            boat_id=boat.asset_id,
            ambulance_id=(
                ambulance.asset_id if ambulances else None
            ),
            selected_at=self.simulation_time,
            boat_eta_s=boat_eta,
            ambulance_eta_s=ambulance_eta,
            expected_rendezvous_at=self.simulation_time
            + max(boat_eta, ambulance_eta),
            expected_hospital_arrival_at=self.simulation_time + total_eta,
        )

        alternatives = [
            {
                "dock_id": candidate_dock.dock_id,
                "dock_name": candidate_dock.name,
                "ambulance_id": candidate_ambulance.asset_id,
                "total_eta_s": round(candidate_total, 1),
                "boat_eta_s": round(candidate_boat_eta, 1),
                "ambulance_eta_s": round(candidate_ambulance_eta, 1),
                "hospital_eta_s": round(candidate_hospital_eta, 1),
            }
            for (
                candidate_total,
                candidate_dock,
                candidate_ambulance,
                candidate_boat_eta,
                candidate_ambulance_eta,
                candidate_hospital_eta,
            ) in sorted(scored, key=lambda item: item[0])[:8]
        ]

        return schedule, alternatives

    def _finish_loading(self, asset: Asset, task: MissionTask) -> None:
        if not (asset.kind == "boat" and task.task_kind == "rescue"):
            super()._finish_loading(asset, task)
            return

        incident = self.incidents[task.incident_id]
        boarded = min(asset.capacity, incident.people_waiting)

        incident.people_waiting -= boarded
        incident.people_onboard += boarded
        incident.status = "onboard"

        asset.cargo_incident_id = incident.incident_id
        asset.cargo_count = boarded

        task.phase = "evacuation"
        task.preemptible = False

        if incident.people_waiting > 0:
            self._queue_task(
                incident,
                task_kind="rescue",
                required_asset_kind="boat",
                destination_node=incident.pickup_node,
            )

        schedule, alternatives = self._select_transfer_schedule(incident, asset)
        self.transfer_schedules[incident.incident_id] = schedule

        dock = next(
            dock
            for dock in self.transfer_ports
            if dock.dock_id == schedule.dock_id
        )

        incident.transfer_port_id = dock.dock_id

        route = self.water_graph.route_points(asset.point, dock.water_node)

        if route is None:
            asset.state = "holding_with_passengers"
            self._trace(
                event_type="TRANSFER_DOCK_SELECTION",
                decision="HOLD",
                claim=f"{asset.asset_id} can reach a supported transfer dock.",
                evidence={"alternatives": alternatives},
                action={"type": "HOLD_AT_SAFE_NODE"},
            )
            return

        asset.route_nodes, asset.route_points = route
        asset.route_index = 1 if len(asset.route_points) > 1 else 0
        asset.state = "evacuating"

        self._trace(
            event_type="TRANSFER_DOCK_SELECTED",
            decision="CLEAR",
            claim=(
                f"{dock.name} should be used for the boat-to-ambulance "
                f"handoff for {incident.incident_id}."
            ),
            evidence={
                "selected_dock": {**asdict(dock), "facility_id": dock.dock_id},
                "selected_at": self.simulation_time,
                "boat_eta_s": schedule.boat_eta_s,
                "ambulance_eta_s": schedule.ambulance_eta_s,
                "expected_rendezvous_at": schedule.expected_rendezvous_at,
                "expected_hospital_arrival_at": (
                    schedule.expected_hospital_arrival_at
                ),
                "alternatives": alternatives,
            },
            action={
                "type": "SCHEDULE_PARALLEL_BOAT_AMBULANCE_RENDEZVOUS",
                "boat_id": asset.asset_id,
                "dock_id": dock.dock_id,
            },
        )

        self._message(
            "PEOPLE_PICKED_UP",
            (
                f"{asset.asset_id} picked up {boarded} people; "
                f"boat and ambulance are now scheduled in parallel for "
                f"{dock.name}."
            ),
            incident_id=incident.incident_id,
            boat_id=asset.asset_id,
            dock_id=dock.dock_id,
        )

        transfer_task = self._queue_task(
            incident,
            task_kind="hospital_transfer",
            required_asset_kind="ambulance",
            destination_node=dock.road_node,
        )

        self.transfer_plans[incident.incident_id] = {
            "transfer_id": schedule.transfer_id,
            "incident_id": incident.incident_id,
            "boat_asset_id": asset.asset_id,
            "ambulance_task_id": (
                transfer_task.task_id if transfer_task is not None else None
            ),
            "port": {
                **asdict(dock),
                "facility_id": dock.dock_id,
            },
            "selected_at": self.simulation_time,
            "expected_rendezvous_at": schedule.expected_rendezvous_at,
            "expected_hospital_arrival_at": schedule.expected_hospital_arrival_at,
        }

        self._trace(
            event_type="TRANSFER_RENDEZVOUS_SCHEDULED",
            decision="CLEAR",
            claim=(
                f"Boat {asset.asset_id} and an ambulance should converge at "
                f"{dock.name} without waiting for the boat to return first."
            ),
            evidence={
                "boat_eta_s": schedule.boat_eta_s,
                "ambulance_eta_s": schedule.ambulance_eta_s,
                "expected_rendezvous_at": schedule.expected_rendezvous_at,
                "expected_hospital_arrival_at": schedule.expected_hospital_arrival_at,
            },
            action={
                "type": "DISPATCH_CONCURRENT_RENDEZVOUS",
                "boat_id": asset.asset_id,
                "ambulance_task_id": (
                    transfer_task.task_id if transfer_task is not None else None
                ),
                "dock_id": dock.dock_id,
            },
        )

        self.schedule()

        if transfer_task is not None and transfer_task.assigned_asset_id:
            schedule.ambulance_id = transfer_task.assigned_asset_id

    def _task_target_point(self, task: MissionTask) -> tuple[float, float]:
        if task.task_kind == "hospital_transfer":
            schedule = self.transfer_schedules.get(task.incident_id)

            if schedule is not None:
                dock = next(
                    dock
                    for dock in self.transfer_ports
                    if dock.dock_id == schedule.dock_id
                )
                return dock.longitude, dock.latitude

        return super()._task_target_point(task)

    def _mark_arrival(self, task: MissionTask, asset: Asset) -> None:
        timing = self.task_timings.get(task.task_id)

        if timing is None or timing.actual_arrival_at is not None:
            return

        timing.actual_arrival_at = self.simulation_time
        timing.status = "arrived"

        self._trace(
            event_type="SCHEDULE_MILESTONE",
            decision="ACCEPT",
            claim=(
                f"{asset.asset_id} reached the destination for "
                f"task {task.task_id}."
            ),
            evidence={
                "expected_arrival_at": timing.expected_arrival_at,
                "actual_arrival_at": timing.actual_arrival_at,
                "arrival_error_s": (
                    timing.actual_arrival_at - timing.expected_arrival_at
                ),
            },
            action={"type": "ADVANCE_TASK_PHASE"},
        )

    def _on_route_complete(self, asset: Asset) -> None:
        if asset.current_task_id is None:
            super()._on_route_complete(asset)
            return

        task = self.tasks[asset.current_task_id]
        self._mark_arrival(task, asset)

        if task.task_kind == "hospital_transfer" and task.phase == "outbound":
            incident = self.incidents[task.incident_id]
            schedule = self.transfer_schedules.get(task.incident_id)

            if schedule is not None:
                schedule.actual_ambulance_arrival_at = self.simulation_time

            if incident.people_at_transfer > 0:
                task.status = "active"
                self._start_loading(asset, task)
            else:
                asset.state = "waiting_at_transfer_port"
                task.status = "waiting_for_patients"

                self._trace(
                    event_type="AMBULANCE_ARRIVED_EARLY",
                    decision="ACCEPT",
                    claim=(
                        f"{asset.asset_id} should wait at the selected dock "
                        "for the arriving boat."
                    ),
                    evidence={
                        "incident_id": incident.incident_id,
                        "patients_at_port": incident.people_at_transfer,
                        "patients_onboard_boat": incident.people_onboard,
                        "arrival_at": self.simulation_time,
                    },
                    action={"type": "WAIT_FOR_RENDEZVOUS"},
                )
            return

        super()._on_route_complete(asset)

    def _activate_waiting_ambulance(self, incident: Incident) -> None:
        for task in self.tasks.values():
            if not (
                task.incident_id == incident.incident_id
                and task.task_kind == "hospital_transfer"
                and task.status == "waiting_for_patients"
                and task.assigned_asset_id
            ):
                continue

            ambulance = self.assets[task.assigned_asset_id]
            task.status = "active"
            self._start_loading(ambulance, task)

            schedule = self.transfer_schedules.get(incident.incident_id)
            if schedule is not None:
                schedule.handoff_started_at = self.simulation_time
                schedule.status = "handoff"

            self._trace(
                event_type="RENDEZVOUS_HANDOFF_STARTED",
                decision="CLEAR",
                claim=(
                    f"Patients at the selected dock should now be loaded into "
                    f"{ambulance.asset_id}."
                ),
                evidence={
                    "incident_id": incident.incident_id,
                    "patients_at_port": incident.people_at_transfer,
                    "handoff_started_at": self.simulation_time,
                },
                action={"type": "START_PORT_TO_AMBULANCE_HANDOFF"},
            )
            return

    def _finish_unloading(self, asset: Asset, task: MissionTask) -> None:
        if asset.kind != "boat":
            super()._finish_unloading(asset, task)

            timing = self.task_timings.get(task.task_id)
            if timing is not None:
                timing.completed_at = self.simulation_time
                timing.status = "completed"

            schedule = self.transfer_schedules.get(task.incident_id)
            if schedule is not None and self.incidents[
                task.incident_id
            ].status == "completed":
                schedule.handoff_completed_at = self.simulation_time
                schedule.status = "completed"
            return

        incident = self.incidents[task.incident_id]
        dock_schedule = self.transfer_schedules[incident.incident_id]
        dock = next(
            dock
            for dock in self.transfer_ports
            if dock.dock_id == dock_schedule.dock_id
        )

        delivered = asset.cargo_count
        incident.people_onboard -= delivered
        incident.people_at_transfer += delivered
        incident.status = "awaiting_hospital_transfer"

        asset.cargo_count = 0
        asset.cargo_incident_id = None
        asset.current_task_id = None
        asset.pending_task_id = None
        asset.route_nodes = []
        asset.route_points = []
        asset.route_index = 0
        asset.state = "standby_at_dock"

        # The selected river dock becomes the boat's new standby location.
        asset.home_node = dock.water_node
        asset.home_longitude = dock.longitude
        asset.home_latitude = dock.latitude
        self.asset_docks[asset.asset_id] = dock.dock_id
        self.asset_current_dock[asset.asset_id] = dock.dock_id

        task.status = "completed"
        task.assigned_asset_id = None
        incident.assigned_asset_id = None

        timing = self.task_timings.get(task.task_id)
        if timing is not None:
            timing.completed_at = self.simulation_time
            timing.status = "completed"

        dock_schedule.actual_boat_arrival_at = self.simulation_time
        dock_schedule.status = "patients_at_port"

        self._trace(
            event_type="PORT_HANDOFF_READY",
            decision="CLEAR",
            claim=(
                f"Patients from {incident.incident_id} are ready for the "
                f"scheduled ambulance at {dock.name}."
            ),
            evidence={
                "dock_id": dock.dock_id,
                "actual_boat_arrival_at": self.simulation_time,
                "ambulance_id": dock_schedule.ambulance_id,
                "people_at_transfer": incident.people_at_transfer,
            },
            action={"type": "BEGIN_OR_WAIT_FOR_HANDOFF"},
        )

        self._trace(
            event_type="PORT_HANDOFF",
            decision="CLEAR",
            claim=(
                f"{delivered} patients from {incident.incident_id} are now "
                f"available for ambulance handoff at {dock.name}."
            ),
            evidence={
                "dock_id": dock.dock_id,
                "dock_name": dock.name,
                "actual_boat_arrival_at": self.simulation_time,
                "expected_boat_arrival_at": (
                    dock_schedule.selected_at + dock_schedule.boat_eta_s
                ),
                "people_at_transfer": incident.people_at_transfer,
                "boat_standby_node": dock.water_node,
            },
            action={
                "type": "RELEASE_BOAT_AT_SELECTED_DOCK",
                "boat_id": asset.asset_id,
            },
        )

        self._message(
            "PEOPLE_AT_TRANSFER_PORT",
            (
                f"{delivered} people reached {dock.name}; "
                f"{asset.asset_id} remains on standby at that dock."
            ),
            incident_id=incident.incident_id,
            dock_id=dock.dock_id,
        )

        hospital_tasks = [
            existing
            for existing in self.tasks.values()
            if (
                existing.incident_id == incident.incident_id
                and existing.task_kind == "hospital_transfer"
                and existing.status
                not in {"completed", "cancelled", "blocked"}
            )
        ]

        if not hospital_tasks:
            self._queue_task(
                incident,
                task_kind="hospital_transfer",
                required_asset_kind="ambulance",
                destination_node=dock.road_node,
            )

        self._activate_waiting_ambulance(incident)
        self.schedule()

    # ------------------------------------------------------------------
    # Schedule re-audit and snapshots
    # ------------------------------------------------------------------

    def _recompute_active_schedule(self, reason: str) -> None:
        revised: list[dict[str, Any]] = []

        for task_id, timing in self.task_timings.items():
            if timing.status not in {"enroute", "arrived"}:
                continue

            asset = self.assets.get(timing.asset_id)

            if asset is None or asset.current_task_id != task_id:
                continue

            previous = timing.expected_arrival_at
            remaining_distance = self._route_distance_for_asset(asset)
            updated = self.simulation_time + self._travel_time_s(
                remaining_distance,
                asset,
            )
            timing.expected_arrival_at = updated

            if abs(updated - previous) >= 3.0:
                revised.append(
                    {
                        "task_id": task_id,
                        "asset_id": asset.asset_id,
                        "previous_expected_arrival_at": previous,
                        "updated_expected_arrival_at": updated,
                    }
                )

        if revised:
            self._trace(
                event_type="SCHEDULE_REVISED",
                decision="REVISE",
                claim=(
                    "Active task timings should be revised after a material "
                    "change in the operating state."
                ),
                evidence={"reason": reason, "revisions": revised},
                action={"type": "UPDATE_EXPECTED_TIMES"},
            )

    def update_config(self, changes: dict[str, Any]) -> None:
        super().update_config(changes)
        self._recompute_active_schedule("parameter_change")

    def inject_shock(
        self,
        shock_type: str,
        target: str | None,
        severity: float,
    ) -> None:
        super().inject_shock(shock_type, target, severity)
        self._recompute_active_schedule(f"shock:{shock_type}")

    def geography_payload(self) -> dict[str, Any]:
        payload = super().geography_payload()
        payload["transfer_ports"] = [
            {**asdict(port), "facility_id": port.dock_id}
            for port in self.transfer_ports
        ]
        return payload

    def snapshot(self) -> dict[str, Any]:
        snapshot = super().snapshot()

        snapshot["version"] = "D0.5"
        snapshot["facilities"]["transfer_ports"] = [
            {**asdict(port), "facility_id": port.dock_id}
            for port in self.transfer_ports
        ]
        snapshot["preparations"] = [
            asdict(item) for item in self.preparations.values()
        ]
        snapshot["readiness"] = list(self.readiness.values())
        snapshot["schedule_entries"] = [
            asdict(item) for item in self.schedule_entries
        ]
        snapshot["transfer_plans"] = list(self.transfer_plans.values())
        snapshot["task_timings"] = [
            asdict(item) for item in self.task_timings.values()
        ]
        snapshot["transfer_schedules"] = [
            asdict(item) for item in self.transfer_schedules.values()
        ]
        snapshot["schedule_events"] = self.schedule_events[-150:]
        snapshot["assets"] = [
            {
                **asset,
                "current_dock_id": self.asset_docks.get(asset["asset_id"]),
                "prepared_for_incident_id": next(
                    (
                        preparation.incident_id
                        for preparation in self.preparations.values()
                        if preparation.asset_id == asset["asset_id"]
                        and preparation.status in {"prepared", "activated"}
                    ),
                    None,
                ),
            }
            for asset in snapshot["assets"]
        ]

        return snapshot


def create_app(
    geography_root: str | Path = (
        "data/geography/antioch_delta_real_v1"
    ),
) -> FastAPI:
    engine = D05Engine(geography_root)
    state_lock = asyncio.Lock()
    websocket_clients: set[WebSocket] = set()

    async def broadcast_snapshot() -> None:
        if not websocket_clients:
            return

        snapshot_text = canonical_json(engine.snapshot())
        disconnected: list[WebSocket] = []

        for websocket in list(websocket_clients):
            try:
                await websocket.send_text(snapshot_text)
            except Exception:  # noqa: BLE001
                disconnected.append(websocket)

        for websocket in disconnected:
            websocket_clients.discard(websocket)

    async def simulation_loop() -> None:
        while True:
            await asyncio.sleep(0.10)

            should_broadcast = False

            async with state_lock:
                if engine.running:
                    engine.tick(0.50 * float(engine.time_scale))
                    should_broadcast = True

            if should_broadcast:
                await broadcast_snapshot()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        task = asyncio.create_task(simulation_loop())

        try:
            yield
        finally:
            task.cancel()

    application = FastAPI(
        title="TRACE-WorldModel D0.5 Concurrent Scheduling Workbench",
        lifespan=lifespan,
    )

    application.state.engine = engine
    application.state.state_lock = state_lock

    application.mount(
        "/d05-static",
        StaticFiles(directory=STATIC_DIR),
        name="d05-static",
    )

    @application.get("/d05")
    async def d05_index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @application.get("/api/d05/geography")
    async def get_geography() -> dict[str, Any]:
        return engine.geography_payload()

    @application.get("/api/d05/state")
    async def get_state() -> dict[str, Any]:
        async with state_lock:
            return engine.snapshot()

    @application.post("/api/d05/incidents")
    async def create_incident(
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        async with state_lock:
            incident = engine.add_incident(
                longitude=float(payload["longitude"]),
                latitude=float(payload["latitude"]),
                people=int(payload.get("people", 4)),
                severity=int(payload.get("severity", 3)),
                deadline_min=int(payload.get("deadline_min", 20)),
                description=str(payload.get("description", "")),
                access_hint=str(payload.get("access_hint", "auto")),
            )
            snapshot = engine.snapshot()

        await broadcast_snapshot()
        return {"incident": asdict(incident), "snapshot": snapshot}

    @application.post("/api/d05/control")
    async def control(
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        action = str(payload.get("action", ""))

        async with state_lock:
            if action == "start":
                engine.running = True
            elif action == "pause":
                engine.running = False
            elif action == "step":
                engine.tick(float(payload.get("seconds", 1.0)))
            elif action == "reset":
                engine.reset()
            elif action == "speed":
                engine.time_scale = max(
                    0.1,
                    min(50.0, float(payload.get("value", 1.0))),
                )

            snapshot = engine.snapshot()

        await broadcast_snapshot()
        return snapshot

    @application.post("/api/d05/config")
    async def update_config(
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        async with state_lock:
            engine.update_config(payload)
            snapshot = engine.snapshot()

        await broadcast_snapshot()
        return snapshot

    @application.post("/api/d05/shock")
    async def inject_shock(
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        async with state_lock:
            engine.inject_shock(
                shock_type=str(payload["shock_type"]),
                target=(str(payload["target"]) if payload.get("target") else None),
                severity=float(payload.get("severity", 1.0)),
            )
            snapshot = engine.snapshot()

        await broadcast_snapshot()
        return snapshot

    @application.post("/api/d05/demo/preemption")
    async def preemption_demo() -> dict[str, Any]:
        async with state_lock:
            engine.run_preemption_demo()
            snapshot = engine.snapshot()

        await broadcast_snapshot()
        return snapshot

    @application.websocket("/ws/d05")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        websocket_clients.add(websocket)

        try:
            await websocket.send_text(canonical_json(engine.snapshot()))

            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            websocket_clients.discard(websocket)

    return application


app: FastAPI | None = None


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run TRACE-WorldModel D0.5 with concurrent scheduling, dynamic docks, "
            "and zoom-aware vehicle rendering."
        )
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8030)
    parser.add_argument(
        "--geography",
        default="data/geography/antioch_delta_real_v1",
    )
    args = parser.parse_args()

    global app
    app = create_app(args.geography)

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
