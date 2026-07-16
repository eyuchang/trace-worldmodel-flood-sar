from __future__ import annotations

import asyncio
import math
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from trace_jepa.util import new_id
from trace_jepa.workbench.engine import DynamicRun, SimulationLoop
from trace_jepa.workbench.models import EventType, EventVisibility, ScenarioLevel


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StepRequest(RequestModel):
    dt: float = Field(default=1.0, gt=0.0, le=600.0)


class SpeedRequest(RequestModel):
    speed: float = Field(ge=0.1, le=50.0)


class EventRequest(RequestModel):
    event_type: EventType
    scenario_level: ScenarioLevel
    visibility: EventVisibility = EventVisibility.BOTH
    payload: dict[str, Any] = Field(default_factory=dict)


class EmergencyCallRequest(RequestModel):
    location_label: str = "Riverside Apartments"
    x: float = 88.0
    y: float = 66.0
    people: int = Field(default=4, ge=1, le=500)
    count_semantics: Literal["current_waiting", "additional_people"] = (
        "current_waiting"
    )
    severity: float = Field(default=0.55, ge=0.0, le=1.0)
    deadline_s: float = Field(default=1200.0, ge=30.0)


def create_app(
    *,
    scenario_path: str | Path | None = None,
    artifact_root: str | Path | None = None,
) -> FastAPI:
    repo_root = Path(__file__).resolve().parents[3]
    scenario = Path(
        scenario_path
        or repo_root / "configs" / "scenarios" / "riverside_flood_dynamic_v2.yaml"
    )
    artifacts = Path(artifact_root or repo_root / "artifacts" / "dynamic")
    run = DynamicRun(scenario_path=scenario, artifact_root=artifacts)
    loop = SimulationLoop(run)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await loop.start()
        try:
            yield
        finally:
            await loop.stop()
            run.export_manifest()

    app = FastAPI(
        title="TRACE-JEPA Dynamic Flood-SAR Workbench",
        version="0.2.2",
        description="Event-sourced S1-S5 research simulator and TRACE control console.",
        lifespan=lifespan,
    )
    app.state.run = run
    app.state.loop = loop

    static_root = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=static_root), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(static_root / "index.html")

    @app.get("/api/state")
    async def state() -> dict[str, Any]:
        return run.snapshot().model_dump(mode="json")

    @app.get("/api/events")
    async def events() -> list[dict[str, Any]]:
        return [event.model_dump(mode="json") for event in run.event_store.all()]

    @app.get("/api/records")
    async def records() -> list[dict[str, Any]]:
        return [record.model_dump(mode="json") for record in run.runtime.repository.all()]

    @app.post("/api/control/start")
    async def start() -> dict[str, Any]:
        await run.start()
        return {"ok": True, "running": True}

    @app.post("/api/control/pause")
    async def pause() -> dict[str, Any]:
        await run.pause()
        return {"ok": True, "running": False}

    @app.post("/api/control/step")
    async def step(request: StepRequest) -> dict[str, Any]:
        await run.step(request.dt)
        return {"ok": True, "simulation_time": run.state.truth.simulation_time}

    @app.post("/api/control/reset")
    async def reset() -> dict[str, Any]:
        await run.reset()
        return {"ok": True, "run_id": run.run_id}

    @app.post("/api/control/speed")
    async def speed(request: SpeedRequest) -> dict[str, Any]:
        await run.set_speed(request.speed)
        return {"ok": True, "speed": run.state.config.simulation_speed}

    @app.post("/api/emergency-call")
    async def emergency_call(request: EmergencyCallRequest) -> dict[str, Any]:
        """Create or update one active incident at the reported location.

        Repeated calls within the configured merge radius update the same
        active incident instead of stacking another marker with a stale
        count. The caller must say whether the number is the current total
        still waiting or additional people at the incident.
        """

        match = None
        for group in run.state.controller.known_groups.values():
            if group.rescued or group.cancelled:
                continue
            if group.rescue_phase not in {"waiting", "assigned"}:
                continue
            distance = math.hypot(
                group.position.x - request.x,
                group.position.y - request.y,
            )
            if distance <= run.state.config.rescue.merge_alert_radius:
                match = group
                break

        call_id = new_id("call")
        group_id = match.group_id if match is not None else new_id("group")
        previous_waiting = int(match.people_waiting or 0) if match is not None else 0
        if match is not None and request.count_semantics == "additional_people":
            resolved_people = previous_waiting + request.people
            resolution = "merged"
        elif match is not None:
            resolved_people = request.people
            resolution = "updated"
        else:
            resolved_people = request.people
            resolution = "created"
        payload = {
            "call_id": call_id,
            "group_id": group_id,
            "location_label": request.location_label,
            "position": {"x": request.x, "y": request.y},
            "people": resolved_people,
            "reported_people": request.people,
            "count_semantics": request.count_semantics,
            "severity": request.severity,
            "deadline_s": request.deadline_s,
            "safe_location_id": run.state.config.rescue.safe_location_id,
            "merged": match is not None,
            "previous_people_waiting": previous_waiting if match is not None else None,
        }

        if match is not None and request.count_semantics == "additional_people":
            event = await run.inject_event(
                event_type=EventType.INCIDENT_MERGED,
                scenario_level=ScenarioLevel.CORE,
                visibility=EventVisibility.BOTH,
                payload={
                    **payload,
                    "people_added": request.people,
                },
            )
            resolution = "merged"
        else:
            # `current_waiting` is an exact operational update, not an
            # addition. This prevents repeated calls from silently doubling
            # the incident count while still allowing an operator to report a
            # larger or smaller current total.
            event = await run.inject_event(
                event_type=EventType.EMERGENCY_CALL,
                scenario_level=ScenarioLevel.CORE,
                visibility=EventVisibility.BOTH,
                payload=payload,
            )
            resolution = "updated" if match is not None else "created"
        group = run.state.truth.groups[group_id]
        return {
            "event": event.model_dump(mode="json"),
            "resolution": resolution,
            "group_id": group_id,
            "people_total": group.people,
            "people_waiting": int(group.people_waiting or 0),
            "people_onboard": group.people_onboard,
            "people_delivered": group.people_delivered,
            "alert_count": group.alert_count,
        }

    @app.post("/api/events")
    async def inject(request: EventRequest) -> dict[str, Any]:
        try:
            event = await run.inject_event(
                event_type=request.event_type,
                scenario_level=request.scenario_level,
                visibility=request.visibility,
                payload=request.payload,
            )
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return event.model_dump(mode="json")

    @app.post("/api/plan")
    async def plan_now() -> dict[str, Any]:
        await run.plan_now()
        return {"ok": True}

    @app.post("/api/export")
    async def export() -> dict[str, Any]:
        path = run.export_manifest()
        return {"ok": True, "path": str(path)}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=8)

        async def subscriber(snapshot: Any) -> None:
            payload = snapshot.model_dump(mode="json")
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            await queue.put(payload)

        run.subscribe(subscriber)
        try:
            await websocket.send_json(run.snapshot().model_dump(mode="json"))
            while True:
                payload = await queue.get()
                await websocket.send_json(payload)
        except WebSocketDisconnect:
            pass
        finally:
            run.unsubscribe(subscriber)

    return app


app = create_app()
