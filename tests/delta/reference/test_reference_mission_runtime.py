from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from trace_jepa.experimental import RevalidationGuard
from trace_jepa.predictor import ToyActionPrefixPredictor
from trace_jepa.runtime import PolicyConfig, PolicyEngine, TraceRuntime
from trace_reference.decision import EvidenceAcquisitionExecutor
from trace_reference.domain import ReferenceEventType
from trace_reference.generation import generate_reference_scenario
from trace_reference.runtime import (
    ReferenceCommitmentLog,
    ReferenceDecisionEngine,
    ReferenceDecisionEngineDependencies,
    ReferenceEventLog,
    ReferenceEvidenceLedger,
    ReferenceMissionRuntime,
    ReferenceRouteService,
    ReferenceScenarioIndex,
    ReferenceTraceGateway,
    ReferenceTraceRepository,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def scenario():
    return generate_reference_scenario(ROOT, seed=20260812)


def _mission_runtime(scenario, root: Path) -> tuple[ReferenceMissionRuntime, ReferenceEventLog]:
    event_log = ReferenceEventLog()
    predictor = ToyActionPrefixPredictor()
    provenance = predictor.provenance()
    guard = RevalidationGuard.bootstrap(
        predictor_version=provenance.predictor_version,
        calibration_version=provenance.calibration_version,
        model_hash=provenance.model_hash,
        calibration_hash=provenance.calibration_hash,
        qualified_families=provenance.qualified_action_types,
    )
    policy = PolicyEngine(
        PolicyConfig(
            policy_version="trace-reference-mission-runtime-test-v1",
            min_model_support=0.60,
            max_ood_score=0.35,
            max_uncertainty=0.30,
            max_rollout_horizon=8,
            max_observation_age_s=3_600,
            require_authority_for=provenance.supported_action_types,
            enable_revalidation_guard=True,
            high_consequence_actions=provenance.supported_action_types,
        ),
        revalidation=guard,
    )
    repository = ReferenceTraceRepository(root)
    ledger = ReferenceEvidenceLedger(root)
    commitments = ReferenceCommitmentLog(root)
    core = TraceRuntime(
        repository=repository,
        ledger=ledger,
        commitments=commitments,
        policy=policy,
    )
    index = ReferenceScenarioIndex.from_physical(
        scenario.geography,
        scenario.gauge_context,
        scenario.physical,
    )
    engine = ReferenceDecisionEngine(
        ReferenceDecisionEngineDependencies(
            scenario=scenario,
            index=index,
            route_service=ReferenceRouteService(index),
            predictor=predictor,
            event_log=event_log,
            trace_gateway=ReferenceTraceGateway(core, event_log),
            evidence_ledger=ledger,
            trace_repository=repository,
            commitment_log=commitments,
            acquisition_executor=EvidenceAcquisitionExecutor(),
            policy_version=policy.config.policy_version,
            environment_contract_version="trace-reference-python311-v1",
        )
    )
    return ReferenceMissionRuntime(scenario, engine), event_log


def test_reference_mission_runtime_merges_public_streams_and_executes_initial_decision(
    scenario,
    tmp_path: Path,
) -> None:
    first = min(
        item.delivered_at_s
        for item in scenario.observations.delivery.envelopes
        if item.delivered_at_s >= 0
    )
    runtime, event_log = _mission_runtime(scenario, tmp_path)
    result = runtime.run(through_s=first)

    assert not result.complete
    assert result.decisions
    assert all(item.decided_at_s <= first for item in result.decisions)
    assert event_log.verify()
    assert tuple(item.at_s for item in event_log.events) == tuple(
        sorted(item.at_s for item in event_log.events)
    )
    replay = event_log.replay()
    assert replay.public_mission_artifacts[ReferenceEventType.CALL_DELIVERED.value]
    assert replay.public_mission_artifacts[
        ReferenceEventType.COORDINATION_MESSAGE_DELIVERED.value
    ]
    assert replay.public_mission_artifacts[ReferenceEventType.RECONCILIATION_UPDATED.value]
    assert runtime.engine.dependencies.trace_repository.verify_chain()
    assert runtime.engine.dependencies.evidence_ledger.verify_chain()
    assert runtime.engine.dependencies.commitment_log.verify_chain()

    public_json = json.dumps(replay.public_mission_artifacts, sort_keys=True)
    for forbidden in ("truth_incident_id", "truth_person_id", "candidate_digest"):
        assert forbidden not in public_json


def test_reference_mission_runtime_does_not_decide_twice_for_one_local_cluster(
    scenario,
    tmp_path: Path,
) -> None:
    first_three = sorted(
        item.delivered_at_s
        for item in scenario.observations.delivery.envelopes
        if item.delivered_at_s >= 0
    )[:3]
    runtime, _event_log = _mission_runtime(scenario, tmp_path)
    result = runtime.run(through_s=first_three[-1])

    keys = tuple(
        (item.controller_authority_id, item.belief_cluster_id) for item in result.decisions
    )
    assert len(keys) == len(set(keys))


def test_reference_mission_runtime_validates_coordination_sources_before_events(
    scenario,
    tmp_path: Path,
) -> None:
    delivery = scenario.coordination.public.deliveries[0]
    tampered_delivery = delivery.model_copy(update={"source_content_digest": "0" * 64})
    public = scenario.coordination.public.model_copy(
        update={
            "deliveries": (tampered_delivery, *scenario.coordination.public.deliveries[1:])
        }
    )
    tampered = replace(
        scenario,
        coordination=scenario.coordination.model_copy(update={"public": public}),
    )
    with pytest.raises(ValueError, match="coordination source digest"):
        _mission_runtime(tampered, tmp_path)


def test_reference_mission_runtime_is_single_use(scenario, tmp_path: Path) -> None:
    runtime, _event_log = _mission_runtime(scenario, tmp_path)
    runtime.run(through_s=-172_800)
    with pytest.raises(RuntimeError, match="single-use"):
        runtime.run(through_s=-172_800)


def test_reference_mission_runtime_records_completed_and_censored_service_outcomes(
    scenario,
    tmp_path: Path,
) -> None:
    runtime, event_log = _mission_runtime(scenario, tmp_path)
    result = runtime.run()

    allocations = tuple(item for item in result.decisions if item.disposition == "allocated")
    assert allocations
    assert result.complete
    assert len(result.outcomes) == len(allocations)
    assert any(item.status == "active_at_scenario_censoring" for item in result.outcomes)
    assert all(
        (
            item.observed_completion_s == item.scheduled_completion_s
            if item.status == "completed_within_window"
            else item.observed_completion_s is None and item.scheduled_completion_s > 345_600
        )
        for item in result.outcomes
    )
    replay = event_log.replay()
    assert len(replay.public_mission_artifacts[ReferenceEventType.OUTCOME_RECORDED.value]) == len(
        result.outcomes
    )
