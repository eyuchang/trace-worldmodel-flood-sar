from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from trace_jepa.workbench.api import create_app
from trace_jepa.workbench.engine import DynamicRun
from trace_jepa.workbench.models import EventType, EventVisibility, ScenarioLevel


SCENARIO = Path(__file__).parents[1] / "configs" / "scenarios" / "riverside_flood_v1.yaml"


def make_run(tmp_path: Path) -> DynamicRun:
    return DynamicRun(scenario_path=SCENARIO, artifact_root=tmp_path / "runs")


def test_truth_is_not_initial_controller_knowledge(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    assert run.state.truth.routes["north_channel"].open is False
    assert run.state.controller.route_beliefs["north_channel"].status == "unknown"


def test_s1_event_changes_parameters_and_is_logged(tmp_path: Path) -> None:
    run = make_run(tmp_path)

    async def exercise() -> None:
        await run.inject_event(
            event_type=EventType.SET_S1_PARAMETERS,
            scenario_level=ScenarioLevel.S1,
            payload={"sensor_noise": 0.44, "seed": 99},
        )

    asyncio.run(exercise())
    assert run.state.config.s1.sensor_noise == 0.44
    assert run.state.config.s1.seed == 99
    event_types = [event.event_type for event in run.event_store.all()]
    assert EventType.SET_S1_PARAMETERS in event_types
    assert event_types[-1] == EventType.REASONING_COMPLETED
    assert run.state.controller.latest_reasoning is not None
    assert run.state.controller.latest_reasoning.scenario_level == ScenarioLevel.S1
    assert run.event_store.verify_chain()


def test_s2_water_can_close_previously_open_route(tmp_path: Path) -> None:
    run = make_run(tmp_path)

    async def exercise() -> None:
        await run.inject_event(
            event_type=EventType.SET_S2_PARAMETERS,
            scenario_level=ScenarioLevel.S2,
            payload={
                "rain_intensity": 1.0,
                "upstream_inflow": 1.0,
                "water_rise_rate": 0.1,
                "route_closure_depth": 0.30,
            },
        )
        await run.step(1.0)

    asyncio.run(exercise())
    assert run.state.truth.routes["south_detour"].open is False
    assert any(event.event_type == EventType.ROUTE_STATUS_CHANGED for event in run.event_store.all())


def test_s3_planner_does_not_double_assign_group(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    run.emit(
        EventType.EMERGENCY_CALL,
        source="test",
        payload={
            "group_id": "group_riverside",
            "location_label": "Riverside Apartments",
            "position": {"x": 88.0, "y": 66.0},
            "people": 4,
            "severity": 0.55,
            "deadline_s": 1200.0,
        },
    )

    async def exercise() -> None:
        await run.inject_event(
            event_type=EventType.ADD_ASSET,
            scenario_level=ScenarioLevel.S3,
            payload={
                "asset_id": "helicopter_1",
                "asset_type": "helicopter",
                "position": {"x": 8.0, "y": 7.0},
                "capacity": 8,
                "speed": 12.0,
                "resource": 1.0,
                "operating_cost": 18.0,
                "weather_tolerance": 0.9,
            },
        )
        await run.plan_now()
        await run.plan_now()

    asyncio.run(exercise())
    assigned = [
        asset.asset_id for asset in run.state.truth.assets.values() if asset.assigned_group_id
    ]
    assert len(assigned) <= 1
    assert run.state.metrics.double_commitment_violations == 0


def test_s4_shock_is_event_sourced(tmp_path: Path) -> None:
    run = make_run(tmp_path)

    async def exercise() -> None:
        await run.inject_event(
            event_type=EventType.INJECT_SHOCK,
            scenario_level=ScenarioLevel.S4,
            visibility=EventVisibility.TRUTH,
            payload={"shock_type": "communication_loss", "severity": 1.0},
        )

    asyncio.run(exercise())
    assert run.state.truth.communications_available is False
    assert run.state.truth.last_shock == "communication_loss"


def test_s5_operator_can_request_reconnaissance(tmp_path: Path) -> None:
    run = make_run(tmp_path)

    async def exercise() -> None:
        await run.inject_event(
            event_type=EventType.REQUEST_SURVEY,
            scenario_level=ScenarioLevel.S5,
            payload={"route_id": "south_detour", "requested_by": "test"},
        )
        await run.plan_now()

    asyncio.run(exercise())
    assert any(
        event.event_type == EventType.ACTION_STARTED
        and event.payload.get("action_type") == "verify_route"
        and event.payload.get("route_id") == "south_detour"
        for event in run.event_store.all()
    )


def test_replay_reconstructs_state(tmp_path: Path) -> None:
    run = make_run(tmp_path)

    async def exercise() -> None:
        await run.inject_event(
            event_type=EventType.SET_S1_PARAMETERS,
            scenario_level=ScenarioLevel.S1,
            payload={"sensor_noise": 0.22},
        )
        await run.step(2.0)
        await run.inject_event(
            event_type=EventType.INJECT_SHOCK,
            scenario_level=ScenarioLevel.S4,
            visibility=EventVisibility.TRUTH,
            payload={"shock_type": "wind_shift", "severity": 0.4},
        )

    asyncio.run(exercise())
    replay = run.replay_state()
    assert replay.model_dump(mode="json") == run.state.model_dump(mode="json")


def test_fastapi_state_and_s1_event(tmp_path: Path) -> None:
    app = create_app(scenario_path=SCENARIO, artifact_root=tmp_path / "api-runs")
    with TestClient(app) as client:
        response = client.get("/api/state")
        assert response.status_code == 200
        assert response.json()["controller"]["route_beliefs"]["north_channel"]["status"] == "unknown"
        response = client.post(
            "/api/events",
            json={
                "event_type": "SET_S1_PARAMETERS",
                "scenario_level": "S1",
                "visibility": "both",
                "payload": {"ood_severity": 0.77},
            },
        )
        assert response.status_code == 200
        assert client.get("/api/state").json()["config"]["s1"]["ood_severity"] == 0.77


def test_websocket_streams_initial_snapshot(tmp_path: Path) -> None:
    app = create_app(scenario_path=SCENARIO, artifact_root=tmp_path / "ws-runs")
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as websocket:
            snapshot = websocket.receive_json()
            assert snapshot["run_id"]
            assert snapshot["controller"]["route_beliefs"]["north_channel"]["status"] == "unknown"
