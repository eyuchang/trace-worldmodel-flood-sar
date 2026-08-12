from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from trace_jepa.experimental import RevalidationGuard
from trace_jepa.predictor import ToyActionPrefixPredictor
from trace_jepa.runtime import PolicyConfig, PolicyEngine, TraceRuntime
from trace_reference.decision import EvidenceAcquisitionExecutor
from trace_reference.generation import generate_reference_scenario
from trace_reference.reconciliation import ReferenceEvidenceGraph
from trace_reference.runtime import (
    ReferenceCommitmentLog,
    ReferenceDecisionEngine,
    ReferenceDecisionEngineDependencies,
    ReferenceDecisionInput,
    ReferenceEventLog,
    ReferenceEvidenceLedger,
    ReferenceRouteService,
    ReferenceScenarioIndex,
    ReferenceTraceGateway,
    ReferenceTraceRepository,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def scenario():
    return generate_reference_scenario(ROOT, seed=20260812)


def _runtime_components(root: Path, event_log: ReferenceEventLog):
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
            policy_version="trace-reference-decision-engine-test-v1",
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
    runtime = TraceRuntime(
        repository=repository,
        ledger=ledger,
        commitments=commitments,
        policy=policy,
    )
    return (
        predictor,
        policy,
        repository,
        ledger,
        commitments,
        ReferenceTraceGateway(runtime, event_log),
    )


def test_reference_decision_engine_closes_one_authenticated_public_report(
    scenario,
    tmp_path: Path,
) -> None:
    report = next(
        item
        for item in scenario.observations.raw.reports
        if 0 <= item.observed_at_s < 180_000
    )
    envelope = next(
        item for item in scenario.observations.delivery.envelopes if item.call_id == report.call_id
    )
    assert envelope.delivered_at_s <= 345_600
    graph = ReferenceEvidenceGraph(envelope.initial_authority_id)
    reconciliation = graph.process(report, delivered_at_s=envelope.delivered_at_s)
    event_log = ReferenceEventLog()
    predictor, policy, repository, ledger, commitments, gateway = _runtime_components(
        tmp_path, event_log
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
            trace_gateway=gateway,
            evidence_ledger=ledger,
            trace_repository=repository,
            commitment_log=commitments,
            acquisition_executor=EvidenceAcquisitionExecutor(),
            policy_version=policy.config.policy_version,
            environment_contract_version="trace-reference-python311-v1",
        )
    )
    execution = engine.execute(
        ReferenceDecisionInput(
            report=report,
            envelope=envelope,
            controller_authority_id=envelope.initial_authority_id,
            reconciliation=reconciliation,
            active_commitments=(),
            known_outcomes=(),
            at_s=envelope.delivered_at_s,
            created_at=(
                scenario.config.timeline.evaluation_start_iso8601
                + timedelta(seconds=envelope.delivered_at_s)
            ),
        )
    )

    assert execution.result.disposition in {
        "allocated",
        "refused",
        "acquisition-requested",
    }
    assert execution.result.manifest_digest == execution.manifest.manifest_digest
    assert execution.proposals.enumeration_receipt.complete_for_declared_grammar
    assert repository.verify_chain()
    assert commitments.verify_chain()
    assert ledger.verify_chain()
    assert event_log.verify()
    replay = event_log.replay()
    assert (
        execution.result.decision_id
        in replay.public_mission_artifacts["decision_manifest_recorded"]
    )
    serialized = execution.result.model_dump_json() + execution.manifest.model_dump_json()
    for forbidden in ("truth_incident", "truth_person", "candidate_audit", "hidden_lineage"):
        assert forbidden not in serialized


def test_reference_decision_engine_rejects_tampered_delivery_before_writes(
    scenario,
    tmp_path: Path,
) -> None:
    report = next(item for item in scenario.observations.raw.reports if item.observed_at_s >= 0)
    envelope = next(
        item for item in scenario.observations.delivery.envelopes if item.call_id == report.call_id
    )
    graph = ReferenceEvidenceGraph(envelope.initial_authority_id)
    reconciliation = graph.process(report, delivered_at_s=envelope.delivered_at_s)
    event_log = ReferenceEventLog()
    predictor, policy, repository, ledger, commitments, gateway = _runtime_components(
        tmp_path, event_log
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
            trace_gateway=gateway,
            evidence_ledger=ledger,
            trace_repository=repository,
            commitment_log=commitments,
            acquisition_executor=EvidenceAcquisitionExecutor(),
            policy_version=policy.config.policy_version,
            environment_contract_version="trace-reference-python311-v1",
        )
    )
    tampered = envelope.model_copy(update={"integrity_token": "0" * 64})
    with pytest.raises(ValueError, match="authentication failed"):
        engine.execute(
            ReferenceDecisionInput(
                report=report,
                envelope=tampered,
                controller_authority_id=envelope.initial_authority_id,
                reconciliation=reconciliation,
                active_commitments=(),
                known_outcomes=(),
                at_s=envelope.delivered_at_s,
                created_at=scenario.config.timeline.evaluation_start_iso8601,
            )
        )
    assert (
        repository.prefix_digest == ledger.prefix_digest == commitments.prefix_digest == ("GENESIS")
    )
    assert not event_log.events
