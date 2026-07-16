from pathlib import Path

from trace_jepa.workbench.d04_server import D04Engine
from trace_jepa.workbench.real_geography import (
    load_real_geography,
)


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "d04_geography"
)


def run_until(
    engine: D04Engine,
    predicate,
    *,
    limit: int = 2_000,
) -> None:
    for _ in range(limit):
        if predicate():
            return

        engine.tick(1.0)

    raise AssertionError(
        "Condition did not become true before the limit."
    )


def test_real_geography_loads() -> None:
    geography = load_real_geography(FIXTURE)

    assert geography.water.nodes
    assert geography.road.nodes
    assert geography.scenario["hospital"]
    assert geography.scenario["transfer_port"]


def test_default_fleet_is_multi_asset_and_docked() -> None:
    engine = D04Engine(FIXTURE)

    kinds = [
        asset.kind
        for asset in engine.assets.values()
    ]

    assert kinds.count("drone") == 3
    assert kinds.count("boat") == 2
    assert kinds.count("ambulance") == 2

    assert all(
        asset.state == "standby"
        for asset in engine.assets.values()
    )


def test_map_click_coordinates_remain_geographic() -> None:
    engine = D04Engine(FIXTURE)

    longitude = -121.789
    latitude = 38.004

    incident = engine.add_incident(
        longitude=longitude,
        latitude=latitude,
        people=4,
        severity=3,
        deadline_min=20,
        description="Geographic alarm.",
        access_hint="auto",
    )

    assert incident.longitude == longitude
    assert incident.latitude == latitude


def test_new_incident_dispatches_drone_first() -> None:
    engine = D04Engine(FIXTURE)

    incident = engine.add_incident(
        longitude=-121.789,
        latitude=38.004,
        people=4,
        severity=3,
        deadline_min=20,
        description="Alarm requiring verification.",
        access_hint="water",
    )

    active_tasks = [
        task
        for task in engine.tasks.values()
        if (
            task.incident_id == incident.incident_id
            and task.status == "active"
        )
    ]

    assert len(active_tasks) == 1
    assert active_tasks[0].task_kind == "survey"

    asset = engine.assets[
        active_tasks[0].assigned_asset_id
    ]

    assert asset.kind == "drone"


def test_idle_drones_do_not_move_randomly() -> None:
    engine = D04Engine(FIXTURE)

    positions = {
        asset.asset_id: asset.point
        for asset in engine.assets.values()
        if asset.kind == "drone"
    }

    for _ in range(20):
        engine.tick(1.0)

    for asset_id, initial in positions.items():
        assert engine.assets[asset_id].point == initial


def test_water_incident_becomes_boat_task_after_survey() -> None:
    engine = D04Engine(FIXTURE)
    engine.config["sensor_noise"] = 0.0

    incident = engine.add_incident(
        longitude=-121.770,
        latitude=38.004,
        people=4,
        severity=3,
        deadline_min=20,
        description="Water alarm.",
        access_hint="water",
    )

    run_until(
        engine,
        lambda: incident.access_mode == "water",
    )

    active_boats = [
        asset
        for asset in engine.assets.values()
        if (
            asset.kind == "boat"
            and asset.current_task_id is not None
        )
    ]

    assert active_boats


def test_land_incident_becomes_ambulance_task_after_survey() -> None:
    engine = D04Engine(FIXTURE)
    engine.config["sensor_noise"] = 0.0

    incident = engine.add_incident(
        longitude=-121.775,
        latitude=38.008,
        people=3,
        severity=3,
        deadline_min=20,
        description="Land alarm.",
        access_hint="land",
    )

    run_until(
        engine,
        lambda: incident.access_mode == "land",
    )

    active_ambulances = [
        asset
        for asset in engine.assets.values()
        if (
            asset.kind == "ambulance"
            and asset.current_task_id is not None
        )
    ]

    assert active_ambulances


def test_boat_handoff_continues_by_ambulance_to_hospital() -> None:
    engine = D04Engine(FIXTURE)
    engine.config["sensor_noise"] = 0.0

    incident = engine.add_incident(
        longitude=-121.760,
        latitude=38.000,
        people=4,
        severity=4,
        deadline_min=20,
        description="End-to-end water rescue.",
        access_hint="water",
    )

    run_until(
        engine,
        lambda: incident.status == "completed",
        limit=5_000,
    )

    assert incident.people_waiting == 0
    assert incident.people_onboard == 0
    assert incident.people_at_transfer == 0
    assert incident.people_delivered == 4

    event_types = {
        entry["event_type"]
        for entry in engine.trace_entries
    }

    assert "PORT_HANDOFF" in event_types
    assert "RESCUE_COMPLETED" in event_types


def test_high_priority_water_incident_requests_preemption() -> None:
    engine = D04Engine(FIXTURE)

    engine.assets["rescue_boat_2"].grounded = True

    first = engine._add_preverified_water_incident(
        node_id="w4",
        people=2,
        severity=2,
        deadline_min=35,
        description="Moderate event.",
    )

    assert first.assigned_asset_id == "rescue_boat_1"

    second = engine._add_preverified_water_incident(
        node_id="w6",
        people=8,
        severity=5,
        deadline_min=5,
        description="Critical event.",
    )

    boat = engine.assets["rescue_boat_1"]

    assert boat.pending_task_id is not None

    pending_task = engine.tasks[
        boat.pending_task_id
    ]

    assert pending_task.incident_id == second.incident_id

    assert any(
        entry["event_type"]
        == "PREEMPTION_PROPOSED"
        for entry in engine.trace_entries
    )


def test_passenger_carrying_asset_is_not_preemptible() -> None:
    engine = D04Engine(FIXTURE)

    engine.assets["rescue_boat_2"].grounded = True

    boat = engine.assets["rescue_boat_1"]
    boat.cargo_count = 3
    boat.state = "evacuating"

    engine._add_preverified_water_incident(
        node_id="w6",
        people=8,
        severity=5,
        deadline_min=5,
        description="Critical event.",
    )

    assert boat.pending_task_id is None
