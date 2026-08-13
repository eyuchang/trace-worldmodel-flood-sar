from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from trace_jepa.experimental import RevalidationGuard
from trace_jepa.predictor import ToyActionPrefixPredictor
from trace_jepa.runtime import PolicyConfig, PolicyEngine, TraceRuntime
from trace_reference import load_reference_fault_schedule
from trace_reference.decision import AcquisitionRequestReceipt, EvidenceAcquisitionExecutor
from trace_reference.domain import (
    ReferenceDecisionHandoffArtifact,
    ReferenceEvent,
    ReferenceEventType,
    ReferenceFaultSchedule,
    ReferenceMissionRestartCheckpoint,
)
from trace_reference.generation import generate_reference_scenario
from trace_reference.runtime import (
    ReferenceCommitmentLog,
    ReferenceDecisionEngine,
    ReferenceDecisionEngineDependencies,
    ReferenceEventLog,
    ReferenceEvidenceLedger,
    ReferenceMissionRuntime,
    ReferenceRouteProviderInput,
    ReferenceRouteService,
    ReferenceScenarioIndex,
    ReferenceTraceGateway,
    ReferenceTraceRepository,
    build_reference_route_provider_receipt,
)
from trace_reference.runtime.fault_overlay import build_reference_coordination_overlay
from trace_reference.runtime.report_fault_overlay import build_reference_report_fault_overlay

ROOT = Path(__file__).resolve().parents[3]
FAULT_SCHEDULE = Path("data/scenario/delta/reference_protocol/reference_fault_schedule_v1.json")


@pytest.fixture(scope="module")
def scenario():
    return generate_reference_scenario(ROOT, seed=20260812)


@pytest.fixture(scope="module")
def fault_schedule() -> ReferenceFaultSchedule:
    return load_reference_fault_schedule(ROOT, FAULT_SCHEDULE)


def _mission_runtime(
    scenario,
    root: Path,
    *,
    events: tuple[ReferenceEvent, ...] = (),
    fault_schedule: ReferenceFaultSchedule | None = None,
    restart_checkpoint: ReferenceMissionRestartCheckpoint | None = None,
) -> tuple[ReferenceMissionRuntime, ReferenceEventLog]:
    event_log = ReferenceEventLog(events)
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
    return ReferenceMissionRuntime(
        scenario,
        engine,
        fault_schedule=fault_schedule,
        restart_checkpoint=restart_checkpoint,
    ), event_log


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
    assert replay.public_mission_artifacts[ReferenceEventType.COORDINATION_MESSAGE_DELIVERED.value]
    delivered_activation_ids = event_log.public_artifact_ids(
        ReferenceEventType.RESOURCE_ACTIVATION_UPDATED
    )
    assert delivered_activation_ids == frozenset(
        item.event_id
        for item in scenario.coordination.activations.events
        if item.delivered_at_s <= first
    )
    assert replay.public_mission_artifacts[ReferenceEventType.RESOURCE_ACTIVATION_UPDATED.value]
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
        update={"deliveries": (tampered_delivery, *scenario.coordination.public.deliveries[1:])}
    )
    tampered = replace(
        scenario,
        coordination=scenario.coordination.model_copy(update={"public": public}),
    )
    with pytest.raises(ValueError, match="coordination source digest"):
        _mission_runtime(tampered, tmp_path)


