from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import random
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import uvicorn
from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from trace_jepa.workbench.real_geography import (
    RealGeography,
    haversine_m,
    load_real_geography,
)


Point = tuple[float, float]
AssetKind = Literal["drone", "boat", "ambulance"]
AccessMode = Literal[
    "water",
    "land",
    "unknown",
    "inaccessible",
]
TaskKind = Literal[
    "survey",
    "rescue",
    "hospital_transfer",
]


STATIC_DIR = Path(__file__).with_name("d04_static")
ARTIFACT_ROOT = Path("artifacts") / "d04"


def make_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def interpolate_point(
    start: Point,
    end: Point,
    fraction: float,
) -> Point:
    fraction = max(0.0, min(1.0, fraction))

    return (
        start[0] + (end[0] - start[0]) * fraction,
        start[1] + (end[1] - start[1]) * fraction,
    )


@dataclass
class Incident:
    incident_id: str
    longitude: float
    latitude: float
    people_total: int
    severity: int
    deadline_min: int
    description: str
    reported_access_hint: str
    access_mode: AccessMode = "unknown"
    pickup_node: str | None = None
    pickup_longitude: float | None = None
    pickup_latitude: float | None = None
    status: str = "awaiting_reconnaissance"
    people_waiting: int = 0
    people_onboard: int = 0
    people_at_transfer: int = 0
    people_delivered: int = 0
    assigned_asset_id: str | None = None
    created_at: float = 0.0
    alert_count: int = 1
    hospital_id: str | None = None
    transfer_port_id: str | None = None

    @property
    def point(self) -> Point:
        return self.longitude, self.latitude

    @property
    def pickup_point(self) -> Point | None:
        if (
            self.pickup_longitude is None
            or self.pickup_latitude is None
        ):
            return None

        return (
            self.pickup_longitude,
            self.pickup_latitude,
        )


@dataclass
class MissionTask:
    task_id: str
    incident_id: str
    task_kind: TaskKind
    required_asset_kind: AssetKind
    priority: float
    status: str = "queued"
    phase: str = "outbound"
    assigned_asset_id: str | None = None
    destination_node: str | None = None
    created_at: float = 0.0
    preemptible: bool = True
    suspended_count: int = 0


@dataclass
class Asset:
    asset_id: str
    kind: AssetKind
    longitude: float
    latitude: float
    home_longitude: float
    home_latitude: float
    home_node: str | None
    speed_mps: float
    capacity: int
    color: str
    marker_size: int
    state: str = "standby"
    current_task_id: str | None = None
    pending_task_id: str | None = None
    route_nodes: list[str] = field(default_factory=list)
    route_points: list[Point] = field(default_factory=list)
    route_index: int = 0
    cargo_incident_id: str | None = None
    cargo_count: int = 0
    phase_timer_s: float = 0.0
    grounded: bool = False
    resource_level: float = 1.0

    @property
    def point(self) -> Point:
        return self.longitude, self.latitude

    @point.setter
    def point(self, value: Point) -> None:
        self.longitude, self.latitude = value

    @property
    def home_point(self) -> Point:
        return self.home_longitude, self.home_latitude


