from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from trace_jepa.evaluation import (
    AttributionStatus,
    CommitmentLedgerRow,
    CommitmentUnitLedgerRow,
    FailureCode,
    RefreshLedgerRow,
    RunDiagnostics,
    classify_failure,
    compute_commitment_metrics,
    compute_commitment_unit_metrics,
    compute_proposal_record_metrics,
    compute_refresh_metrics,
    derive_commitment_ledger,
    derive_commitment_unit_ledger,
    derive_refresh_ledger,
    read_hashed_ledger,
    verify_hashed_ledger,
    write_hashed_ledger,
    adjudicate_execution_truth,
)
from trace_jepa.refresh import (
    NoRefreshPolicy,
    RefreshDecision,
    RefreshMode,
    TriggerFamily,
)
from trace_jepa.workbench.engine import DynamicRun
from trace_jepa.workbench.models import EventType
from trace_jepa.workbench.models import SimulationEvent
from trace_jepa.workbench.scenario import load_initial_state


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


class GaugeOncePolicy:
    name = "test_gauge_once"

    def __init__(self) -> None:
        self.requested = False

    def decide(self, state, claims, pending):
        if pending is None or self.requested:
            return RefreshDecision(
                policy=self.name,
                mode=RefreshMode.CONTINUE,
                rationale="no request due",
            )
        self.requested = True
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
            rationale="ledger integration request",
        )


def test_commitment_ledger_is_event_derived_and_conserves_proposals(
    tmp_path: Path,
) -> None:
    run = DynamicRun(
        scenario_path=SCENARIO,
        artifact_root=tmp_path,
        refresh_scheduler=NoRefreshPolicy(),
    )
    _seed_group(run)
    asyncio.run(run.plan_now())
    rows = derive_commitment_ledger(run.event_store.all())
    assert rows
    assert sum(row.executed for row in rows) >= 1
    assert all(row.proposed for row in rows)
    assert all(
        sum((row.executed, row.held, row.escalated)) == 1 for row in rows
    )
    assert all(not row.executed_stale or row.executed for row in rows)

    metrics = compute_commitment_metrics(rows)
    assert metrics.proposed == metrics.executed + metrics.held + metrics.escalated
    assert metrics.executed_stale <= metrics.executed
    assert metrics.coverage == pytest.approx(metrics.executed / metrics.proposed)


def test_clear_alternative_losing_planner_selection_is_not_a_hold() -> None:
    events = [
        SimulationEvent(
            run_id="run",
            sequence=1,
            simulation_time=0.0,
            source="planner",
            event_type=EventType.PLAN_PROPOSED,
            payload={
                "plan_id": "plan-a",
                "record_id": "record-a",
                "record_version": 1,
                "action": {
                    "action_type": "dispatch_rescue_boat",
                    "route_id": "north_channel",
                },
            },
        ),
        SimulationEvent(
            run_id="run",
            sequence=2,
            simulation_time=0.0,
            source="gate",
            event_type=EventType.COMMITMENT_DECISION,
            payload={"plan_id": "plan-a", "decision": "clear"},
        ),
        SimulationEvent(
            run_id="run",
            sequence=3,
            simulation_time=0.0,
            source="planner",
            event_type=EventType.PLAN_PROPOSED,
            payload={
                "plan_id": "plan-b",
                "record_id": "record-b",
                "record_version": 1,
                "action": {
                    "action_type": "dispatch_rescue_boat",
                    "route_id": "south_detour",
                },
            },
        ),
        SimulationEvent(
            run_id="run",
            sequence=4,
            simulation_time=0.0,
            source="gate",
            event_type=EventType.COMMITMENT_DECISION,
            payload={"plan_id": "plan-b", "decision": "clear"},
        ),
        SimulationEvent(
            run_id="run",
            sequence=5,
            simulation_time=0.0,
            source="controller",
            event_type=EventType.PLAN_SELECTED,
            payload={"plan_id": "plan-b"},
        ),
        SimulationEvent(
            run_id="run",
            sequence=6,
            simulation_time=0.0,
            source="dispatcher",
            event_type=EventType.ACTION_STARTED,
            payload={
                "plan_id": "plan-b",
                "truth_safe_at_execution": True,
                "authorization_outside_tolerance": False,
                "executed_stale": False,
            },
        ),
    ]
    rows = derive_commitment_ledger(events)
    assert [row.plan_id for row in rows] == ["plan-b"]
    assert rows[0].executed is True
    assert rows[0].held is False