def test_reference_mission_runtime_binds_activation_schedule_to_resource_roster(
    scenario,
    tmp_path: Path,
) -> None:
    activations = scenario.coordination.activations.model_copy(
        update={"resource_catalog_digest": "0" * 64}
    )
    coordination = scenario.coordination.model_copy(update={"activations": activations})
    tampered = replace(scenario, coordination=coordination)

    with pytest.raises(ValueError, match="another resource catalog"):
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
    acquisition_decisions = tuple(
        item for item in result.decisions if item.disposition == "acquisition-requested"
    )
    reassessments = tuple(
        item for item in result.decisions if item.reassessment_of_decision_id is not None
    )
    assert acquisition_decisions
    assert len(reassessments) == len(acquisition_decisions)
    assert all(item.disposition != "acquisition-requested" for item in reassessments)
    assert {item.reassessment_of_decision_id for item in reassessments} == {
        item.decision_id for item in acquisition_decisions
    }
    assert any(item.status == "active_at_scenario_censoring" for item in result.outcomes)
    assert all(item.status != "partial_service_within_window" for item in result.outcomes)
    assert all(
        item.observed_completion_s == item.scheduled_completion_s
        if item.status == "completed_within_window"
        else item.observed_completion_s is None
        for item in result.outcomes
    )
    replay = event_log.replay()
    assert len(replay.public_mission_artifacts[ReferenceEventType.OUTCOME_RECORDED.value]) == len(
        result.outcomes
    )
    assert len(
        replay.public_mission_artifacts[ReferenceEventType.PROVIDER_RECEIPT_RECORDED.value]
    ) == len(acquisition_decisions)
    assert len(
        replay.public_mission_artifacts[ReferenceEventType.ACQUISITION_OUTCOME_RECORDED.value]
    ) == len(acquisition_decisions)
    assert len(
        replay.public_mission_artifacts[ReferenceEventType.PHYSICAL_EVIDENCE_RECORDED.value]
    ) == len(acquisition_decisions)
    decision_artifacts = replay.public_mission_artifacts[
        ReferenceEventType.DECISION_MANIFEST_RECORDED.value
    ]
    for reassessment in reassessments:
        artifact = json.loads(decision_artifacts[reassessment.decision_id])
        handoff = ReferenceDecisionHandoffArtifact.model_validate(artifact)
        assert artifact["manifest"]["acquisition_outcome_digest"] is not None
        assert artifact["decision"]["reassessment_of_decision_id"] is not None
        assert handoff.manifest.cost_delta_digest == handoff.cost_delta.cost_delta_digest
        assert handoff.catalog.catalog_digest == handoff.selection.catalog_digest
        assert (
            handoff.public_snapshot.snapshot_digest
            == handoff.eligibility.public_snapshot_digest
        )
    public_json = json.dumps(replay.public_mission_artifacts, sort_keys=True)
    for forbidden in ("truth_incident_id", "truth_person_id", "candidate_digest"):
        assert forbidden not in public_json
    request_json = next(
        iter(
            replay.public_mission_artifacts[ReferenceEventType.ACQUISITION_REQUESTED.value].values()
        )
    )
    request = AcquisitionRequestReceipt.model_validate_json(request_json)
    tampered = request.model_copy(update={"route_catalog_digest": "0" * 64})
    report = next(
        item for item in scenario.observations.raw.reports if item.call_id == request.target_call_id
    )
    with pytest.raises(ValueError, match="request digest"):
        build_reference_route_provider_receipt(
            ReferenceRouteProviderInput(
                request=tampered,
                report=report,
                route_service=runtime.engine.dependencies.route_service,
                resources=scenario.resources,
            )
        )