class D04Engine:
    def __init__(
        self,
        geography_root: str | Path = (
            "data/geography/"
            "antioch_delta_real_v1"
        ),
    ) -> None:
        self.geography_root = Path(geography_root)
        self.random = random.Random(11)
        self.reset()

    def reset(self) -> None:
        # Reload the cached geography so a reset also clears
        # edge closures, congestion changes, and other shocks.
        self.geography = load_real_geography(
            self.geography_root
        )

        self.water_graph = self.geography.water
        self.road_graph = self.geography.road

        self.hospital = self.geography.scenario[
            "hospital"
        ]

        self.transfer_port = self.geography.scenario[
            "transfer_port"
        ]

        self.random.seed(11)
        self.run_id = make_id("run")
        self.simulation_time = 0.0
        self.running = False
        self.time_scale = 1.0

        self.incidents: dict[str, Incident] = {}
        self.tasks: dict[str, MissionTask] = {}
        self.assets: dict[str, Asset] = {}

        self.trace_entries: list[dict[str, Any]] = []
        self.messages: list[dict[str, Any]] = []
        self.scheduled_alerts: list[dict[str, Any]] = []

        self.config: dict[str, Any] = {
            "sensor_noise": 0.04,
            "river_level": 0.32,
            "river_rate": 0.0,
            "preemption_margin": 15.0,
            "commander_approval": True,
        }

        self._trace_previous_hash = ""
        self._trace_sequence = 0

        self.run_directory = (
            ARTIFACT_ROOT / self.run_id
        )

        self.run_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.trace_path = (
            self.run_directory
            / "operational_trace.jsonl"
        )

        self._create_default_fleet()

        self._message(
            "SYSTEM_READY",
            (
                "Three docked drones, two boats, and "
                "two hospital ambulances are available."
            ),
        )

    def _create_default_fleet(self) -> None:
        drone_colors = [
            "#7c3aed",
            "#0891b2",
            "#db2777",
        ]

        for index, base in enumerate(
            self.geography.scenario["drone_bases"]
        ):
            asset_id = f"survey_drone_{index + 1}"

            self.assets[asset_id] = Asset(
                asset_id=asset_id,
                kind="drone",
                longitude=float(base["longitude"]),
                latitude=float(base["latitude"]),
                home_longitude=float(
                    base["longitude"]
                ),
                home_latitude=float(
                    base["latitude"]
                ),
                home_node=str(base["node_id"]),
                speed_mps=24.0,
                capacity=0,
                color=drone_colors[
                    index % len(drone_colors)
                ],
                marker_size=30,
                state="standby",
            )

        boat_colors = [
            "#0369a1",
            "#0e7490",
        ]

        for index, base in enumerate(
            self.geography.scenario["boat_bases"]
        ):
            asset_id = f"rescue_boat_{index + 1}"

            self.assets[asset_id] = Asset(
                asset_id=asset_id,
                kind="boat",
                longitude=float(base["longitude"]),
                latitude=float(base["latitude"]),
                home_longitude=float(
                    base["longitude"]
                ),
                home_latitude=float(
                    base["latitude"]
                ),
                home_node=str(base["node_id"]),
                speed_mps=11.0,
                capacity=8 if index == 0 else 6,
                color=boat_colors[
                    index % len(boat_colors)
                ],
                marker_size=42 if index == 0 else 37,
                state="standby",
            )

        hospital_node = str(
            self.hospital["road_node"]
        )

        hospital_point = self.road_graph.node_point(
            hospital_node
        )

        ambulance_colors = [
            "#dc2626",
            "#ea580c",
        ]

        ambulance_count = len(
            self.geography.scenario[
                "ambulance_bases"
            ]
        )

        for index in range(ambulance_count):
            asset_id = f"ambulance_{index + 1}"

            self.assets[asset_id] = Asset(
                asset_id=asset_id,
                kind="ambulance",
                longitude=hospital_point[0],
                latitude=hospital_point[1],
                home_longitude=hospital_point[0],
                home_latitude=hospital_point[1],
                home_node=hospital_node,
                speed_mps=15.0,
                capacity=4,
                color=ambulance_colors[
                    index % len(ambulance_colors)
                ],
                marker_size=38 if index == 0 else 34,
                state="standby",
            )

    def _message(
        self,
        event_type: str,
        text: str,
        **details: Any,
    ) -> None:
        entry = {
            "message_id": make_id("message"),
            "simulation_time": round(
                self.simulation_time,
                2,
            ),
            "event_type": event_type,
            "text": text,
            "details": details,
        }

        self.messages.append(entry)
        self.messages = self.messages[-250:]

    def _trace(
        self,
        *,
        event_type: str,
        decision: str,
        claim: str,
        evidence: dict[str, Any],
        action: dict[str, Any],
    ) -> dict[str, Any]:
        self._trace_sequence += 1

        payload = {
            "record_id": (
                f"trace-d04-"
                f"{self._trace_sequence:06d}"
            ),
            "record_version": 1,
            "simulation_time": round(
                self.simulation_time,
                2,
            ),
            "event_type": event_type,
            "decision": decision,
            "claim": claim,
            "evidence": evidence,
            "action": action,
            "policy_version": (
                "reactive-scheduler-v1"
            ),
            "geography_source": (
                self.geography.scenario["source"]
            ),
            "previous_hash": (
                self._trace_previous_hash
            ),
        }

        digest = hashlib.sha256(
            (
                self._trace_previous_hash
                + canonical_json(payload)
            ).encode("utf-8")
        ).hexdigest()

        payload["record_hash"] = digest
        self._trace_previous_hash = digest

        self.trace_entries.append(payload)

        with self.trace_path.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(canonical_json(payload))
            handle.write("\n")

        return payload

    def _incident_priority(
        self,
        incident: Incident,
    ) -> float:
        deadline_pressure = max(
            0.0,
            30.0 - float(incident.deadline_min),
        )

        return (
            20.0 * float(incident.severity)
            + 2.0 * float(incident.people_waiting)
            + 2.0 * float(
                incident.people_at_transfer
            )
            + 1.5 * deadline_pressure
        )

    def add_incident(
        self,
        *,
        longitude: float,
        latitude: float,
        people: int,
        severity: int,
        deadline_min: int,
        description: str,
        access_hint: str = "auto",
    ) -> Incident:
        incident = Incident(
            incident_id=make_id("incident"),
            longitude=float(longitude),
            latitude=float(latitude),
            people_total=max(1, int(people)),
            people_waiting=max(1, int(people)),
            severity=max(
                1,
                min(5, int(severity)),
            ),
            deadline_min=max(
                1,
                int(deadline_min),
            ),
            description=(
                description.strip()
                or "Emergency assistance requested."
            ),
            reported_access_hint=access_hint,
            access_mode="unknown",
            status="awaiting_reconnaissance",
            created_at=self.simulation_time,
            hospital_id=self.hospital[
                "facility_id"
            ],
            transfer_port_id=self.transfer_port[
                "facility_id"
            ],
        )

        self.incidents[incident.incident_id] = (
            incident
        )

        self._message(
            "ALERT_RECEIVED",
            (
                f"{incident.people_waiting} people "
                f"reported at "
                f"{incident.incident_id}."
            ),
            incident_id=incident.incident_id,
            longitude=incident.longitude,
            latitude=incident.latitude,
        )

        self._trace(
            event_type="INCIDENT_GROUNDED",
            decision="ACCEPT",
            claim=(
                f"Emergency incident "
                f"{incident.incident_id} has been "
                "grounded at the clicked geographic "
                "location."
            ),
            evidence={
                "longitude": incident.longitude,
                "latitude": incident.latitude,
                "people": (
                    incident.people_waiting
                ),
                "severity": incident.severity,
                "deadline_min": (
                    incident.deadline_min
                ),
                "reported_access_hint": (
                    incident.reported_access_hint
                ),
            },
            action={
                "type": (
                    "QUEUE_RECONNAISSANCE"
                ),
                "incident_id": (
                    incident.incident_id
                ),
            },
        )

        self._queue_task(
            incident,
            task_kind="survey",
            required_asset_kind="drone",
            destination_node=None,
        )

        self.schedule()

        return incident

    def _add_preverified_water_incident(
        self,
        *,
        node_id: str,
        people: int,
        severity: int,
        deadline_min: int,
        description: str,
    ) -> Incident:
        point = self.water_graph.node_point(
            node_id
        )

        incident = Incident(
            incident_id=make_id("incident"),
            longitude=point[0],
            latitude=point[1],
            people_total=people,
            people_waiting=people,
            severity=severity,
            deadline_min=deadline_min,
            description=description,
            reported_access_hint="water",
            access_mode="water",
            pickup_node=node_id,
            pickup_longitude=point[0],
            pickup_latitude=point[1],
            status="awaiting_assignment",
            created_at=self.simulation_time,
            hospital_id=self.hospital[
                "facility_id"
            ],
            transfer_port_id=self.transfer_port[
                "facility_id"
            ],
        )

        self.incidents[incident.incident_id] = (
            incident
        )

        self._message(
            "PREVERIFIED_ALERT",
            (
                f"Preemption demo created "
                f"{incident.incident_id}."
            ),
            incident_id=incident.incident_id,
        )

        self._queue_task(
            incident,
            task_kind="rescue",
            required_asset_kind="boat",
            destination_node=node_id,
        )

        self.schedule()

        return incident

    def _queue_task(
        self,
        incident: Incident,
        *,
        task_kind: TaskKind,
        required_asset_kind: AssetKind,
        destination_node: str | None,
    ) -> MissionTask | None:
        for task in self.tasks.values():
            if (
                task.incident_id
                == incident.incident_id
                and task.task_kind == task_kind
                and task.status
                not in {
                    "completed",
                    "cancelled",
                    "blocked",
                }
            ):
                return None

        task = MissionTask(
            task_id=make_id("task"),
            incident_id=incident.incident_id,
            task_kind=task_kind,
            required_asset_kind=(
                required_asset_kind
            ),
            priority=self._incident_priority(
                incident
            ),
            destination_node=destination_node,
            created_at=self.simulation_time,
        )

        self.tasks[task.task_id] = task
        return task

    def _classify_access(
        self,
        incident: Incident,
    ) -> tuple[
        AccessMode,
        str | None,
        Point | None,
        float,
    ]:
        point = incident.point

        water_node, water_distance = (
            self.water_graph.nearest_node(point)
        )

        road_node, road_distance = (
            self.road_graph.nearest_node(point)
        )

        maximum_water_distance = float(
            self.geography.scenario[
                "water_maximum_snap_m"
            ]
        )

        maximum_road_distance = float(
            self.geography.scenario[
                "road_maximum_snap_m"
            ]
        )

        water_feasible = (
            water_distance
            <= maximum_water_distance
        )

        road_feasible = (
            road_distance
            <= maximum_road_distance
        )

        hint = incident.reported_access_hint

        if hint == "water" and water_feasible:
            return (
                "water",
                water_node,
                self.water_graph.node_point(
                    water_node
                ),
                water_distance,
            )

        if hint == "land" and road_feasible:
            return (
                "land",
                road_node,
                self.road_graph.node_point(
                    road_node
                ),
                road_distance,
            )

        if water_feasible and road_feasible:
            if water_distance <= road_distance:
                return (
                    "water",
                    water_node,
                    self.water_graph.node_point(
                        water_node
                    ),
                    water_distance,
                )

            return (
                "land",
                road_node,
                self.road_graph.node_point(
                    road_node
                ),
                road_distance,
            )

        if water_feasible:
            return (
                "water",
                water_node,
                self.water_graph.node_point(
                    water_node
                ),
                water_distance,
            )

        if road_feasible:
            return (
                "land",
                road_node,
                self.road_graph.node_point(
                    road_node
                ),
                road_distance,
            )

        return (
            "inaccessible",
            None,
            None,
            min(water_distance, road_distance),
        )

    def _task_target_point(
        self,
        task: MissionTask,
    ) -> Point:
        incident = self.incidents[
            task.incident_id
        ]

        if task.task_kind == "survey":
            return incident.point

        if task.task_kind == "hospital_transfer":
            return (
                float(self.transfer_port["longitude"]),
                float(self.transfer_port["latitude"]),
            )

        if incident.pickup_point is not None:
            return incident.pickup_point

        return incident.point

    def _free_assets(
        self,
        kind: AssetKind,
    ) -> list[Asset]:
        return [
            asset
            for asset in self.assets.values()
            if (
                asset.kind == kind
                and not asset.grounded
                and asset.current_task_id is None
                and asset.pending_task_id is None
                and asset.state == "standby"
            )
        ]

    def _asset_distance_to_task(
        self,
        asset: Asset,
        task: MissionTask,
    ) -> float:
        return haversine_m(
            asset.point,
            self._task_target_point(task),
        )

    def _route_asset_to_task(
        self,
        asset: Asset,
        task: MissionTask,
    ) -> bool:
        incident = self.incidents[
            task.incident_id
        ]

        if asset.kind == "drone":
            asset.route_nodes = []
            asset.route_points = [
                asset.point,
                incident.point,
            ]

        elif asset.kind == "boat":
            if task.destination_node is None:
                return False

            route = self.water_graph.route_points(
                asset.point,
                task.destination_node,
            )

            if route is None:
                return False

            (
                asset.route_nodes,
                asset.route_points,
            ) = route

        elif asset.kind == "ambulance":
            if task.destination_node is None:
                return False

            route = self.road_graph.route_points(
                asset.point,
                task.destination_node,
            )

            if route is None:
                return False

            (
                asset.route_nodes,
                asset.route_points,
            ) = route

        else:
            return False

        asset.route_index = (
            1
            if len(asset.route_points) > 1
            else 0
        )

        return True

    def _assign_task(
        self,
        task: MissionTask,
        asset: Asset,
        *,
        preemption: bool = False,
    ) -> bool:
        incident = self.incidents[
            task.incident_id
        ]

        if not bool(
            self.config["commander_approval"]
        ):
            task.status = "held"

            self._trace(
                event_type="TASK_ASSIGNMENT",
                decision="ESCALATE",
                claim=(
                    f"{asset.asset_id} should be "
                    f"assigned to "
                    f"{incident.incident_id}."
                ),
                evidence={
                    "commander_approval": False,
                    "priority": task.priority,
                },
                action={
                    "type": "HOLD_ASSIGNMENT",
                    "task_id": task.task_id,
                },
            )

            return False

        if not self._route_asset_to_task(
            asset,
            task,
        ):
            task.status = "blocked"

            self._trace(
                event_type="TASK_ASSIGNMENT",
                decision="HOLD",
                claim=(
                    f"{asset.asset_id} can reach "
                    f"{incident.incident_id}."
                ),
                evidence={
                    "access_mode": (
                        incident.access_mode
                    ),
                    "destination_node": (
                        task.destination_node
                    ),
                    "route_available": False,
                },
                action={
                    "type": (
                        "REQUEST_RECONSIDERATION"
                    ),
                    "task_id": task.task_id,
                },
            )

            return False

        task.status = "active"
        task.assigned_asset_id = (
            asset.asset_id
        )

        incident.assigned_asset_id = (
            asset.asset_id
        )

        if task.task_kind == "survey":
            incident.status = (
                "survey_enroute"
            )
            asset.state = "enroute_survey"
        elif task.task_kind == "hospital_transfer":
            incident.status = (
                "ambulance_enroute_to_port"
            )
            asset.state = (
                "enroute_transfer_pickup"
            )
        else:
            incident.status = (
                "responder_enroute"
            )
            asset.state = "enroute_pickup"

        asset.current_task_id = task.task_id
        asset.pending_task_id = None

        self._trace(
            event_type=(
                "PREEMPTION_COMMITTED"
                if preemption
                else "TASK_ASSIGNMENT"
            ),
            decision="CLEAR",
            claim=(
                f"{asset.asset_id} should execute "
                f"{task.task_kind} task "
                f"{task.task_id} for "
                f"{incident.incident_id}."
            ),
            evidence={
                "asset_kind": asset.kind,
                "asset_capacity": asset.capacity,
                "priority": round(
                    task.priority,
                    2,
                ),
                "incident_severity": (
                    incident.severity
                ),
                "people_waiting": (
                    incident.people_waiting
                ),
                "people_at_transfer": (
                    incident.people_at_transfer
                ),
                "route_points": len(
                    asset.route_points
                ),
                "preemption": preemption,
                "commander_approval": True,
            },
            action={
                "type": (
                    "PREEMPT_AND_ASSIGN"
                    if preemption
                    else "ASSIGN"
                ),
                "asset_id": asset.asset_id,
                "task_id": task.task_id,
                "incident_id": (
                    incident.incident_id
                ),
            },
        )

        self._message(
            (
                "PREEMPTION_EXECUTED"
                if preemption
                else "TASK_ASSIGNED"
            ),
            (
                f"{asset.asset_id} assigned to "
                f"{incident.incident_id}."
            ),
            asset_id=asset.asset_id,
            task_id=task.task_id,
            incident_id=incident.incident_id,
        )

        return True

    def _eligible_preemption_assets(
        self,
        task: MissionTask,
    ) -> list[
        tuple[
            float,
            Asset,
            MissionTask,
        ]
    ]:
        candidates: list[
            tuple[
                float,
                Asset,
                MissionTask,
            ]
        ] = []

        for asset in self.assets.values():
            if (
                asset.kind
                != task.required_asset_kind
                or asset.grounded
                or asset.current_task_id is None
                or asset.pending_task_id
                is not None
            ):
                continue

            if asset.cargo_count > 0:
                continue

            if asset.state in {
                "loading",
                "unloading",
                "evacuating",
                "holding_with_passengers",
            }:
                continue

            old_task = self.tasks[
                asset.current_task_id
            ]

            priority_delta = (
                task.priority
                - old_task.priority
            )

            if priority_delta < float(
                self.config[
                    "preemption_margin"
                ]
            ):
                continue

            candidates.append(
                (
                    priority_delta,
                    asset,
                    old_task,
                )
            )

        candidates.sort(
            key=lambda item: (
                -item[0],
                self._asset_distance_to_task(
                    item[1],
                    task,
                ),
            )
        )

        return candidates

    def _request_preemption(
        self,
        task: MissionTask,
    ) -> bool:
        candidates = (
            self._eligible_preemption_assets(
                task
            )
        )

        if not candidates:
            return False

        (
            priority_delta,
            asset,
            old_task,
        ) = candidates[0]

        task.status = "awaiting_preemption"
        asset.pending_task_id = task.task_id

        self._trace(
            event_type="PREEMPTION_PROPOSED",
            decision="CLEAR",
            claim=(
                f"{asset.asset_id} should be "
                f"reassigned from "
                f"{old_task.incident_id} to "
                f"{task.incident_id}."
            ),
            evidence={
                "old_task_id": old_task.task_id,
                "new_task_id": task.task_id,
                "old_priority": round(
                    old_task.priority,
                    2,
                ),
                "new_priority": round(
                    task.priority,
                    2,
                ),
                "priority_delta": round(
                    priority_delta,
                    2,
                ),
                "asset_cargo_count": (
                    asset.cargo_count
                ),
                "safe_node_required": (
                    asset.kind
                    in {"boat", "ambulance"}
                ),
            },
            action={
                "type": (
                    "PREEMPT_AT_NEXT_SAFE_NODE"
                    if asset.kind
                    in {"boat", "ambulance"}
                    else "PREEMPT_NOW"
                ),
                "asset_id": asset.asset_id,
                "old_task_id": (
                    old_task.task_id
                ),
                "new_task_id": task.task_id,
            },
        )

        self._message(
            "PREEMPTION_PENDING",
            (
                f"{asset.asset_id} will switch "
                f"from {old_task.incident_id} "
                f"to {task.incident_id}"
                + (
                    " at the next navigation node."
                    if asset.kind
                    in {"boat", "ambulance"}
                    else " immediately."
                )
            ),
            asset_id=asset.asset_id,
            old_task_id=old_task.task_id,
            new_task_id=task.task_id,
        )

        if asset.kind == "drone":
            self._apply_preemption(asset)

        return True

    def _apply_preemption(
        self,
        asset: Asset,
    ) -> None:
        if asset.pending_task_id is None:
            return

        new_task = self.tasks[
            asset.pending_task_id
        ]

        old_task = (
            self.tasks[
                asset.current_task_id
            ]
            if asset.current_task_id
            else None
        )

        if old_task is not None:
            old_task.status = "suspended"
            old_task.assigned_asset_id = None
            old_task.suspended_count += 1

            old_incident = self.incidents[
                old_task.incident_id
            ]

            old_incident.assigned_asset_id = (
                None
            )

            if old_task.task_kind == "survey":
                old_incident.status = (
                    "awaiting_reconnaissance"
                )
            else:
                old_incident.status = (
                    "suspended"
                )

        asset.current_task_id = None
        asset.pending_task_id = None
        asset.route_nodes = []
        asset.route_points = []
        asset.route_index = 0

        self._assign_task(
            new_task,
            asset,
            preemption=True,
        )

    def schedule(self) -> None:
        pending_tasks = [
            task
            for task in self.tasks.values()
            if task.status
            in {"queued", "suspended"}
        ]

        pending_tasks.sort(
            key=lambda task: (
                -task.priority,
                task.created_at,
            )
        )

        for task in pending_tasks:
            free_assets = self._free_assets(
                task.required_asset_kind
            )

            if free_assets:
                free_assets.sort(
                    key=lambda asset: (
                        self._asset_distance_to_task(
                            asset,
                            task,
                        ),
                        asset.asset_id,
                    )
                )

                self._assign_task(
                    task,
                    free_assets[0],
                )

                continue

            self._request_preemption(task)

    def _complete_survey(
        self,
        asset: Asset,
        task: MissionTask,
    ) -> None:
        incident = self.incidents[
            task.incident_id
        ]

        (
            access_mode,
            pickup_node,
            pickup_point,
            access_distance,
        ) = self._classify_access(incident)

        inconclusive_probability = min(
            0.75,
            max(
                0.0,
                float(
                    self.config[
                        "sensor_noise"
                    ]
                ),
            ),
        )

        if (
            self.random.random()
            < inconclusive_probability
        ):
            access_mode = "unknown"
            pickup_node = None
            pickup_point = None

        task.status = "completed"
        task.assigned_asset_id = None

        asset.current_task_id = None
        asset.pending_task_id = None
        asset.state = "returning_to_base"
        asset.route_nodes = []
        asset.route_points = [
            asset.point,
            asset.home_point,
        ]
        asset.route_index = 1

        incident.assigned_asset_id = None

        if access_mode == "unknown":
            incident.status = (
                "awaiting_reconnaissance"
            )

            self._trace(
                event_type=(
                    "RECONNAISSANCE_RESULT"
                ),
                decision="QUALIFY",
                claim=(
                    f"Reconnaissance of "
                    f"{incident.incident_id} "
                    "is currently inconclusive."
                ),
                evidence={
                    "sensor_noise": (
                        self.config[
                            "sensor_noise"
                        ]
                    ),
                    "access_distance_m": round(
                        access_distance,
                        1,
                    ),
                },
                action={
                    "type": "REQUEUE_SURVEY",
                    "incident_id": (
                        incident.incident_id
                    ),
                },
            )

            self._queue_task(
                incident,
                task_kind="survey",
                required_asset_kind="drone",
                destination_node=None,
            )

            self.schedule()
            return

        incident.access_mode = access_mode
        incident.pickup_node = pickup_node

        if pickup_point is not None:
            (
                incident.pickup_longitude,
                incident.pickup_latitude,
            ) = pickup_point

        if access_mode == "inaccessible":
            incident.status = "escalated"

            self._trace(
                event_type=(
                    "RECONNAISSANCE_RESULT"
                ),
                decision="ESCALATE",
                claim=(
                    f"{incident.incident_id} "
                    "has no supported boat or "
                    "road access."
                ),
                evidence={
                    "nearest_access_distance_m": (
                        round(
                            access_distance,
                            1,
                        )
                    ),
                },
                action={
                    "type": (
                        "REQUEST_EXTERNAL_RESOURCE"
                    ),
                    "incident_id": (
                        incident.incident_id
                    ),
                },
            )

            self._message(
                "ACCESS_ESCALATED",
                (
                    f"{incident.incident_id} "
                    "requires another rescue "
                    "modality."
                ),
                incident_id=(
                    incident.incident_id
                ),
            )

            self.schedule()
            return

        incident.status = "awaiting_assignment"

        required_kind: AssetKind = (
            "boat"
            if access_mode == "water"
            else "ambulance"
        )

        self._trace(
            event_type="RECONNAISSANCE_RESULT",
            decision="ACCEPT",
            claim=(
                f"{incident.incident_id} is "
                f"{access_mode}-accessible."
            ),
            evidence={
                "access_mode": access_mode,
                "pickup_node": pickup_node,
                "access_distance_m": round(
                    access_distance,
                    1,
                ),
                "drone_id": asset.asset_id,
            },
            action={
                "type": "QUEUE_RESCUE",
                "incident_id": (
                    incident.incident_id
                ),
                "required_asset_kind": (
                    required_kind
                ),
            },
        )

        self._message(
            "RECONNAISSANCE_COMPLETE",
            (
                f"{asset.asset_id} classified "
                f"{incident.incident_id} as "
                f"{access_mode}-accessible."
            ),
            incident_id=incident.incident_id,
            asset_id=asset.asset_id,
        )

        self._queue_task(
            incident,
            task_kind="rescue",
            required_asset_kind=required_kind,
            destination_node=pickup_node,
        )

        self.schedule()

    def _start_loading(
        self,
        asset: Asset,
        task: MissionTask,
    ) -> None:
        incident = self.incidents[
            task.incident_id
        ]

        asset.state = "loading"
        asset.phase_timer_s = 5.0
        task.preemptible = False

        if task.task_kind == "hospital_transfer":
            incident.status = (
                "loading_ambulance_at_port"
            )
        else:
            incident.status = "loading"

        self._message(
            "BOARDING_STARTED",
            (
                f"{asset.asset_id} arrived for "
                f"{incident.incident_id}; "
                "boarding started."
            ),
            incident_id=incident.incident_id,
            asset_id=asset.asset_id,
            task_kind=task.task_kind,
        )

    def _queue_remaining_work(
        self,
        incident: Incident,
        task: MissionTask,
    ) -> None:
        if (
            task.task_kind == "rescue"
            and incident.people_waiting > 0
        ):
            required_kind: AssetKind = (
                "boat"
                if incident.access_mode
                == "water"
                else "ambulance"
            )

            self._queue_task(
                incident,
                task_kind="rescue",
                required_asset_kind=(
                    required_kind
                ),
                destination_node=(
                    incident.pickup_node
                ),
            )

        if (
            task.task_kind
            == "hospital_transfer"
            and incident.people_at_transfer > 0
        ):
            self._queue_task(
                incident,
                task_kind=(
                    "hospital_transfer"
                ),
                required_asset_kind=(
                    "ambulance"
                ),
                destination_node=str(
                    self.transfer_port[
                        "road_node"
                    ]
                ),
            )

    def _finish_loading(
        self,
        asset: Asset,
        task: MissionTask,
    ) -> None:
        incident = self.incidents[
            task.incident_id
        ]

        if task.task_kind == "hospital_transfer":
            boarded = min(
                asset.capacity,
                incident.people_at_transfer,
            )
            incident.people_at_transfer -= (
                boarded
            )
        else:
            boarded = min(
                asset.capacity,
                incident.people_waiting,
            )
            incident.people_waiting -= boarded

        incident.people_onboard += boarded
        incident.status = "onboard"

        asset.cargo_incident_id = (
            incident.incident_id
        )
        asset.cargo_count = boarded

        task.phase = "evacuation"
        task.preemptible = False

        if asset.kind == "boat":
            graph = self.water_graph
            destination_node = str(
                self.transfer_port[
                    "water_node"
                ]
            )
            destination_name = (
                self.transfer_port["name"]
            )
        elif asset.kind == "ambulance":
            graph = self.road_graph
            destination_node = str(
                self.hospital["road_node"]
            )
            destination_name = (
                self.hospital["name"]
            )
        else:
            raise RuntimeError(
                "A drone cannot carry evacuees."
            )

        route = graph.route_points(
            asset.point,
            destination_node,
        )

        if route is None:
            asset.state = (
                "holding_with_passengers"
            )

            self._trace(
                event_type="EVACUATION_ROUTE",
                decision="HOLD",
                claim=(
                    f"{asset.asset_id} can "
                    f"evacuate {boarded} people "
                    f"to {destination_name}."
                ),
                evidence={
                    "route_available": False,
                    "cargo_count": boarded,
                },
                action={
                    "type": (
                        "HOLD_AT_SAFE_NODE"
                    ),
                    "asset_id": asset.asset_id,
                },
            )

            return

        (
            asset.route_nodes,
            asset.route_points,
        ) = route

        asset.route_index = (
            1
            if len(asset.route_points) > 1
            else 0
        )

        asset.state = "evacuating"

        self._trace(
            event_type="EVACUATION_ROUTE",
            decision="CLEAR",
            claim=(
                f"{asset.asset_id} should "
                f"evacuate {boarded} people "
                f"to {destination_name}."
            ),
            evidence={
                "cargo_count": boarded,
                "route_points": len(
                    asset.route_points
                ),
                "asset_kind": asset.kind,
                "preemptible": False,
                "destination": (
                    destination_name
                ),
            },
            action={
                "type": "EVACUATE_TO_SAFETY",
                "asset_id": asset.asset_id,
                "incident_id": (
                    incident.incident_id
                ),
                "destination": (
                    destination_name
                ),
            },
        )

        self._message(
            "PEOPLE_PICKED_UP",
            (
                f"{asset.asset_id} picked up "
                f"{boarded} people from "
                f"{incident.incident_id}; "
                f"transport to "
                f"{destination_name} began."
            ),
            incident_id=incident.incident_id,
            asset_id=asset.asset_id,
            people=boarded,
        )

    def _start_unloading(
        self,
        asset: Asset,
    ) -> None:
        asset.state = "unloading"
        asset.phase_timer_s = 5.0

        self._message(
            "UNLOADING_STARTED",
            (
                f"{asset.asset_id} reached "
                "the handoff location."
            ),
            asset_id=asset.asset_id,
            people=asset.cargo_count,
        )

    def _finish_unloading(
        self,
        asset: Asset,
        task: MissionTask,
    ) -> None:
        incident = self.incidents[
            task.incident_id
        ]

        delivered = asset.cargo_count
        incident.people_onboard -= delivered

        asset.cargo_count = 0
        asset.cargo_incident_id = None
        asset.current_task_id = None
        asset.pending_task_id = None
        asset.route_nodes = []
        asset.route_points = []
        asset.route_index = 0
        asset.state = "standby"

        task.status = "completed"
        task.assigned_asset_id = None
        incident.assigned_asset_id = None

        if (
            task.task_kind == "rescue"
            and incident.people_waiting > 0
        ):
            required_kind: AssetKind = (
                "boat"
                if incident.access_mode == "water"
                else "ambulance"
            )

            self._queue_task(
                incident,
                task_kind="rescue",
                required_asset_kind=required_kind,
                destination_node=incident.pickup_node,
            )

        if asset.kind == "boat":
            incident.people_at_transfer += delivered
            incident.status = (
                "awaiting_hospital_transfer"
            )

            self._trace(
                event_type="PORT_HANDOFF",
                decision="CLEAR",
                claim=(
                    f"{delivered} people from "
                    f"{incident.incident_id} "
                    "should be transferred "
                    f"from {self.transfer_port['name']} "
                    f"to {self.hospital['name']}."
                ),
                evidence={
                    "people_at_transfer": (
                        incident.people_at_transfer
                    ),
                    "transfer_port": (
                        self.transfer_port[
                            "name"
                        ]
                    ),
                    "hospital": (
                        self.hospital["name"]
                    ),
                },
                action={
                    "type": (
                        "QUEUE_HOSPITAL_TRANSFER"
                    ),
                    "incident_id": (
                        incident.incident_id
                    ),
                },
            )

            self._message(
                "PEOPLE_AT_TRANSFER_PORT",
                (
                    f"{delivered} people from "
                    f"{incident.incident_id} "
                    f"arrived at "
                    f"{self.transfer_port['name']}; "
                    "ambulance transfer was queued."
                ),
                incident_id=(
                    incident.incident_id
                ),
                people=delivered,
            )

            self._queue_task(
                incident,
                task_kind=(
                    "hospital_transfer"
                ),
                required_asset_kind=(
                    "ambulance"
                ),
                destination_node=str(
                    self.transfer_port[
                        "road_node"
                    ]
                ),
            )

        else:
            incident.people_delivered += (
                delivered
            )

            if incident.people_at_transfer > 0:
                self._queue_task(
                    incident,
                    task_kind="hospital_transfer",
                    required_asset_kind="ambulance",
                    destination_node=str(
                        self.transfer_port["road_node"]
                    ),
                )

            self._message(
                "PEOPLE_DELIVERED",
                (
                    f"{delivered} people from "
                    f"{incident.incident_id} "
                    f"were delivered to "
                    f"{self.hospital['name']}."
                ),
                incident_id=(
                    incident.incident_id
                ),
                asset_id=asset.asset_id,
                people=delivered,
            )

        if (
            incident.people_waiting == 0
            and incident.people_onboard == 0
            and incident.people_at_transfer
            == 0
        ):
            incident.status = "completed"

            self._trace(
                event_type="RESCUE_COMPLETED",
                decision="ACCEPT",
                claim=(
                    f"Incident "
                    f"{incident.incident_id} "
                    "has been completed."
                ),
                evidence={
                    "people_total": (
                        incident.people_total
                    ),
                    "people_delivered": (
                        incident.people_delivered
                    ),
                    "hospital": (
                        self.hospital["name"]
                    ),
                },
                action={
                    "type": "CLOSE_INCIDENT",
                    "incident_id": (
                        incident.incident_id
                    ),
                },
            )

            self._message(
                "RESCUE_COMPLETED",
                (
                    f"{incident.incident_id} "
                    "completed; "
                    f"{incident.people_delivered} "
                    "people reached the hospital."
                ),
                incident_id=(
                    incident.incident_id
                ),
            )
        elif incident.people_waiting > 0:
            incident.status = (
                "awaiting_assignment"
            )
        elif incident.people_at_transfer > 0:
            incident.status = (
                "awaiting_hospital_transfer"
            )

        self.schedule()

    def _on_route_complete(
        self,
        asset: Asset,
    ) -> None:
        if asset.current_task_id is None:
            if asset.state == "returning_to_base":
                asset.state = "standby"
                asset.route_nodes = []
                asset.route_points = []
                asset.route_index = 0

                self._message(
                    "DRONE_DOCKED",
                    (
                        f"{asset.asset_id} "
                        "returned to its "
                        "riverside base."
                    ),
                    asset_id=asset.asset_id,
                )

            return

        task = self.tasks[
            asset.current_task_id
        ]

        if task.task_kind == "survey":
            self._complete_survey(
                asset,
                task,
            )
            return

        if task.phase == "outbound":
            self._start_loading(
                asset,
                task,
            )
            return

        if task.phase == "evacuation":
            self._start_unloading(asset)

    def _movement_speed(
        self,
        asset: Asset,
    ) -> float:
        if asset.kind == "boat":
            river_level = float(
                self.config["river_level"]
            )

            return asset.speed_mps * max(
                0.45,
                1.0
                - 0.35 * river_level,
            )

        return asset.speed_mps

    def _move_asset(
        self,
        asset: Asset,
        delta_s: float,
    ) -> None:
        if asset.grounded:
            return

        if asset.state in {
            "loading",
            "unloading",
        }:
            asset.phase_timer_s -= delta_s

            if asset.phase_timer_s > 0:
                return

            task = (
                self.tasks[
                    asset.current_task_id
                ]
                if asset.current_task_id
                else None
            )

            if task is None:
                asset.state = "standby"
                return

            if asset.state == "loading":
                self._finish_loading(
                    asset,
                    task,
                )
            else:
                self._finish_unloading(
                    asset,
                    task,
                )

            return

        if (
            asset.route_index
            >= len(asset.route_points)
        ):
            return

        target = asset.route_points[
            asset.route_index
        ]

        remaining = haversine_m(
            asset.point,
            target,
        )

        step = (
            self._movement_speed(asset)
            * delta_s
        )

        if remaining <= max(0.1, step):
            asset.point = target
            asset.route_index += 1

            if (
                asset.pending_task_id
                is not None
            ):
                self._apply_preemption(
                    asset
                )
                return

            if (
                asset.route_index
                >= len(
                    asset.route_points
                )
            ):
                self._on_route_complete(
                    asset
                )

            return

        asset.point = interpolate_point(
            asset.point,
            target,
            step / remaining,
        )

    def tick(
        self,
        delta_s: float,
    ) -> None:
        delta_s = max(
            0.0,
            float(delta_s),
        )

        self.simulation_time += delta_s

        due = [
            item
            for item in self.scheduled_alerts
            if item["due_at"]
            <= self.simulation_time
        ]

        self.scheduled_alerts = [
            item
            for item in self.scheduled_alerts
            if item["due_at"]
            > self.simulation_time
        ]

        for item in due:
            self._add_preverified_water_incident(
                **item["incident"]
            )

        river_rate = float(
            self.config["river_rate"]
        )

        if river_rate != 0.0:
            self.config["river_level"] = max(
                0.0,
                min(
                    1.5,
                    float(
                        self.config[
                            "river_level"
                        ]
                    )
                    + river_rate
                    * delta_s
                    / 60.0,
                ),
            )

        for asset in self.assets.values():
            self._move_asset(
                asset,
                delta_s,
            )

        self.schedule()

    def update_config(
        self,
        changes: dict[str, Any],
    ) -> None:
        allowed = {
            "sensor_noise",
            "river_level",
            "river_rate",
            "preemption_margin",
            "commander_approval",
        }

        applied: dict[str, Any] = {}

        for key, value in changes.items():
            if key not in allowed:
                continue

            if key == "commander_approval":
                applied[key] = bool(value)
            else:
                applied[key] = float(value)

            self.config[key] = applied[key]

        self._trace(
            event_type=(
                "EXPERIMENT_PARAMETER_CHANGED"
            ),
            decision="REVISE",
            claim=(
                "The Mission Controller should "
                "re-audit active plans after "
                "an S1-S5 parameter change."
            ),
            evidence={
                "changes": applied,
                "active_tasks": [
                    task.task_id
                    for task
                    in self.tasks.values()
                    if task.status
                    == "active"
                ],
            },
            action={
                "type": (
                    "REAUDIT_AND_RESCHEDULE"
                ),
            },
        )

        self._message(
            "PARAMETERS_UPDATED",
            (
                "S1-S5 parameters changed; "
                "active assignments were "
                "re-audited."
            ),
            changes=applied,
        )

        self.schedule()

    def inject_shock(
        self,
        shock_type: str,
        target: str | None,
        severity: float,
    ) -> None:
        if (
            shock_type == "ground_asset"
            and target
        ):
            asset = self.assets.get(target)

            if asset:
                asset.grounded = True
                self._message(
                    "ASSET_GROUNDED",
                    (
                        f"{asset.asset_id} "
                        "was grounded."
                    ),
                    asset_id=asset.asset_id,
                )

        elif (
            shock_type == "restore_asset"
            and target
        ):
            asset = self.assets.get(target)

            if asset:
                asset.grounded = False

        elif (
            shock_type
            == "close_water_edge"
            and target
        ):
            self.water_graph.close_edge(
                target,
                "operator shock",
            )

        elif (
            shock_type
            == "open_water_edge"
            and target
        ):
            self.water_graph.open_edge(target)

        self._trace(
            event_type="SHOCK_INJECTED",
            decision="REVISE",
            claim=(
                "The active schedule should be "
                "re-evaluated after the injected "
                "disruption."
            ),
            evidence={
                "shock_type": shock_type,
                "target": target,
                "severity": severity,
            },
            action={
                "type": (
                    "REACTIVE_RESCHEDULE"
                ),
            },
        )

        self.schedule()

    def run_preemption_demo(self) -> None:
        self.reset()

        self.assets[
            "rescue_boat_2"
        ].grounded = True

        demo_nodes = [
            str(node_id)
            for node_id in self.geography.scenario[
                "demo_water_nodes"
            ]
        ]

        self._add_preverified_water_incident(
            node_id=demo_nodes[0],
            people=3,
            severity=2,
            deadline_min=35,
            description=(
                "Moderate-priority "
                "water incident A."
            ),
        )

        self.scheduled_alerts.append(
            {
                "due_at": (
                    self.simulation_time
                    + 12.0
                ),
                "incident": {
                    "node_id": (
                        demo_nodes[1]
                    ),
                    "people": 8,
                    "severity": 5,
                    "deadline_min": 5,
                    "description": (
                        "Critical incident B "
                        "requiring reactive "
                        "preemption."
                    ),
                },
            }
        )

        self.running = True

        self._message(
            "PREEMPTION_DEMO_STARTED",
            (
                "Boat 1 is serving incident A; "
                "critical incident B will "
                "appear at t+12 s."
            ),
        )

    def geography_payload(
        self,
    ) -> dict[str, Any]:
        return {
            "scenario": self.geography.scenario,
            "waterways": (
                self.geography.waterways_geojson
            ),
            "facilities": (
                self.geography.facilities_geojson
            ),
        }

    def snapshot(self) -> dict[str, Any]:
        waiting = sum(
            incident.people_waiting
            for incident
            in self.incidents.values()
            if incident.status
            != "completed"
        )

        onboard = sum(
            incident.people_onboard
            for incident
            in self.incidents.values()
        )

        at_transfer = sum(
            incident.people_at_transfer
            for incident
            in self.incidents.values()
        )

        delivered = sum(
            incident.people_delivered
            for incident
            in self.incidents.values()
        )

        return {
            "run_id": self.run_id,
            "simulation_time": round(
                self.simulation_time,
                2,
            ),
            "running": self.running,
            "time_scale": self.time_scale,
            "map": {
                **self.geography.scenario[
                    "camera"
                ],
                "bbox": (
                    self.geography.scenario[
                        "bbox"
                    ]
                ),
                "synthetic_geometry": False,
                "source": (
                    self.geography.scenario[
                        "source"
                    ]
                ),
            },
            "config": self.config,
            "facilities": {
                "hospital": self.hospital,
                "transfer_port": (
                    self.transfer_port
                ),
                "boat_bases": (
                    self.geography.scenario[
                        "boat_bases"
                    ]
                ),
                "drone_bases": (
                    self.geography.scenario[
                        "drone_bases"
                    ]
                ),
            },
            "assets": [
                {
                    **asdict(asset),
                    "remaining_route": [
                        list(asset.point),
                        *[
                            list(point)
                            for point
                            in asset.route_points[
                                asset.route_index:
                            ]
                        ],
                    ],
                }
                for asset in self.assets.values()
            ],
            "incidents": [
                asdict(incident)
                for incident
                in self.incidents.values()
            ],
            "tasks": [
                asdict(task)
                for task
                in self.tasks.values()
            ],
            "closed_water_edges": [
                status
                for status
                in self.water_graph.edge_statuses()
                if not status["open"]
            ],
            "trace_entries": (
                self.trace_entries[-100:]
            ),
            "messages": self.messages[-120:],
            "metrics": {
                "people_waiting": waiting,
                "people_onboard": onboard,
                "people_at_transfer": (
                    at_transfer
                ),
                "people_delivered": delivered,
                "active_tasks": sum(
                    task.status == "active"
                    for task
                    in self.tasks.values()
                ),
                "suspended_tasks": sum(
                    task.status
                    == "suspended"
                    for task
                    in self.tasks.values()
                ),
                "pending_preemptions": sum(
                    asset.pending_task_id
                    is not None
                    for asset
                    in self.assets.values()
                ),
                "trace_records": len(
                    self.trace_entries
                ),
            },
        }


