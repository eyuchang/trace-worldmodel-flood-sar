from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from trace_jepa.refresh import (
    AdaptiveRefreshPolicy,
    NoRefreshPolicy,
    RefreshDecision,
    RefreshMode,
    TriggerFamily,
)
from trace_jepa.workbench.engine import DynamicRun
from trace_jepa.workbench.models import EventType, ScenarioLevel


SCENARIO = Path("configs/scenarios/riverside_flood_dynamic_v2.yaml")


def _seed_group(run: DynamicRun) -> None:
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


class AlwaysGaugePolicy:
    name = "test_always_gauge"

    def decide(self, state, claims, pending):
        if pending is None:
            return RefreshDecision(
                policy=self.name,
                mode=RefreshMode.CONTINUE,
                rationale="no pending commitment",
            )
        return RefreshDecision(
            policy=self.name,
            commitment_id=pending.commitment_id,
            claim_id=pending.claim_id,
            triggered_families=(TriggerFamily.PREDICTED,),
            mode=RefreshMode.ACQUIRE,
            q=pending.flip_risk,
            d_or_margin=0.0,
            voi_table=pending.channels,
            selected_channel="gauge_poll",
            rationale="integration-test channel request",
        )


def test_explicit_no_refresh_has_zero_policy_driven_evidence(tmp_path: Path) -> None:
    run = DynamicRun(
        scenario_path=SCENARIO,
        artifact_root=tmp_path,
        refresh_scheduler=NoRefreshPolicy(),
    )
    _seed_group(run)
    asyncio.run(run.plan_now())
    events = run.event_store.all()
    assert not any(
        event.event_type
        in {
            EventType.REFRESH_TRIGGERED,
            EventType.GAUGE_POLL,
            EventType.REQUEST_SURVEY,
            EventType.EVIDENCE_ACQUIRED,
        }
        for event in events
    )
    assert any(
        event.event_type == EventType.ACTION_STARTED
        and event.payload.get("action_type") != "verify_route"
        for event in events
    )


def test_adaptive_policy_emits_attributable_trigger_and_withdrawal(
    tmp_path: Path,
) -> None:
    run = DynamicRun(
        scenario_path=SCENARIO,
        artifact_root=tmp_path,
        refresh_scheduler=AdaptiveRefreshPolicy(),
        epsilon_c=1.0,
    )
    run.state.controller.route_beliefs["south_detour"].clearance_valid_until = 1.0
    _seed_group(run)
    asyncio.run(run.plan_now())
    triggers = [
        event
        for event in run.event_store.all()
        if event.event_type == EventType.REFRESH_TRIGGERED
    ]
    assert triggers
    assert all(event.payload["claim_id"] for event in triggers)
    assert all(event.payload["record_id"] for event in triggers)
    assert all(isinstance(event.payload["voi_table"], list) for event in triggers)
    assert any(
        event.event_type == EventType.AUTH_WITHDRAWN
        for event in run.event_store.all()
    )


def test_controller_visible_depth_innovation_fires_observed_family(
    tmp_path: Path,
) -> None:
    run = DynamicRun(
        scenario_path=SCENARIO,
        artifact_root=tmp_path,
        refresh_scheduler=AdaptiveRefreshPolicy(),
        epsilon_c=1.0,
    )
    run.emit(
        EventType.OBSERVATION,
        source="integration_gauge",
        scenario_level=ScenarioLevel.S1,
        payload={
            "kind": "route_depth",
            "route_id": "south_detour",
            "water_depth": 0.38,
            "source": "integration_gauge",
            "observed_at": 0.0,
        },
    )
    _seed_group(run)
    asyncio.run(run.plan_now())
    observed = [
        event
        for event in run.event_store.all()
        if event.event_type == EventType.REFRESH_TRIGGERED
        and event.payload["family"] == "observed"
    ]
    assert len(observed) == 1
    assert observed[0].payload["d_or_margin"] is not None


def test_gauge_poll_samples_at_request_and_reveals_only_at_delivery(
    tmp_path: Path,
) -> None:
    run = DynamicRun(
        scenario_path=SCENARIO,
        artifact_root=tmp_path,
        refresh_scheduler=AlwaysGaugePolicy(),
    )
    _seed_group(run)
    initial_visible_depths = {
        route_id: belief.water_depth
        for route_id, belief in run.state.controller.route_beliefs.items()
    }
    asyncio.run(run.plan_now())

    poll = next(
        event
        for event in run.event_store.all()
        if event.event_type == EventType.GAUGE_POLL
    )
    route_id = poll.payload["route_id"]
    sampled_depth = poll.payload["sampled_water_depth"]
    assert poll.payload["latency_s"] == pytest.approx(5.0)
    assert poll.payload["cost"] == pytest.approx(0.2)
    assert (
        run.state.controller.route_beliefs[route_id].water_depth
        == initial_visible_depths[route_id]
    )
    assert all(
        "sampled_water_depth" not in pending
        for pending in run.state.controller.pending_evidence
    )

    async def advance() -> None:
        run.state.config.auto_plan = False
        run.emit(
            EventType.SET_S2_PARAMETERS,
            source="test",
            scenario_level=ScenarioLevel.S2,
            payload={"water_rise_rate": 0.01},
        )
        for _ in range(5):
            await run.step(1.0)

    asyncio.run(advance())
    belief = run.state.controller.route_beliefs[route_id]
    assert belief.water_depth == pytest.approx(sampled_depth)
    assert run.state.truth.routes[route_id].water_depth != pytest.approx(sampled_depth)
    acquired = [
        event
        for event in run.event_store.all()
        if event.event_type == EventType.EVIDENCE_ACQUIRED
        and event.payload.get("channel") == "gauge_poll"
    ]
    assert len(acquired) == 1
    assert acquired[0].payload["delivered_at"] == pytest.approx(
        poll.payload["deliver_at"]
    )
    assert run.state.controller.pending_evidence == []


def test_drone_survey_records_exact_flight_cost_and_latency(tmp_path: Path) -> None:
    run = DynamicRun(
        scenario_path=SCENARIO,
        artifact_root=tmp_path,
        refresh_scheduler=NoRefreshPolicy(),
    )
    _seed_group(run)

    async def exercise() -> None:
        await run.inject_event(
            event_type=EventType.REQUEST_SURVEY,
            scenario_level=ScenarioLevel.S5,
            payload={"route_id": "south_detour", "requested_by": "test"},
        )
        await run.plan_now()
        for _ in range(300):
            if any(
                event.event_type == EventType.EVIDENCE_ACQUIRED
                and event.payload.get("channel") == "drone_survey"
                for event in run.event_store.all()
            ):
                return
            await run.step(1.0)
        raise AssertionError("drone survey did not complete")

    asyncio.run(exercise())
    started = next(
        event
        for event in run.event_store.all()
        if event.event_type == EventType.ACTION_STARTED
        and event.payload.get("action_type") == "verify_route"
    )
    acquired = next(
        event
        for event in run.event_store.all()
        if event.event_type == EventType.EVIDENCE_ACQUIRED
        and event.payload.get("channel") == "drone_survey"
    )
    flight_time = acquired.simulation_time - started.simulation_time
    assert acquired.payload["latency_s"] == pytest.approx(flight_time)
    assert acquired.payload["cost"] == pytest.approx(5.0 + flight_time * 0.0009)