def test_registered_delivery_faults_are_reachable_and_preserve_exogenous_inputs(
    scenario,
    fault_schedule: ReferenceFaultSchedule,
    tmp_path: Path,
) -> None:
    original_digests = (
        scenario.physical.physical_digest,
        scenario.exposure.exposure_digest,
        scenario.truth.truth_digest,
        scenario.observations.raw.raw_reports_digest,
        scenario.resources.hidden.hidden_resource_digest,
    )
    overlay = build_reference_coordination_overlay(scenario, fault_schedule)
    assert overlay.unreachable_fault_ids == ()
    selected = dict(overlay.selected_targets)
    assert len(selected) == 3

    reordered = next(item for item in overlay.attempts if item.behavior == "reordered-delivery")
    original = next(
        item
        for item in scenario.coordination.public.deliveries
        if item.delivery_id == reordered.delivery.delivery_id
    )
    assert reordered.at_s == original.delivered_at_s + 900
    assert any(
        original.delivered_at_s < item.delivered_at_s < reordered.at_s
        for item in scenario.coordination.public.deliveries
    )

    runtime, event_log = _mission_runtime(
        scenario,
        tmp_path,
        fault_schedule=fault_schedule,
    )
    report_overlay = build_reference_report_fault_overlay(scenario, fault_schedule)
    assert report_overlay.coordination.unreachable_fault_ids == ()
    assert len(report_overlay.reports) == 2
    through_s = max(200_000, *(item.envelope.delivered_at_s for item in report_overlay.reports))
    result = runtime.run(through_s=through_s)
    applications = {item.family: item for item in result.fault_applications}
    assert {
        "authenticated-false-report",
        "reordered-evidence-delivery",
        "duplicated-delivery-retry",
        "identity-dispute-visible-revision",
        "stale-acknowledgement-key-rotation",
    } <= set(applications)
    assert applications["duplicated-delivery-retry"].disposition == ("duplicate-effect-suppressed")
    assert applications["stale-acknowledgement-key-rotation"].disposition == ("stale-key-rejected")
    replay = event_log.replay()
    assert ReferenceEventType.FAULT_APPLIED.value not in replay.public_mission_artifacts
    fault_events = [
        item for item in event_log.events if item.event_type == ReferenceEventType.FAULT_APPLIED
    ]
    assert fault_events
    assert all(item.visibility.value == "hidden_evaluation_only" for item in fault_events)
    public_json = json.dumps(replay.public_mission_artifacts, sort_keys=True)
    assert "authenticated-false-report" not in public_json
    assert "identity-dispute-visible-revision" not in public_json
    delivered = replay.public_mission_artifacts[
        ReferenceEventType.COORDINATION_MESSAGE_DELIVERED.value
    ]
    assert selected["reference-fault-duplicated-delivery-retry-v1"] in delivered
    assert selected["reference-fault-stale-key-acknowledgement-v1"] not in delivered
    injected = {item.fault_id: item for item in report_overlay.reports}
    false_report = injected["reference-fault-authenticated-false-report-v1"].report
    revision = injected["reference-fault-identity-dispute-revision-v1"].report
    assert false_report.call_id not in {item.call_id for item in scenario.observations.raw.reports}
    assert "source-unverified" in false_report.descriptor_tokens
    assert revision.revision_of_call_id is not None
    revised = next(
        item
        for item in scenario.observations.raw.reports
        if item.call_id == revision.revision_of_call_id
    )
    assert revision.callback_token == revised.callback_token
    revision_steps = [
        json.loads(value)
        for value in replay.public_mission_artifacts[
            ReferenceEventType.RECONCILIATION_UPDATED.value
        ].values()
        if json.loads(value)["call_id"] == revision.call_id
    ]
    assert len(revision_steps) == 1
    assert revision_steps[0]["relationship_status"] == "confirmed"
    assert revision_steps[0]["visible_evidence_basis"] == ["explicit_visible_revision_pointer"]
    assert original_digests == (
        scenario.physical.physical_digest,
        scenario.exposure.exposure_digest,
        scenario.truth.truth_digest,
        scenario.observations.raw.raw_reports_digest,
        scenario.resources.hidden.hidden_resource_digest,
    )