def create_app(
    geography_root: str | Path = (
        "data/geography/"
        "antioch_delta_real_v1"
    ),
) -> FastAPI:
    engine = D04Engine(geography_root)
    state_lock = asyncio.Lock()
    websocket_clients: set[WebSocket] = set()

    async def broadcast_snapshot() -> None:
        if not websocket_clients:
            return

        snapshot_text = canonical_json(
            engine.snapshot()
        )

        disconnected: list[WebSocket] = []

        for websocket in list(
            websocket_clients
        ):
            try:
                await websocket.send_text(
                    snapshot_text
                )
            except Exception:  # noqa: BLE001
                disconnected.append(
                    websocket
                )

        for websocket in disconnected:
            websocket_clients.discard(
                websocket
            )

    async def simulation_loop() -> None:
        while True:
            await asyncio.sleep(0.10)

            should_broadcast = False

            async with state_lock:
                if engine.running:
                    engine.tick(
                        0.50
                        * float(
                            engine.time_scale
                        )
                    )
                    should_broadcast = True

            if should_broadcast:
                await broadcast_snapshot()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        task = asyncio.create_task(
            simulation_loop()
        )

        try:
            yield
        finally:
            task.cancel()

    application = FastAPI(
        title=(
            "TRACE-WorldModel D0.4 "
            "Real Geography Workbench"
        ),
        lifespan=lifespan,
    )

    application.state.engine = engine
    application.state.state_lock = (
        state_lock
    )

    application.mount(
        "/d04-static",
        StaticFiles(directory=STATIC_DIR),
        name="d04-static",
    )

    @application.get("/d04")
    async def d04_index() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "index.html"
        )

    @application.get(
        "/api/d04/geography"
    )
    async def get_geography() -> dict[str, Any]:
        return engine.geography_payload()

    @application.get("/api/d04/state")
    async def get_state() -> dict[str, Any]:
        async with state_lock:
            return engine.snapshot()

    @application.post(
        "/api/d04/incidents"
    )
    async def create_incident(
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        async with state_lock:
            incident = engine.add_incident(
                longitude=float(
                    payload["longitude"]
                ),
                latitude=float(
                    payload["latitude"]
                ),
                people=int(
                    payload.get("people", 4)
                ),
                severity=int(
                    payload.get("severity", 3)
                ),
                deadline_min=int(
                    payload.get(
                        "deadline_min",
                        20,
                    )
                ),
                description=str(
                    payload.get(
                        "description",
                        "",
                    )
                ),
                access_hint=str(
                    payload.get(
                        "access_hint",
                        "auto",
                    )
                ),
            )

            snapshot = engine.snapshot()

        await broadcast_snapshot()

        return {
            "incident": asdict(incident),
            "snapshot": snapshot,
        }

    @application.post("/api/d04/control")
    async def control(
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        action = str(
            payload.get("action", "")
        )

        async with state_lock:
            if action == "start":
                engine.running = True
            elif action == "pause":
                engine.running = False
            elif action == "step":
                engine.tick(
                    float(
                        payload.get(
                            "seconds",
                            1.0,
                        )
                    )
                )
            elif action == "reset":
                engine.reset()
            elif action == "speed":
                engine.time_scale = max(
                    0.1,
                    min(
                        20.0,
                        float(
                            payload.get(
                                "value",
                                1.0,
                            )
                        ),
                    ),
                )

            snapshot = engine.snapshot()

        await broadcast_snapshot()
        return snapshot

    @application.post("/api/d04/config")
    async def update_config(
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        async with state_lock:
            engine.update_config(payload)
            snapshot = engine.snapshot()

        await broadcast_snapshot()
        return snapshot

    @application.post("/api/d04/shock")
    async def inject_shock(
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        async with state_lock:
            engine.inject_shock(
                shock_type=str(
                    payload["shock_type"]
                ),
                target=(
                    str(payload["target"])
                    if payload.get("target")
                    else None
                ),
                severity=float(
                    payload.get(
                        "severity",
                        1.0,
                    )
                ),
            )

            snapshot = engine.snapshot()

        await broadcast_snapshot()
        return snapshot

    @application.post(
        "/api/d04/demo/preemption"
    )
    async def preemption_demo() -> dict[str, Any]:
        async with state_lock:
            engine.run_preemption_demo()
            snapshot = engine.snapshot()

        await broadcast_snapshot()
        return snapshot

    @application.websocket("/ws/d04")
    async def websocket_endpoint(
        websocket: WebSocket,
    ) -> None:
        await websocket.accept()
        websocket_clients.add(websocket)

        try:
            await websocket.send_text(
                canonical_json(
                    engine.snapshot()
                )
            )

            while True:
                await websocket.receive_text()

        except WebSocketDisconnect:
            pass

        finally:
            websocket_clients.discard(
                websocket
            )

    return application


app: FastAPI | None = None


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the TRACE-WorldModel D0.4 real-geography "
            "multi-asset workbench."
        )
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8020,
    )

    parser.add_argument(
        "--geography",
        default=(
            "data/geography/"
            "antioch_delta_real_v1"
        ),
    )

    args = parser.parse_args()

    global app
    app = create_app(args.geography)

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