def test_commitment_units_collapse_repeated_record_versions() -> None:
    common = {
        "plan_id": "boat:one:group:south",
        "record_id": "record-stable",
        "action_class": "dispatch_rescue_boat",
        "route_id": "south_detour",
        "decision": "hold",
        "selected": False,
        "loss_components": {"realized_stale_loss": 0.0},
    }
    records = [
        CommitmentLedgerRow(
            proposal_sequence=10,
            record_version=2,
            proposed_at=10.0,
            held=True,
            **common,
        ),
        CommitmentLedgerRow(
            proposal_sequence=20,
            record_version=4,
            proposed_at=15.0,
            held=True,
            **common,
        ),
        CommitmentLedgerRow(
            proposal_sequence=30,
            record_version=6,
            proposed_at=20.0,
            decision="clear",
            selected=True,
            executed=True,
            execution_sequence=31,
            truth_safe_at_execution=True,
            held=False,
            **{key: value for key, value in common.items() if key not in {"decision", "selected"}},
        ),
    ]

    units = derive_commitment_unit_ledger(records)
    assert len(units) == 1
    unit = units[0]
    assert isinstance(unit, CommitmentUnitLedgerRow)
    assert unit.proposal_record_count == 3
    assert unit.first_record_version == 2
    assert unit.last_record_version == 6
    assert unit.executed is True
    assert unit.held is False

    metrics = compute_commitment_unit_metrics(units, proposal_records=3)
    assert metrics.proposal_records == 3
    assert metrics.proposed == 1
    assert metrics.executed == 1
    assert metrics.coverage == pytest.approx(1.0)

    legacy = compute_proposal_record_metrics(records)
    assert legacy.proposal_records is None
    assert legacy.proposed == 3
    assert legacy.executed == 1
    assert legacy.coverage == pytest.approx(1.0 / 3.0)


def test_commitment_unit_derivation_rejects_unstable_identity() -> None:
    first = CommitmentLedgerRow(
        proposal_sequence=1,
        plan_id="plan-1",
        record_id="record-1",
        record_version=1,
        action_class="dispatch_rescue_boat",
        route_id="south_detour",
        proposed_at=0.0,
        held=True,
        loss_components={},
    )
    second = first.model_copy(
        update={
            "proposal_sequence": 2,
            "record_id": "record-2",
            "record_version": 2,
            "proposed_at": 1.0,
        }
    )
    with pytest.raises(ValueError, match="stable identity"):
        derive_commitment_unit_ledger([first, second])


def test_truth_oracle_keeps_expired_but_true_authorization_out_of_stale_rate() -> None:
    initial = load_initial_state("run", SCENARIO)
    event = SimulationEvent(
        run_id="run",
        sequence=1,
        simulation_time=0.0,
        source="dispatcher",
        event_type=EventType.ACTION_STARTED,
        payload={
            "asset_id": "rescue_boat_1",
            "action_type": "dispatch_rescue_boat",
            "route_id": "south_detour",
            "path": [],
            "path_segments": [],
            "target": {"x": 88.0, "y": 66.0},
            "truth_safe_at_execution": True,
            "authorization_outside_tolerance": True,
            "executed_stale": False,
        },
    )
    labels = adjudicate_execution_truth(initial, [event])
    assert labels[1].truth_safe is True
    assert labels[1].executed_stale is False


def test_refresh_ledger_links_trigger_to_delivered_gauge(tmp_path: Path) -> None:
    run = DynamicRun(
        scenario_path=SCENARIO,
        artifact_root=tmp_path,
        refresh_scheduler=GaugeOncePolicy(),
    )
    _seed_group(run)

    async def exercise() -> None:
        await run.plan_now()
        run.state.config.auto_plan = False
        for _ in range(5):
            await run.step(1.0)

    asyncio.run(exercise())
    rows = derive_refresh_ledger(run.event_store.all())
    assert len(rows) == 1
    row = rows[0]
    assert row.family == "predicted"
    assert row.selected_channel == "gauge_poll"
    assert row.acquisition_sequence is not None
    assert row.cost == pytest.approx(0.2)
    assert row.latency_s == pytest.approx(5.0)
    assert row.usable is True