def _assert_outcome_fault_closure(result, runtime, replay) -> None:
    partial_application = next(
        item for item in result.fault_applications if item.family == "partial-service-outcome"
    )
    partial_outcomes = tuple(
        item for item in result.outcomes if item.status == "partial_service_within_window"
    )
    assert len(partial_outcomes) == 1
    assert partial_outcomes[0].commitment_id == partial_application.target_public_id
    assert partial_outcomes[0].realized_service_fraction_micros == 500_000
    assert len(partial_outcomes[0].affected_public_subject_ids) == 1
    assert partial_outcomes[0].affected_public_subject_ids[0].startswith("RBC-")
    censor_application = next(
        item
        for item in result.fault_applications
        if item.family == "completion-after-scenario-censoring"
    )
    censored_outcome = next(
        item
        for item in result.outcomes
        if item.commitment_id == censor_application.target_public_id
    )
    assert censored_outcome.status == "active_at_scenario_censoring"
    assert censored_outcome.scheduled_completion_s > 345_600
    assert censored_outcome.observed_completion_s is None
    assert len(result.contradictions) == 1
    assert len(result.compensations) == 1
    assert len(result.consistency_debts) == 1
    contradiction = result.contradictions[0]
    compensation = result.compensations[0]
    debt = result.consistency_debts[0]
    assert compensation.invalidated_commitment_id == contradiction.commitment_id
    assert compensation.status == "failed"
    assert debt.invalidated_commitment_id == contradiction.commitment_id
    assert debt.failed_compensation_id == compensation.compensation_id
    assert debt.status == "unresolved-escalated"
    assert debt.escalation_target == "AUTH-01"
    revised_record = runtime.engine.dependencies.trace_repository.get(
        contradiction.authorizing_trace_record_id
    )
    assert revised_record.record_version == contradiction.authorizing_trace_record_version + 1
    assert revised_record.final_status.value == "revise"
    assert "realized_contradiction" in revised_record.failed_gates
    revised_evidence = runtime.engine.dependencies.evidence_ledger.get(
        revised_record.evidence_refs[-1]
    )
    assert revised_evidence.decisively_contradicted
    assert revised_evidence.realized_outcome == contradiction.model_dump(mode="json")
    assert {
        item.family: item.target_public_id
        for item in result.fault_applications
        if item.family in {"contradictory-outcome-evidence", "failed-compensation"}
    } == {
        "contradictory-outcome-evidence": contradiction.commitment_id,
        "failed-compensation": compensation.compensation_id,
    }
    assert (
        len(replay.public_mission_artifacts[ReferenceEventType.OUTCOME_EVIDENCE_RECORDED.value])
        == 1
    )
    assert len(replay.public_mission_artifacts[ReferenceEventType.COMPENSATION_RECORDED.value]) == 1
    assert (
        len(replay.public_mission_artifacts[ReferenceEventType.CONSISTENCY_DEBT_RECORDED.value])
        == 1
    )
    public_json = json.dumps(replay.public_mission_artifacts, sort_keys=True)
    assert "contradictory-outcome-evidence" not in public_json
    assert "failed-compensation" not in public_json


def test_silent_provider_success_reconciles_after_client_timeout(
    scenario,
    fault_schedule: ReferenceFaultSchedule,
    tmp_path: Path,
) -> None:
    uninterrupted_root = tmp_path / "uninterrupted"
    uninterrupted_root.mkdir()
    runtime, event_log = _mission_runtime(
        scenario,
        uninterrupted_root,
        fault_schedule=fault_schedule,
    )
    result = runtime.run()
    application = next(
        item
        for item in result.fault_applications
        if item.family == "silent-provider-success-after-timeout"
    )
    replay = event_log.replay()
    _assert_outcome_fault_closure(result, runtime, replay)
    outcomes = [
        json.loads(value)
        for value in replay.public_mission_artifacts[
            ReferenceEventType.ACQUISITION_OUTCOME_RECORDED.value
        ].values()
    ]
    targeted = [item for item in outcomes if item["request_id"] == application.target_public_id]
    assert [item["outcome_status"] for item in targeted] == [
        "provider-timeout",
        "evidence-accepted",
    ]
    assert (
        len(
            [
                item
                for item in result.decisions
                if item.reassessment_of_decision_id is not None
                and item.acquisition_request_id is None
            ]
        )
        >= 1
    )
    assert runtime.engine.dependencies.trace_repository.verify_chain()
    assert runtime.engine.dependencies.evidence_ledger.verify_chain()

    request = next(
        AcquisitionRequestReceipt.model_validate_json(value)
        for value in replay.public_mission_artifacts[
            ReferenceEventType.ACQUISITION_REQUESTED.value
        ].values()
        if json.loads(value)["request_id"] == application.target_public_id
    )
    restarted_root = tmp_path / "restarted"
    restarted_root.mkdir()
    before_restart, prefix_log = _mission_runtime(
        scenario,
        restarted_root,
        fault_schedule=fault_schedule,
    )
    before_restart.run(through_s=request.expected_delivery_s)
    checkpoint = before_restart.checkpoint()
    recovered, recovered_log = _mission_runtime(
        scenario,
        restarted_root,
        events=prefix_log.events,
        fault_schedule=fault_schedule,
        restart_checkpoint=checkpoint,
    )
    recovered_result = recovered.run()

    assert recovered_result == result
    assert recovered_log.events == event_log.events
    for relative_name in (
        "trace_records.jsonl",
        "commitments.jsonl",
        "evidence_index.jsonl",
    ):
        assert (restarted_root / relative_name).read_bytes() == (
            uninterrupted_root / relative_name
        ).read_bytes()


