from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from trace_jepa.contracts import ActionInstance
from trace_jepa.workbench.api import create_app
from trace_jepa.workbench.engine import DynamicRun
from trace_jepa.workbench.models import EventType, ScenarioLevel
from trace_jepa.workbench.navigation import plan_route_constrained_action


SCENARIO = (
    Path(__file__).parents[1]
    / "configs"
    / "scenarios"
    / "riverside_flood_dynamic_v2.yaml"
)


def make_run(tmp_path: Path) -> DynamicRun:
    return DynamicRun(scenario_path=SCENARIO, artifact_root=tmp_path / "runs")


def test_dynamic_scenario_starts_without_a_stale_incident_marker(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    assert run.state.truth.groups == {}
    assert run.state.controller.known_groups == {}
    assert run.state.metrics.pending_people == 0


def test_repeat_call_updates_same_active_incident_instead_of_stacking_marker(
    tmp_path: Path,
) -> None:
    app = create_app(scenario_path=SCENARIO, artifact_root=tmp_path / "api-runs")
    with TestClient(app) as client:
        first = client.post(
            "/api/emergency-call",
            json={
                "location_label": "Riverside Apartments",
                "x": 88,
                "y": 66,
                "people": 4,
                "severity": 0.55,
                "deadline_s": 1200,
            },
        )
        assert first.status_code == 200
        assert first.json()["resolution"] == "created"

        second = client.post(
            "/api/emergency-call",
            json={
                "location_label": "Riverside Apartments",
                "x": 88.5,
                "y": 66.4,
                "people": 6,
                "severity": 0.70,
                "deadline_s": 900,
            },
        )
        assert second.status_code == 200
        body = second.json()
        assert body["resolution"] == "updated"
        assert body["people_waiting"] == 6
        assert body["alert_count"] == 2

        third = client.post(
            "/api/emergency-call",
            json={
                "location_label": "Riverside Apartments",
                "x": 88.4,
                "y": 66.2,
                "people": 3,
                "severity": 0.72,
                "deadline_s": 850,
                "count_semantics": "additional_people",
            },
        )
        assert third.status_code == 200
        assert third.json()["resolution"] == "merged"
        assert third.json()["people_waiting"] == 9
        assert third.json()["alert_count"] == 3

        state = client.get("/api/state").json()
        assert len(state["truth"]["groups"]) == 1
        group = next(iter(state["truth"]["groups"].values()))
        assert group["people_waiting"] == 9
        assert group["people"] == 9


def test_distinct_location_creates_a_second_incident(tmp_path: Path) -> None:
    app = create_app(scenario_path=SCENARIO, artifact_root=tmp_path / "api-runs")
    with TestClient(app) as client:
        for payload in (
            {
                "location_label": "Riverside Apartments",
                "x": 88,
                "y": 66,
                "people": 4,
                "severity": 0.55,
                "deadline_s": 1200,
            },
            {
                "location_label": "East School Roof",
                "x": 70,
                "y": 58,
                "people": 3,
                "severity": 0.70,
                "deadline_s": 900,
            },
        ):
            response = client.post("/api/emergency-call", json=payload)
            assert response.status_code == 200
            assert response.json()["resolution"] == "created"

        state = client.get("/api/state").json()
        assert len(state["truth"]["groups"]) == 2
        assert sorted(group["people_waiting"] for group in state["truth"]["groups"].values()) == [3, 4]


def test_boat_pickup_is_not_rescue_until_safe_delivery(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    run.state.config.s2.water_rise_rate = 0.0

    async def exercise() -> None:
        await run.inject_event(
            event_type=EventType.EMERGENCY_CALL,
            scenario_level=ScenarioLevel.CORE,
            payload={
                "group_id": "group_riverside",
                "location_label": "Riverside Apartments",
                "position": {"x": 88.0, "y": 66.0},
                "people": 4,
                "severity": 0.55,
                "deadline_s": 1200.0,
                "safe_location_id": "safe_transfer_dock",
            },
        )

        for _ in range(20):
            await run.step(10.0)
            if any(
                event.event_type == EventType.PEOPLE_PICKED_UP
                for event in run.event_store.all()
            ):
                break

        group = run.state.truth.groups["group_riverside"]
        boat = run.state.truth.assets["rescue_boat_1"]
        assert group.people_waiting == 0
        assert group.people_onboard == 4
        assert group.people_delivered == 0
        assert group.rescued is False
        assert boat.passenger_count == 4
        assert boat.status in {"awaiting_clearance", "moving"}
        assert run.state.metrics.rescued_people == 0

        for _ in range(20):
            await run.step(10.0)
            if run.state.metrics.rescued_people == 4:
                break

    asyncio.run(exercise())

    group = run.state.truth.groups["group_riverside"]
    boat = run.state.truth.assets["rescue_boat_1"]
    event_types = [event.event_type for event in run.event_store.all()]

    assert EventType.BOARDING_STARTED in event_types
    assert EventType.PEOPLE_PICKED_UP in event_types
    assert EventType.UNLOADING_STARTED in event_types
    assert EventType.PEOPLE_DELIVERED in event_types
    assert EventType.ASSET_STANDBY in event_types
    assert group.people_waiting == 0
    assert group.people_onboard == 0
    assert group.people_delivered == 4
    assert group.rescued is True
    assert boat.position == boat.home_position
    assert boat.passenger_count == 0
    assert boat.status == "standby"
    assert boat.mission_phase == "standby"
    assert run.state.metrics.rescued_people == 4


def test_evacuation_to_safety_uses_reverse_waterway_edges(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    run.emit(
        EventType.EMERGENCY_CALL,
        source="test",
        payload={
            "group_id": "group_riverside",
            "location_label": "Riverside Apartments",
            "position": {"x": 88.0, "y": 66.0},
            "people": 4,
        },
    )
    boat = run.state.truth.assets["rescue_boat_1"]
    boat.position = run.state.truth.groups["group_riverside"].position
    boat.passenger_count = 4
    boat.passenger_group_ids = ["group_riverside"]
    boat.status = "awaiting_clearance"
    run.state.controller.known_assets[boat.asset_id] = boat.model_copy(deep=True)

    action = ActionInstance(
        action_type="evacuate_to_safety",
        actor_id=boat.asset_id,
        origin="incident_pickup",
        destination="safe_transfer_dock",
        route_id="south_detour",
        parameters={
            "group_ids": ["group_riverside"],
            "people_count": 4,
            "safe_location_id": "safe_transfer_dock",
        },
    )
    navigation = plan_route_constrained_action(run.state, action, view="controller")

    assert navigation.target == boat.home_position
    assert navigation.segments
    assert all(segment.mode == "water" for segment in navigation.segments)
    assert all(segment.direction == "reverse" for segment in navigation.segments)
    assert all(segment.direction != "direct" for segment in navigation.segments)



def test_asset_heading_updates_for_visual_animation(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    run.emit(
        EventType.ASSET_MOVED,
        source="test",
        payload={
            "asset_id": "rescue_boat_1",
            "position": {"x": 16.0, "y": 20.0},
            "resource": 0.99,
            "path_index": 0,
        },
    )
    assert round(run.state.truth.assets["rescue_boat_1"].heading_degrees, 3) == 45.0

def test_browser_uses_asset_specific_svg_animation_and_waiting_counts() -> None:
    app_path = (
        Path(__file__).parents[1]
        / "src"
        / "trace_jepa"
        / "workbench"
        / "static"
        / "app.js"
    )
    source = app_path.read_text(encoding="utf-8")
    styles = app_path.with_name("styles.css").read_text(encoding="utf-8")

    assert "function droneIcon" in source
    assert "function boatIcon" in source
    assert "animateTransform" in source
    assert "group.people_waiting" in source
    assert "asset.passenger_count" in source
    assert "callCountSemantics" in app_path.with_name("index.html").read_text(encoding="utf-8")
    assert "callResult" in app_path.with_name("index.html").read_text(encoding="utf-8")
    assert "glyphs =" not in source
    assert "@keyframes rotorSpin" in styles
    assert "@keyframes boatBob" in styles