def test_refresh_metrics_deduplicate_one_acquisition_across_trigger_families() -> None:
    common = {
        "refresh_decision_id": "refresh-1",
        "evidence_request_id": "evidence-1",
        "simulation_time": 10.0,
        "policy": "adaptive",
        "commitment_id": "pending:plan-1",
        "claim_id": "claim-1",
        "record_id": "record-1",
        "record_version": 1,
        "plan_id": "plan-1",
        "selected_channel": "gauge_poll",
        "acquisition_sequence": 99,
        "cost": 0.2,
        "latency_s": 5.0,
        "usable": True,
    }
    rows = [
        RefreshLedgerRow(trigger_sequence=10, family="predicted", **common),
        RefreshLedgerRow(trigger_sequence=11, family="structural", **common),
    ]
    metrics = compute_refresh_metrics(rows)
    assert metrics.trigger_decisions == 1
    assert metrics.trigger_family_events == 2
    assert metrics.evidence_acquisitions == 1
    assert metrics.usable_evidence_acquisitions == 1
    assert metrics.total_cost == pytest.approx(0.2)
    assert metrics.family_counts == {"predicted": 1, "structural": 1}


def test_sidecar_ledger_is_atomic_roundtrippable_and_tamper_evident(
    tmp_path: Path,
) -> None:
    row = CommitmentLedgerRow(
        proposal_sequence=1,
        plan_id="plan-1",
        record_id="record-1",
        record_version=1,
        action_class="dispatch_rescue_boat",
        proposed_at=0.0,
        decision="clear",
        selected=True,
        executed=True,
        execution_sequence=2,
        truth_safe_at_execution=True,
        authorization_outside_tolerance=False,
        loss_components={"realized_stale_loss": 0.0},
    )
    path = tmp_path / "commitment_ledger.jsonl"
    head = write_hashed_ledger(path, [row])
    assert head != "GENESIS"
    assert verify_hashed_ledger(path)
    assert read_hashed_ledger(path, CommitmentLedgerRow) == [row]
    assert not list(tmp_path.glob("*.tmp"))

    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["payload"]["executed_stale"] = True
    path.write_text(json.dumps(envelope) + "\n", encoding="utf-8")
    assert not verify_hashed_ledger(path)
    with pytest.raises(ValueError, match="verification failed"):
        read_hashed_ledger(path, CommitmentLedgerRow)


@pytest.mark.parametrize(
    "updates, expected",
    [
        (
            {
                "registered_disruption_matches": True,
                "storage_chain_valid": False,
                "schema_contract_valid": False,
            },
            FailureCode.INJECTED_DISRUPTION,
        ),
        (
            {"storage_chain_valid": False, "schema_contract_valid": False},
            FailureCode.STORAGE_INTEGRITY,
        ),
        ({"schema_contract_valid": False, "timed_out": True}, FailureCode.CONTRACT_VIOLATION),
        ({"timed_out": True, "model_transient": True}, FailureCode.HARNESS_BUG),
        ({"model_transient": True}, FailureCode.MODEL_TRANSIENT),
        ({"scenario_failed": True}, FailureCode.SCENARIO_OUTCOME),
    ],
)
def test_failure_classifier_uses_fixed_registry_first_priority(
    updates, expected
) -> None:
    classification = classify_failure(RunDiagnostics(**updates))
    assert classification is not None
    assert classification.code == expected


def test_attribution_is_separate_and_model_retry_is_limited_once() -> None:
    first = classify_failure(
        RunDiagnostics(
            model_transient=True,
            model_retry_count=0,
            attribution_status=AttributionStatus.QUALIFIED,
        )
    )
    second = classify_failure(
        RunDiagnostics(
            model_transient=True,
            model_retry_count=1,
            attribution_status=AttributionStatus.QUALIFIED,
        )
    )
    assert first is not None and second is not None
    assert first.attribution_status == AttributionStatus.QUALIFIED
    assert first.retry_model_once is True
    assert second.retry_model_once is False
    assert classify_failure(RunDiagnostics(completed_successfully=True)) is None
