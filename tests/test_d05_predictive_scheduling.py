from pathlib import Path

from fastapi.testclient import TestClient

from trace_jepa.workbench.d05_server import D05Engine, create_app


FIXTURE = Path(__file__).parent / "fixtures" / "d04_geography"


def run_until(engine: D05Engine, predicate, *, limit: int = 8_000) -> None:
    for _ in range(limit):
        if predicate():
            return
        engine.tick(1.0)
    raise AssertionError("Condition did not become true before the limit.")


def create_water_incident(engine: D05Engine):
    engine.config["sensor_noise"] = 0.0
    return engine.add_incident(
        longitude=-121.760,
        latitude=38.000,
        people=4,
        severity=4,
        deadline_min=20,
        description="Water rescue for predictive scheduling.",
        access_hint="water",
    )


def test_boats_and_drones_are_anchored_at_transfer_docks() -> None:
    engine = D05Engine(FIXTURE)
    port_points = {
        (dock.longitude, dock.latitude)
        for dock in engine.transfer_ports
    }

    water_assets = [
        asset
        for asset in engine.assets.values()
        if asset.kind in {"boat", "drone"}
    ]

    assert len([asset for asset in water_assets if asset.kind == "boat"]) == 2
    assert len([asset for asset in water_assets if asset.kind == "drone"]) == 3
    assert all(asset.point in port_points for asset in water_assets)
    assert all(asset.state == "standby_at_dock" for asset in water_assets)
    assert all(asset.asset_id in engine.asset_docks for asset in water_assets)


def test_alert_prepares_response_while_drone_is_airborne() -> None:
    engine = D05Engine(FIXTURE)
    incident = create_water_incident(engine)

    preparation = engine.preparations[incident.incident_id]
    assert preparation.asset_kind == "boat"
    assert preparation.status == "prepared"

    survey_task = next(
        task
        for task in engine.tasks.values()
        if task.incident_id == incident.incident_id
        and task.task_kind == "survey"
    )
    assert survey_task.status == "active"
    assert survey_task.assigned_asset_id is not None

    assert any(
        entry["event_type"] == "RESPONSE_PREPARATION"
        for entry in engine.trace_entries
    )


def test_ambulance_is_dispatched_when_boat_picks_up_patients() -> None:
    engine = D05Engine(FIXTURE)
    incident = create_water_incident(engine)

    run_until(
        engine,
        lambda: incident.incident_id in engine.transfer_schedules,
    )

    schedule = engine.transfer_schedules[incident.incident_id]
    assert schedule.ambulance_id is not None

    ambulance = engine.assets[schedule.ambulance_id]
    assert ambulance.current_task_id is not None
    assert ambulance.state in {
        "enroute_transfer_pickup",
        "waiting_at_transfer_port",
        "loading",
        "evacuating",
    }

    boat = engine.assets[schedule.boat_id]
    assert boat.cargo_count > 0
    assert boat.state in {"evacuating", "evacuating_to_selected_dock", "unloading", "standby_at_dock"}

    events = {entry["event_type"] for entry in engine.trace_entries}
    assert "TRANSFER_DOCK_SELECTED" in events
    assert "AMBULANCE_DISPATCHED_EARLY" in events


def test_ambulance_can_arrive_before_boat_and_wait() -> None:
    engine = D05Engine(FIXTURE)
    incident = create_water_incident(engine)

    run_until(
        engine,
        lambda: any(
            asset.state == "waiting_at_transfer_port"
            for asset in engine.assets.values()
            if asset.kind == "ambulance"
        ),
    )

    assert incident.people_onboard > 0
    assert incident.people_at_transfer == 0
    assert any(
        entry["event_type"] == "AMBULANCE_ARRIVED_EARLY"
        for entry in engine.trace_entries
    )


def test_boat_remains_at_selected_dock_after_handoff() -> None:
    engine = D05Engine(FIXTURE)
    incident = create_water_incident(engine)

    run_until(
        engine,
        lambda: incident.incident_id in engine.transfer_schedules,
    )
    schedule = engine.transfer_schedules[incident.incident_id]
    dock = next(
        dock
        for dock in engine.transfer_ports
        if dock.dock_id == schedule.dock_id
    )
    boat = engine.assets[schedule.boat_id]

    run_until(
        engine,
        lambda: boat.state == "standby_at_dock" and boat.cargo_count == 0,
    )

    assert boat.home_node == dock.water_node
    assert engine.asset_docks[boat.asset_id] == dock.dock_id
    assert boat.point == (dock.longitude, dock.latitude)


def test_water_rescue_completes_with_timing_recorded() -> None:
    engine = D05Engine(FIXTURE)
    incident = create_water_incident(engine)

    run_until(engine, lambda: incident.status == "completed")

    assert incident.people_waiting == 0
    assert incident.people_onboard == 0
    assert incident.people_at_transfer == 0
    assert incident.people_delivered == 4

    transfer = engine.transfer_schedules[incident.incident_id]
    assert transfer.actual_boat_arrival_at is not None
    assert transfer.actual_ambulance_arrival_at is not None
    assert transfer.handoff_started_at is not None
    assert transfer.handoff_completed_at is not None
    assert transfer.status == "completed"

    events = {entry["event_type"] for entry in engine.trace_entries}
    assert "TRANSFER_DOCK_SELECTED" in events
    assert "PORT_HANDOFF" in events
    assert "RENDEZVOUS_HANDOFF_STARTED" in events
    assert "RESCUE_COMPLETED" in events


def test_speed_control_endpoint_restores_time_scale_control() -> None:
    app = create_app(FIXTURE)

    with TestClient(app) as client:
        response = client.post(
            "/api/d05/control",
            json={"action": "speed", "value": 10},
        )
        assert response.status_code == 200
        assert response.json()["time_scale"] == 10.0


def test_ui_scales_markers_and_shows_predictive_schedule() -> None:
    html = (
        Path(__file__).parents[1]
        / "src"
        / "trace_jepa"
        / "workbench"
        / "d05_static"
        / "index.html"
    ).read_text(encoding="utf-8")

    assert 'id="speedSelect"' in html
    assert "markerScaleForZoom" in html
    assert 'map.on("zoom", updateMarkerScales)' in html
    assert 'id="scheduleList"' in html
    assert "transfer_schedules" in html
    assert "task_timings" in html