def test_reference_mission_restart_matches_uninterrupted_continuation(
    scenario,
    fault_schedule: ReferenceFaultSchedule,
    tmp_path: Path,
) -> None:
    uninterrupted_root = tmp_path / "uninterrupted"
    uninterrupted_root.mkdir()
    uninterrupted, uninterrupted_log = _mission_runtime(scenario, uninterrupted_root)
    expected = uninterrupted.run()

    restarted_root = tmp_path / "restarted"
    restarted_root.mkdir()
    before_crash, prefix_log = _mission_runtime(scenario, restarted_root)
    before_crash.run(through_s=180_000)
    checkpoint = before_crash.checkpoint()
    tampered_checkpoint = checkpoint.model_copy(update={"event_prefix_digest": "0" * 64})
    with pytest.raises(ValueError, match="checkpoint digest"):
        _mission_runtime(
            scenario,
            restarted_root,
            events=prefix_log.events,
            restart_checkpoint=tampered_checkpoint,
        )
    with pytest.raises(ValueError, match="runtime profile"):
        _mission_runtime(
            scenario,
            restarted_root,
            events=prefix_log.events,
            fault_schedule=fault_schedule,
            restart_checkpoint=checkpoint,
        )
    recovered, recovered_log = _mission_runtime(
        scenario,
        restarted_root,
        events=prefix_log.events,
        restart_checkpoint=checkpoint,
    )
    actual = recovered.run()

    assert actual == expected
    assert recovered_log.events == uninterrupted_log.events
    for relative_name in (
        "trace_records.jsonl",
        "commitments.jsonl",
        "evidence_index.jsonl",
    ):
        assert (restarted_root / relative_name).read_bytes() == (
            uninterrupted_root / relative_name
        ).read_bytes()
    expected_evidence = sorted((uninterrupted_root / "evidence").glob("*.json"))
    actual_evidence = sorted((restarted_root / "evidence").glob("*.json"))
    assert [item.name for item in actual_evidence] == [item.name for item in expected_evidence]
    assert [item.read_bytes() for item in actual_evidence] == [
        item.read_bytes() for item in expected_evidence
    ]


def test_registered_crash_restart_matches_faulted_continuation(
    scenario,
    fault_schedule: ReferenceFaultSchedule,
    tmp_path: Path,
) -> None:
    uninterrupted_root = tmp_path / "uninterrupted-faulted"
    uninterrupted_root.mkdir()
    uninterrupted, _uninterrupted_log = _mission_runtime(
        scenario,
        uninterrupted_root,
        fault_schedule=fault_schedule,
    )
    expected = uninterrupted.run()

    restarted_root = tmp_path / "restarted-faulted"
    restarted_root.mkdir()
    before_crash, prefix_log = _mission_runtime(
        scenario,
        restarted_root,
        fault_schedule=fault_schedule,
    )
    before_crash.run(through_s=187_200)
    checkpoint = before_crash.checkpoint(register_crash=True)
    recovered, recovered_log = _mission_runtime(
        scenario,
        restarted_root,
        events=prefix_log.events,
        fault_schedule=fault_schedule,
        restart_checkpoint=checkpoint,
    )
    actual = recovered.run()

    crash = next(
        item for item in actual.fault_applications if item.family == "controller-crash-restart"
    )
    assert crash.applied_at_s == 187_200
    without_crash = tuple(
        item for item in actual.fault_applications if item.family != "controller-crash-restart"
    )
    assert without_crash == expected.fault_applications
    assert actual.decisions == expected.decisions
    assert actual.outcomes == expected.outcomes
    assert actual.contradictions == expected.contradictions
    assert actual.compensations == expected.compensations
    assert actual.consistency_debts == expected.consistency_debts
    for relative_name in (
        "trace_records.jsonl",
        "commitments.jsonl",
        "evidence_index.jsonl",
    ):
        assert (restarted_root / relative_name).read_bytes() == (
            uninterrupted_root / relative_name
        ).read_bytes()
    assert recovered_log.verify()
