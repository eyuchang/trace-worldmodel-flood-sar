from __future__ import annotations

import asyncio
from pathlib import Path

from trace_jepa.contracts import ActionInstance
from trace_jepa.workbench.engine import DynamicRun
from trace_jepa.workbench.models import EventType, EventVisibility, ScenarioLevel
from trace_jepa.workbench.navigation import plan_route_constrained_action


SCENARIO = Path(__file__).parents[1] / "configs" / "scenarios" / "riverside_flood_v1.yaml"


def make_run(tmp_path: Path) -> DynamicRun:
    return DynamicRun(scenario_path=SCENARIO, artifact_root=tmp_path / "runs")


def seed_riverside_group(run: DynamicRun) -> None:
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
            "safe_location_id": "safe_transfer_dock",
        },
    )


def test_boat_at_hazard_returns_on_network_before_switching_routes(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    seed_riverside_group(run)
    boat = run.state.truth.assets["rescue_boat_1"]
    hazard = run.state.truth.routes["north_channel"].blockage_position
    assert hazard is not None
    boat.position = hazard
    run.state.controller.known_assets[boat.asset_id].position = hazard
    north_belief = run.state.controller.route_beliefs["north_channel"]
    north_belief.status = "blocked"
    north_belief.blocked_segment_index = 3

    action = ActionInstance(
        action_type="dispatch_rescue_boat",
        actor_id="rescue_boat_1",
        destination="group_riverside",
        route_id="south_detour",
        parameters={"group_id": "group_riverside", "people_count": 4},
    )
    navigation = plan_route_constrained_action(run.state, action, view="controller")

    route_sequence = [segment.route_id for segment in navigation.segments]
    assert route_sequence[:3] == ["north_channel", "north_channel", "north_channel"]
    assert navigation.segments[0].direction == "reverse"
    assert "south_detour" in route_sequence[3:]
    assert all(segment.mode == "water" for segment in navigation.segments)
    assert all(segment.direction != "direct" for segment in navigation.segments)


def test_boat_stops_at_blocked_edge_instead_of_crossing_it(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    seed_riverside_group(run)
    run.state.config.auto_plan = False
    action = ActionInstance(
        action_type="dispatch_rescue_boat",
        actor_id="rescue_boat_1",
        destination="group_riverside",
        route_id="north_channel",
        parameters={"group_id": "group_riverside", "people_count": 4},
    )
    navigation = plan_route_constrained_action(run.state, action, view="controller")
    run.emit(
        EventType.ACTION_STARTED,
        source="test_dispatcher",
        payload={
            "asset_id": action.actor_id,
            "action_type": action.action_type,
            "route_id": action.route_id,
            "group_id": "group_riverside",
            "path": [point.model_dump() for point in navigation.points],
            "path_segments": [segment.model_dump(mode="json") for segment in navigation.segments],
            "target": navigation.target.model_dump(),
            "record_id": "test-record",
            "record_version": 1,
            "plan_id": "test-north",
        },
    )

    async def exercise() -> None:
        for _ in range(40):
            await run.step(1.0)
            if any(event.event_type == EventType.ACTION_INTERRUPTED for event in run.event_store.all()):
                break

    asyncio.run(exercise())
    interruption = next(
        event for event in run.event_store.all() if event.event_type == EventType.ACTION_INTERRUPTED
    )
    boat = run.state.truth.assets["rescue_boat_1"]
    assert interruption.payload["edge_index"] == 3
    assert abs(boat.position.x - 60.0) < 1e-6
    assert abs(boat.position.y - 64.0) < 1e-6
    assert boat.position != run.state.truth.groups["group_riverside"].position


def test_s1_change_produces_explicit_reasoning_and_trace_versions(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    seed_riverside_group(run)

    async def exercise() -> None:
        await run.plan_now()
        await run.inject_event(
            event_type=EventType.SET_S1_PARAMETERS,
            scenario_level=ScenarioLevel.S1,
            payload={"sensor_noise": 0.42, "ood_severity": 0.61},
        )

    asyncio.run(exercise())
    cycle = run.state.controller.latest_reasoning
    assert cycle is not None and cycle.completed
    assert [step.stage for step in cycle.steps] == [
        "trigger",
        "state",
        "prediction",
        "claim",
        "trace",
        "plan",
    ] or [step.stage for step in cycle.steps] == [
        "trigger",
        "state",
        "prediction",
        "claim",
        "trace",
        "plan",
        "commitment",
    ]
    assert cycle.affected_record_ids
    assert run.state.metrics.parameter_revisions > 0
    latest = {}
    for record in run.runtime.repository.all():
        latest[record.record_id] = record
    assert any(record.metadata.get("semantic_revision_of") for record in latest.values())


def test_truth_only_shock_does_not_revise_trace_until_observed(tmp_path: Path) -> None:
    run = make_run(tmp_path)

    async def exercise() -> None:
        await run.plan_now()
        before = len(run.runtime.repository.all())
        await run.inject_event(
            event_type=EventType.INJECT_SHOCK,
            scenario_level=ScenarioLevel.S4,
            visibility=EventVisibility.TRUTH,
            payload={"shock_type": "levee_breach", "severity": 0.8},
        )
        return before

    before = asyncio.run(exercise())
    assert len(run.runtime.repository.all()) == before
    cycle = run.state.controller.latest_reasoning
    assert cycle is not None
    assert cycle.steps[-1].details["trace_update"] == "none_until_observed"
