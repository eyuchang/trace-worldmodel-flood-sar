from pathlib import Path

from trace_jepa.workbench.d05_server import D05Engine


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "d04_geography"
)


def run_until(engine: D05Engine, predicate, *, limit: int = 5_000) -> None:
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
        description="Concurrent scheduling test.",
        access_hint="water",
    )


def test_multiple_transfer_ports_are_available() -> None:
    engine = D05Engine(FIXTURE)

    assert len(engine.transfer_ports) >= 2
    assert all(port.water_node for port in engine.transfer_ports)
    assert all(port.road_node for port in engine.transfer_ports)


def test_response_is_prepared_while_drone_is_enroute() -> None:
    engine = D05Engine(FIXTURE)
    incident = create_water_incident(engine)

    preparation = engine.preparations[incident.incident_id]

    assert preparation.asset_kind == "boat"
    assert preparation.status == "prepared"

    survey_tasks = [
        task
        for task in engine.tasks.values()
        if (
            task.incident_id == incident.incident_id
            and task.task_kind == "survey"
            and task.status == "active"
        )
    ]

    assert survey_tasks

    assert any(
        entry["event_type"] == "PARALLEL_RESPONSE_READINESS"
        for entry in engine.trace_entries
    )


def test_ambulance_dispatches_when_boat_picks_up_patients() -> None:
    engine = D05Engine(FIXTURE)
    incident = create_water_incident(engine)

    run_until(
        engine,
        lambda: any(
            asset.kind == "boat"
            and asset.state == "evacuating"
            and asset.cargo_count > 0
            for asset in engine.assets.values()
        ),
    )

    boat = next(
        asset
        for asset in engine.assets.values()
        if asset.kind == "boat" and asset.cargo_count > 0
    )

    ambulance_tasks = [
        task
        for task in engine.tasks.values()
        if (
            task.incident_id == incident.incident_id
            and task.task_kind == "hospital_transfer"
        )
    ]

    assert ambulance_tasks
    assert ambulance_tasks[0].assigned_asset_id is not None

    ambulance = engine.assets[ambulance_tasks[0].assigned_asset_id]

    assert ambulance.state in {
        "enroute_transfer_pickup",
        "waiting_at_transfer_port",
        "loading",
        "evacuating",
    }

    # The boat is still en route, so this is genuinely concurrent.
    assert boat.state == "evacuating"
    assert incident.people_at_transfer == 0

    assert any(
        entry["event_type"] == "AMBULANCE_DISPATCHED_EARLY"
        for entry in engine.trace_entries
    )


def test_boat_remains_at_selected_dock_after_handoff() -> None:
    engine = D05Engine(FIXTURE)
    incident = create_water_incident(engine)

    run_until(
        engine,
        lambda: incident.people_at_transfer > 0,
    )

    schedule = engine.transfer_schedules[incident.incident_id]
    dock = next(
        port
        for port in engine.transfer_ports
        if port.dock_id == schedule.dock_id
    )
    boat = engine.assets[schedule.boat_id]

    assert boat.state == "standby_at_dock"
    assert boat.home_node == dock.water_node
    assert boat.point == (dock.longitude, dock.latitude)


def test_temporal_trace_contains_expected_and_actual_times() -> None:
    engine = D05Engine(FIXTURE)
    incident = create_water_incident(engine)

    run_until(
        engine,
        lambda: incident.status == "completed",
    )

    event_types = {
        entry["event_type"]
        for entry in engine.trace_entries
    }

    assert "SCHEDULE_COMMITTED" in event_types
    assert "SCHEDULE_MILESTONE" in event_types
    assert "TRANSFER_DOCK_SELECTED" in event_types
    assert "RENDEZVOUS_HANDOFF_STARTED" in event_types

    assert all(
        timing.expected_arrival_at >= timing.dispatched_at
        for timing in engine.task_timings.values()
    )

    assert any(
        timing.actual_arrival_at is not None
        for timing in engine.task_timings.values()
    )


def test_material_parameter_change_revises_active_eta() -> None:
    engine = D05Engine(FIXTURE)
    create_water_incident(engine)

    run_until(
        engine,
        lambda: any(
            asset.kind == "boat"
            and asset.state == "evacuating"
            and asset.current_task_id is not None
            for asset in engine.assets.values()
        ),
    )

    engine.update_config({"river_level": 1.4})

    assert any(
        entry["event_type"] == "SCHEDULE_REVISED"
        for entry in engine.trace_entries
    )


def test_ui_has_zoom_scaled_markers_and_time_speed_control() -> None:
    html = (
        Path(__file__).parents[1]
        / "src"
        / "trace_jepa"
        / "workbench"
        / "d05_static"
        / "index.html"
    ).read_text(encoding="utf-8")

    assert 'id="speedSelect"' in html
    assert 'action: "speed"' in html
    assert "markerScaleForZoom" in html
    assert 'map.on("zoom", updateMarkerScales)' in html
    assert 'id="scheduleList"' in html


def test_complete_hospital_chain_still_finishes() -> None:
    engine = D05Engine(FIXTURE)
    incident = create_water_incident(engine)

    run_until(
        engine,
        lambda: incident.status == "completed",
    )

    assert incident.people_waiting == 0
    assert incident.people_onboard == 0
    assert incident.people_at_transfer == 0
    assert incident.people_delivered == 4
