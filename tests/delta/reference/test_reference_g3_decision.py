from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from trace_jepa.contracts import (
    ActionInstance,
    Claim,
    ClaimLayer,
    CommitmentDecision,
    PlanCandidate,
    WorldModelEvidence,
)
from trace_jepa.experimental import RevalidationGuard, build_experimental_profile
from trace_jepa.predictor import (
    PredictorContext,
    PredictorObservation,
    PredictorPriorProfile,
    PredictorRequest,
    PredictorRouteObservation,
    ToyActionPrefixPredictor,
)
from trace_jepa.runtime import PolicyConfig, PolicyEngine, TraceRuntime
from trace_jepa.support import canonical_json_bytes, sha256_bytes
from trace_reference import load_reference_resource_parameters
from trace_reference.decision.acquisition import (
    EvidenceAcquisitionExecutor,
    ProviderReceiptInput,
    sign_provider_receipt,
)
from trace_reference.decision.artifacts import (
    CommitmentEnvelopeInput,
    ServiceOutcomeInput,
    build_commitment_envelope,
    build_service_outcome,
)
from trace_reference.decision.canonical import decision_digest
from trace_reference.decision.costs import (
    CostDeltaInput,
    DecisionCostLedger,
    build_cost_delta,
)
from trace_reference.decision.counterfactual import ReferencePublicCounterfactualModel
from trace_reference.decision.domain import (
    BaseSelectionRequest,
    CounterfactualStepRequest,
    ProposalRequest,
    ProposalSet,
    PublicEnvironmentBelief,
    ReferenceTraceAssessment,
)
from trace_reference.decision.eligibility import (
    build_response_bundle_catalog,
    classify_reference_proposals,
)
from trace_reference.decision.evidence_binding import (
    PredictorEvidenceBinding,
    bind_predictor_evidence,
)
from trace_reference.decision.proposals import propose_reference_actions
from trace_reference.decision.selector import BaseReferenceSelector
from trace_reference.decision.visibility import (
    SnapshotInput,
    build_controller_visible_snapshot,
)
from trace_reference.domain.coordination import (
    ReferenceCoordinationDelivery,
    ReferencePublicCoordinationScenario,
)
from trace_reference.domain.resources import (
    ReferencePublicResourceTelemetryScenario,
    ReferenceResourceClass,
    ReferenceResourceState,
    ReferenceResourceTelemetry,
)
from trace_reference.generation import generate_reference_resources
from trace_reference.runtime import (
    ProposalAssessmentInput,
    ReferenceCommitmentLog,
    ReferenceEventLog,
    ReferenceEvidenceLedger,
    ReferenceTraceGateway,
    ReferenceTraceRepository,
    SelectedCommitmentInput,
)

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def decision_fixture():
    parameters = load_reference_resource_parameters(
        ROOT,
        Path("data/scenario/delta/reference/resources/reference_resource_parameters_v1.yaml"),
    )
    resources = generate_reference_resources(parameters, seed=20260812, kappa=1.0)
    selected = []
    for resource_class in (
        ReferenceResourceClass.RESCUE_BOAT,
        ReferenceResourceClass.TYPE_I_ENGINE,
        ReferenceResourceClass.SMALL_UAS,
    ):
        selected.append(
            next(
                item for item in resources.hidden.resources if item.resource_class == resource_class
            )
        )
    telemetry = tuple(
        ReferenceResourceTelemetry(
            telemetry_id=f"RT-{index:016x}",
            resource_id=item.resource_id,
            observed_at_s=900,
            delivered_at_s=900,
            owning_authority_id=item.owning_authority_id,
            reported_state=ReferenceResourceState.AVAILABLE_STAGED,
            reported_crew_fatigue_band="low",
            reported_fuel_or_charge_band="full",
        )
        for index, item in enumerate(selected, start=1)
    )
    public_telemetry = ReferencePublicResourceTelemetryScenario(
        scenario_id="WF-DFLD-01-REFERENCE",
        schema_version="delta-reference-resource-telemetry-v1",
        seed=20260812,
        iota_micros=700_000,
        telemetry=telemetry,
        telemetry_digest="1" * 64,
    )
    deliveries = tuple(
        ReferenceCoordinationDelivery(
            delivery_id=f"CD-{index:016x}",
            evidence_kind="resource-telemetry",
            evidence_id=item.telemetry_id,
            source_authority_id=item.owning_authority_id,
            recipient_authority_id="AUTH-01",
            recipient_partition_id="AUTH-01-P01",
            source_available_at_s=900,
            delivered_at_s=900,
            source_content_digest="2" * 64,
        )
        for index, item in enumerate(telemetry, start=1)
    )
    coordination = ReferencePublicCoordinationScenario(
        scenario_id="WF-DFLD-01-REFERENCE",
        schema_version="delta-reference-coordination-v1",
        seed=20260812,
        phi=4,
        authority_registry_version="delta-reference-governance-v1",
        deliveries=deliveries,
        public_coordination_digest="3" * 64,
    )
    snapshot = build_controller_visible_snapshot(
        SnapshotInput(
            mission_id="reference-mission-development",
            decision_id="reference-decision-001",
            controller_authority_id="AUTH-01",
            at_s=1_000,
            evidence_prefix_digest="4" * 64,
            trace_prefix_digest="GENESIS",
            commitment_prefix_digest="GENESIS",
            environment_beliefs=(
                PublicEnvironmentBelief(
                    belief_id="belief-crossing-xng-04",
                    kind="crossing",
                    entity_id="XNG-04",
                    value="open",
                    observed_at_s=900,
                    evidence_id="environment-evidence-001",
                ),
            ),
            active_commitments=(),
            known_outcomes=(),
            prior_profile_id="reference-prior-pi-0p7-v1",
            policy_version="trace-reference-v1",
            environment_contract_version="trace-reference-python311-v1",
        ),
        public_telemetry,
        tuple(selected),
        coordination,
        ToyActionPrefixPredictor().provenance(),
    )
    request = ProposalRequest(
        schema_version="delta-reference-proposal-request-v1",
        decision_id=snapshot.decision_id,
        public_snapshot_digest=snapshot.snapshot_digest,
        target_public_incident_id="public-belief-cluster-001",
        public_taxonomy="C-STR",
        decision_deadline_s=3_600,
        policy_version=snapshot.policy_version,
        proposal_namespace="reference-public-proposal-grammar-v1",
    )
    proposals = propose_reference_actions(request, snapshot)
    return snapshot, request, proposals


def _assessment(proposal_digest: str, decision: CommitmentDecision) -> ReferenceTraceAssessment:
    body = {
        "proposal_digest": proposal_digest,
        "commitment_decision": decision.value,
        "trace_record_id": f"trace-{proposal_digest[:20]}",
        "trace_record_version": 2,
        "evidence_digest": decision_digest({"proposal": proposal_digest, "evidence": "public"}),
        "failed_gates": () if decision == CommitmentDecision.CLEAR else ("freshness",),
        "missing_items": () if decision == CommitmentDecision.CLEAR else ("fresh evidence",),
        "authorization_sufficient_for_action": decision == CommitmentDecision.CLEAR,
    }
    return ReferenceTraceAssessment(**body, assessment_digest=decision_digest(body))


def _catalog(decision_fixture, *, hold_primary: bool = False):
    snapshot, _, proposals = decision_fixture
    assessments = {
        item.proposal_digest: _assessment(
            item.proposal_digest,
            CommitmentDecision.HOLD if hold_primary else CommitmentDecision.CLEAR,
        )
        for item in proposals.physical_actions
    }
    assessments.update(
        {
            item.proposal_digest: _assessment(item.proposal_digest, CommitmentDecision.CLEAR)
            for item in proposals.safe_alternatives
        }
    )
    eligibility = classify_reference_proposals(snapshot, proposals, assessments)
    return proposals, eligibility, build_response_bundle_catalog(snapshot, proposals, eligibility)


def _core_action_for_test(proposal) -> ActionInstance:
    action = proposal.action
    return ActionInstance(
        action_id=action.action_id,
        action_type=action.action_class,
        actor_id=action.actor_resource_id or "reference-unassigned-resource",
        origin=action.origin_node_id,
        destination=action.destination_public_id,
        route_id=action.route_id,
        parameters={
            "required_capability": action.required_capability,
            "reference_action_digest": action.action_digest,
            "actor_crew_id": action.actor_crew_id,
        },
    )


def _bound_proposals(decision_fixture, *, observation_age_s: float = 60.0):
    _, _, proposals = decision_fixture
    predictor = ToyActionPrefixPredictor()
    requests = {}
    evidences = {}
    bindings = {}
    created_at = datetime(2026, 1, 17, 4, 16, 40, tzinfo=UTC)
    for proposal in (*proposals.physical_actions, *proposals.safe_alternatives):
        action = _core_action_for_test(proposal)
        plan = PlanCandidate(
            plan_id=f"plan-{proposal.action.action_digest[:20]}",
            name="Reference G3 closure fixture",
            actions=(action,),
            utility=1.0,
            reversible_first_action=proposal.reversible,
            requires_authority=True,
        )
        request = PredictorRequest(
            plan=plan,
            observation=PredictorObservation(
                routes=[
                    PredictorRouteObservation(
                        route_id="reference-public-route-v1",
                        report="open",
                        nominal_travel_s=900,
                        confidence=0.95,
                        observation_age_s=observation_age_s,
                        crossing_sample_time_s=900,
                    )
                ],
                context=PredictorContext(
                    simulation_time_s=1_000,
                    available_resource_units=2,
                    call_observation_age_s=observation_age_s,
                    coordination_latency_s=100,
                    prior_profile=PredictorPriorProfile(
                        profile_id="reference-prior-pi-0p7-v1",
                        calibration_version=predictor.calibration_version,
                        prior_accuracy_milli=700,
                    ),
                ),
            ),
        )
        prediction = predictor.predict(request)
        provenance = predictor.provenance()
        request_digest = sha256_bytes(canonical_json_bytes(request.model_dump(mode="json")))
        profile = build_experimental_profile(
            predictor_version=provenance.predictor_version,
            calibration_version=provenance.calibration_version,
            claim_family=action.action_type,
            adequacy_status=provenance.adequacy_status,
            prediction_timestamp=created_at,
            model_hash=provenance.model_hash,
            calibration_hash=provenance.calibration_hash,
        ).model_copy(update={"profile_id": f"profile-{proposal.action.action_digest[:20]}"})
        evidence = WorldModelEvidence(
            evidence_id=f"reference-evidence-{proposal.action.action_digest[:20]}",
            rollout_id=f"reference-rollout-{proposal.action.action_digest[:20]}",
            encoder_version="reference-symbolic-observation-v1",
            fusion_version="reference-controller-context-v1",
            predictor_version=provenance.predictor_version,
            semantic_probe_versions=("reference-route-resource-probe-v1",),
            training_snapshot=provenance.training_snapshot,
            observation_window_hash=request_digest,
            fleet_state_hash="5" * 64,
            candidate_plan_id=plan.plan_id,
            action_schema_version=provenance.action_schema_version,
            rollout_horizon=prediction.rollout_horizon,
            predicted_claims=("registered route and compatible capacity support response",),
            uncertainty=prediction.uncertainty,
            model_support=prediction.model_support,
            out_of_distribution_score=prediction.out_of_distribution_score,
            rollout_consistency=1.0 - prediction.uncertainty,
            reachability_evidence={"route_status": "open", "sample_time_s": 900},
            calibration_version=provenance.calibration_version,
            assumptions=prediction.assumptions,
            observation_age_s=observation_age_s,
            created_at=created_at,
            experimental_profile=profile,
        )
        evidence_digest = sha256_bytes(canonical_json_bytes(evidence.model_dump(mode="json")))
        bindings[proposal.action.action_digest] = PredictorEvidenceBinding(
            action_digest=proposal.action.action_digest,
            predictor_request_digest=request_digest,
            predictor_evidence_digest=evidence_digest,
        )
        requests[proposal.action.action_digest] = request
        evidences[proposal.action.action_digest] = evidence
    return bind_predictor_evidence(proposals, bindings), requests, evidences


def _trace_gateway(tmp_path: Path) -> ReferenceTraceGateway:
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
            policy_version="trace-reference-g3-fixture-v1",
            min_model_support=0.60,
            max_ood_score=0.35,
            max_uncertainty=0.30,
            max_rollout_horizon=8,
            max_observation_age_s=120,
            require_authority_for=provenance.supported_action_types,
            enable_revalidation_guard=True,
            high_consequence_actions=provenance.supported_action_types,
        ),
        revalidation=guard,
    )
    runtime = TraceRuntime(
        repository=ReferenceTraceRepository(tmp_path),
        ledger=ReferenceEvidenceLedger(tmp_path),
        commitments=ReferenceCommitmentLog(tmp_path),
        policy=policy,
    )
    return ReferenceTraceGateway(runtime, ReferenceEventLog())


def test_g3_public_snapshot_is_allowlisted_deterministic_and_hidden_free(
    decision_fixture,
) -> None:
    snapshot, request, proposals = decision_fixture
    assert snapshot.decision_extension_id is None
    serialized = snapshot.model_dump_json()
    for forbidden in (
        "truth_incident",
        "truth_person",
        "candidate_audit",
        "future_event",
        "hidden",
        "callback_token",
    ):
        assert forbidden not in serialized
    assert (
        proposals.model_dump_json()
        == propose_reference_actions(request, snapshot).model_dump_json()
    )


def test_g3_catalog_contains_only_preclassified_eligible_roots(decision_fixture) -> None:
    proposals, eligibility, catalog = _catalog(decision_fixture)
    assert catalog.complete_for_declared_grammar
    assert len(catalog.bundles) == sum(item.eligible for item in eligibility.classifications)
    assert {item.proposal_digest for item in catalog.bundles} == {
        item.proposal_digest for item in eligibility.classifications if item.eligible
    }
    assert all(item.fallback_disposition != CommitmentDecision.CLEAR for item in catalog.bundles)
    assert proposals.enumeration_receipt.generated_count == (
        len(proposals.physical_actions)
        + len(proposals.acquisition_offers)
        + len(proposals.safe_alternatives)
    )


def test_g3_hold_cannot_become_act_now_but_safe_alternative_is_independent(
    decision_fixture,
) -> None:
    proposals, _, catalog = _catalog(decision_fixture, hold_primary=True)
    primary_digests = {item.proposal_digest for item in proposals.physical_actions}
    assert not primary_digests & {item.proposal_digest for item in catalog.bundles}
    assert {item.proposal_digest for item in proposals.safe_alternatives} <= {
        item.proposal_digest for item in catalog.bundles
    }


@pytest.mark.parametrize(
    ("change", "expected_gate"),
    [
        ({"clear_probability_micros": 100_000}, "preposterior-adequacy"),
        ({"expected_latency_s": 3_000}, "deadline-feasibility"),
        ({"value_of_information_microunits": 120_000}, "positive-net-value"),
        ({"provider_available": False}, "provider-availability"),
        ({"authority_present": False}, "authority"),
        ({"minimum_interval_clear": False}, "minimum-interval"),
        ({"no_pending_request": False}, "pending-request"),
    ],
)
def test_g3_inadequate_acquisition_never_enters_catalog(
    decision_fixture, change, expected_gate
) -> None:
    snapshot, _, proposals = decision_fixture
    offer_body = proposals.acquisition_offers[0].model_dump(
        mode="json", exclude={"proposal_digest"}
    )
    offer_body.update(change)
    changed_offer = proposals.acquisition_offers[0].model_validate(
        {**offer_body, "proposal_digest": decision_digest(offer_body)}
    )
    set_body = proposals.model_dump(mode="json", exclude={"proposal_set_digest"})
    set_body["acquisition_offers"] = [changed_offer.model_dump(mode="json")]
    changed_set = ProposalSet(**set_body, proposal_set_digest=decision_digest(set_body))
    assessments = {
        item.proposal_digest: _assessment(item.proposal_digest, CommitmentDecision.CLEAR)
        for item in (*changed_set.physical_actions, *changed_set.safe_alternatives)
    }
    eligibility = classify_reference_proposals(snapshot, changed_set, assessments)
    classification = next(
        item
        for item in eligibility.classifications
        if item.proposal_id == changed_offer.proposal_id
    )
    assert not classification.eligible
    assert expected_gate in classification.failed_gates
    catalog = build_response_bundle_catalog(snapshot, changed_set, eligibility)
    assert changed_offer.proposal_digest not in {item.proposal_digest for item in catalog.bundles}


def test_g3_base_selector_cannot_change_catalog_membership(decision_fixture) -> None:
    snapshot, _, _ = decision_fixture
    _, _, catalog = _catalog(decision_fixture)
    before = catalog.model_dump_json()
    request = BaseSelectionRequest(
        catalog_digest=catalog.catalog_digest,
        public_snapshot_digest=snapshot.snapshot_digest,
        trace_prefix_digest=snapshot.trace_prefix_digest,
        at_s=snapshot.at_s,
    )
    receipt = BaseReferenceSelector().select(request, catalog)
    assert receipt.selected_bundle_id in {item.bundle_id for item in catalog.bundles}
    assert catalog.model_dump_json() == before


def test_g3_counterfactual_is_bounded_pure_and_not_world_evidence(decision_fixture) -> None:
    snapshot, _, _ = decision_fixture
    _, _, catalog = _catalog(decision_fixture)
    bundle = catalog.bundles[0]
    model = ReferencePublicCounterfactualModel()
    state = model.fork(snapshot)
    snapshot_before = snapshot.model_dump_json()
    result = model.step(
        CounterfactualStepRequest(
            state_digest=state.state_digest,
            bundle_digest=bundle.bundle_digest,
            horizon_increment_s=300,
            maximum_primitive_operations=10_000,
            model_version="reference-public-one-step-model-v1",
        ),
        state,
        bundle,
    )
    assert result.semantic_role == "simulation_only"
    assert snapshot.model_dump_json() == snapshot_before
    with pytest.raises(ValidationError):
        WorldModelEvidence.model_validate(result.model_dump(mode="json"))


def test_g3_digest_tampering_fails_closed(decision_fixture) -> None:
    snapshot, request, proposals = decision_fixture
    tampered = snapshot.model_copy(update={"policy_version": "tampered-policy"})
    with pytest.raises(ValueError, match="digest is invalid"):
        propose_reference_actions(request, tampered)
    assessments = {
        item.proposal_digest: _assessment(item.proposal_digest, CommitmentDecision.CLEAR)
        for item in (*proposals.physical_actions, *proposals.safe_alternatives)
    }
    bad_assessment = next(iter(assessments.values())).model_copy(
        update={"trace_record_version": 99}
    )
    assessments[bad_assessment.proposal_digest] = bad_assessment
    with pytest.raises(ValueError, match="assessment digest is invalid"):
        classify_reference_proposals(snapshot, proposals, assessments)


def test_g3_decision_package_contains_no_forbidden_policy_implementation() -> None:
    source = "\n".join(
        path.read_text("utf-8")
        for path in sorted((ROOT / "src/trace_reference/decision").glob("*.py"))
    ).casefold()
    for forbidden in (
        "borda",
        "pareto",
        "ambiguity_trigger",
        "branch_allocator",
        "rollout_budget",
        "successor_expansion",
    ):
        assert forbidden not in source


def test_g3_physical_acquisition_is_idempotent_authenticated_and_non_authorizing(
    decision_fixture,
) -> None:
    _, _, catalog = _catalog(decision_fixture)
    bundle = next(item for item in catalog.bundles if item.acquisition is not None)
    executor = EvidenceAcquisitionExecutor()
    request = executor.request(bundle)
    assert executor.request(bundle) == request

    provider = sign_provider_receipt(
        ProviderReceiptInput(
            receipt_id="provider-receipt-001",
            request=request,
            status="success",
            started_at_s=request.requested_at_s,
            observed_at_s=request.requested_at_s + 30,
            delivered_at_s=request.requested_at_s + 60,
            payload_json='{"crossing":"XNG-04","state":"open"}',
        )
    )
    outcome, evidence = executor.ingest(provider)
    assert outcome.outcome_status == "evidence-accepted"
    assert outcome.expected_physical_cost == bundle.acquisition.physical_cost
    assert outcome.charged_physical_cost == bundle.acquisition.physical_cost
    assert outcome.expected_latency_s == bundle.acquisition.expected_latency_s
    assert evidence is not None
    assert evidence.semantic_role == "physical_observation"
    with pytest.raises(ValidationError):
        WorldModelEvidence.model_validate(evidence.model_dump(mode="json"))

    replay, replay_evidence = executor.ingest(provider)
    assert replay.outcome_status == "duplicate-receipt-ignored"
    assert replay_evidence is None
    assert not hasattr(executor, "commit")


@pytest.mark.parametrize("status", ["timeout", "partial", "malformed", "failed"])
def test_g3_provider_failure_never_produces_physical_evidence(decision_fixture, status) -> None:
    _, _, catalog = _catalog(decision_fixture)
    bundle = next(item for item in catalog.bundles if item.acquisition is not None)
    executor = EvidenceAcquisitionExecutor()
    request = executor.request(bundle)
    provider = sign_provider_receipt(
        ProviderReceiptInput(
            receipt_id=f"provider-receipt-{status}",
            request=request,
            status=status,
            started_at_s=request.requested_at_s,
            observed_at_s=None,
            delivered_at_s=request.requested_at_s + 60,
            payload_json=None,
        )
    )
    outcome, evidence = executor.ingest(provider)
    assert outcome.outcome_status == f"provider-{status}"
    assert evidence is None


def test_g3_provider_timing_and_receipt_identity_fail_closed(decision_fixture) -> None:
    _, _, catalog = _catalog(decision_fixture)
    bundle = next(item for item in catalog.bundles if item.acquisition is not None)
    executor = EvidenceAcquisitionExecutor()
    request = executor.request(bundle)
    valid = sign_provider_receipt(
        ProviderReceiptInput(
            receipt_id="provider-receipt-late",
            request=request,
            status="success",
            started_at_s=request.requested_at_s,
            observed_at_s=request.requested_at_s + 30,
            delivered_at_s=request.latest_useful_delivery_s + 1,
            payload_json='{"crossing":"XNG-04","state":"open"}',
        )
    )
    late, evidence = executor.ingest(valid)
    assert late.outcome_status == "late-after-useful-deadline"
    assert evidence is None

    changed = valid.model_copy(update={"delivered_at_s": valid.delivered_at_s + 1})
    rejected, changed_evidence = executor.ingest(changed)
    assert rejected.outcome_status == "invalid-authentication"
    assert changed_evidence is None


def test_g3_signed_but_malformed_provider_payload_cannot_create_evidence(
    decision_fixture,
) -> None:
    _, _, catalog = _catalog(decision_fixture)
    bundle = next(item for item in catalog.bundles if item.acquisition is not None)
    executor = EvidenceAcquisitionExecutor()
    request = executor.request(bundle)
    malformed = sign_provider_receipt(
        ProviderReceiptInput(
            receipt_id="provider-receipt-malformed-json",
            request=request,
            status="success",
            started_at_s=request.requested_at_s,
            observed_at_s=request.requested_at_s + 30,
            delivered_at_s=request.requested_at_s + 60,
            payload_json="not-json",
        )
    )
    outcome, evidence = executor.ingest(malformed)
    assert outcome.outcome_status == "provider-malformed"
    assert evidence is None


def test_g3_unknown_request_records_no_invented_cost_or_latency(decision_fixture) -> None:
    _, _, catalog = _catalog(decision_fixture)
    bundle = next(item for item in catalog.bundles if item.acquisition is not None)
    request = EvidenceAcquisitionExecutor().request(bundle)
    provider = sign_provider_receipt(
        ProviderReceiptInput(
            receipt_id="provider-receipt-unknown-request",
            request=request,
            status="timeout",
            started_at_s=request.requested_at_s,
            observed_at_s=None,
            delivered_at_s=request.requested_at_s + 60,
            payload_json=None,
        )
    ).model_copy(update={"request_id": "missing-request"})
    outcome, evidence = EvidenceAcquisitionExecutor().ingest(provider)
    assert outcome.outcome_status == "unknown-request"
    assert outcome.request_digest is None
    assert outcome.expected_physical_cost is None
    assert outcome.charged_physical_cost is None
    assert outcome.expected_latency_s is None
    assert outcome.realized_latency_s is None
    assert evidence is None


def test_g3_cost_ledger_conserves_receipts_without_double_counting(
    decision_fixture,
) -> None:
    _, _, catalog = _catalog(decision_fixture)
    offer = next(item.acquisition for item in catalog.bundles if item.acquisition is not None)
    assert offer is not None
    first = build_cost_delta(
        CostDeltaInput(
            receipt_id="cost-receipt-001",
            physical_acquisition_costs=(offer.physical_cost,),
            predictor_inference_count=1,
            bytes_read=64,
        )
    )
    second = build_cost_delta(
        CostDeltaInput(
            receipt_id="cost-receipt-002",
            planning_transition_count=1,
            service_delay_s=30,
        )
    )
    ledger = DecisionCostLedger()
    ledger.append(first)
    ledger.append(first)
    ledger.append(second)
    totals = ledger.totals()
    assert totals.physical_acquisition_costs == (offer.physical_cost,)
    assert totals.predictor_inference_count == 1
    assert totals.planning_transition_count == 1
    assert totals.bytes_read == 64
    assert totals.service_delay_s == 30
    assert totals.receipt_ids == ("cost-receipt-001", "cost-receipt-002")

    conflicting = build_cost_delta(
        CostDeltaInput(
            receipt_id="cost-receipt-001",
            planning_transition_count=2,
        )
    )
    with pytest.raises(ValueError, match="reused with different content"):
        ledger.append(conflicting)


def test_g3_service_outcomes_preserve_completion_beyond_censoring() -> None:
    commitment = build_commitment_envelope(
        CommitmentEnvelopeInput(
            commitment_id="reference-commitment-001",
            authorizing_trace_record_id="trace-reference-001",
            authorizing_trace_record_version=2,
            selected_bundle_id="bundle-reference-001",
            selected_bundle_digest="1" * 64,
            selection_digest="2" * 64,
            public_snapshot_digest="3" * 64,
            committed_at_s=345_000,
        )
    )
    outcome = build_service_outcome(
        ServiceOutcomeInput(
            outcome_id="reference-outcome-001",
            commitment_id=commitment.commitment_id,
            status="active_at_scenario_censoring",
            scheduled_completion_s=348_600,
            observed_completion_s=None,
            authorizing_trace_record_id=commitment.authorizing_trace_record_id,
            authorizing_trace_record_version=commitment.authorizing_trace_record_version,
        )
    )
    assert outcome.scheduled_completion_s == 348_600
    assert outcome.observed_completion_s is None


def test_g3_exact_trace_closure_reassesses_consumes_and_commits(
    decision_fixture,
    tmp_path: Path,
) -> None:
    snapshot, _, _ = decision_fixture
    proposals, requests, evidences = _bound_proposals(decision_fixture)
    assessments = {
        item.proposal_digest: _assessment(item.proposal_digest, CommitmentDecision.CLEAR)
        for item in (*proposals.physical_actions, *proposals.safe_alternatives)
    }
    eligibility = classify_reference_proposals(snapshot, proposals, assessments)
    catalog = build_response_bundle_catalog(snapshot, proposals, eligibility)
    selection = BaseReferenceSelector().select(
        BaseSelectionRequest(
            catalog_digest=catalog.catalog_digest,
            public_snapshot_digest=snapshot.snapshot_digest,
            trace_prefix_digest=snapshot.trace_prefix_digest,
            at_s=snapshot.at_s,
        ),
        catalog,
    )
    bundle = next(
        item for item in catalog.bundles if item.bundle_id == selection.selected_bundle_id
    )
    proposal = next(
        item
        for item in (*proposals.physical_actions, *proposals.safe_alternatives)
        if item.proposal_digest == bundle.proposal_digest
    )
    claim = Claim(
        claim_id="reference-claim-g3-closure",
        layer=ClaimLayer.PREDICTIVE,
        text="The registered route and compatible resource support response.",
        grounding={"public_incident_id": proposal.action.destination_public_id},
        confidence=0.82,
        confidence_semantics="transparent Toy action-prefix fixture",
        created_at=datetime(2026, 1, 17, 4, 16, 40, tzinfo=UTC),
    )
    gateway = _trace_gateway(tmp_path)
    closure = gateway.commit_selected(
        SelectedCommitmentInput(
            bundle=bundle,
            catalog=catalog,
            selection=selection,
            proposal=proposal,
            assessment_input=ProposalAssessmentInput(
                proposal=proposal,
                snapshot=snapshot,
                predictor_request=requests[proposal.action.action_digest],
                evidence=evidences[proposal.action.action_digest],
                claim=claim,
                at_s=1_001,
                created_at=datetime(2026, 1, 17, 4, 16, 41, tzinfo=UTC),
                lineage_key="reference-g3-closure-lineage",
            ),
            consumer_action_id="reference-consumer-g3-closure",
        )
    )
    assert closure.commitment is not None
    assert closure.commitment_envelope is not None
    assert closure.commitment.authorizing_record_id == closure.consumed_record.record_id
    assert closure.commitment.authorizing_record_version == closure.consumed_record.record_version
    assert (
        closure.commitment_envelope.authorizing_trace_record_version
        == closure.consumed_record.record_version
    )
    assert gateway.runtime.repository.verify_chain()
    assert gateway.runtime.commitments.verify_chain()
    replay = gateway.event_log.replay()
    assert len(replay.public_mission_artifacts["trace_decision_recorded"]) == 2
    assert len(replay.public_mission_artifacts["commitment_created"]) == 1


def test_g3_post_selection_staleness_holds_without_commitment(
    decision_fixture,
    tmp_path: Path,
) -> None:
    snapshot, _, _ = decision_fixture
    proposals, requests, evidences = _bound_proposals(
        decision_fixture,
        observation_age_s=121,
    )
    assessments = {
        item.proposal_digest: _assessment(item.proposal_digest, CommitmentDecision.CLEAR)
        for item in (*proposals.physical_actions, *proposals.safe_alternatives)
    }
    eligibility = classify_reference_proposals(snapshot, proposals, assessments)
    catalog = build_response_bundle_catalog(snapshot, proposals, eligibility)
    selection = BaseReferenceSelector().select(
        BaseSelectionRequest(
            catalog_digest=catalog.catalog_digest,
            public_snapshot_digest=snapshot.snapshot_digest,
            trace_prefix_digest=snapshot.trace_prefix_digest,
            at_s=snapshot.at_s,
        ),
        catalog,
    )
    bundle = next(
        item for item in catalog.bundles if item.bundle_id == selection.selected_bundle_id
    )
    proposal = next(
        item
        for item in (*proposals.physical_actions, *proposals.safe_alternatives)
        if item.proposal_digest == bundle.proposal_digest
    )
    gateway = _trace_gateway(tmp_path)
    closure = gateway.commit_selected(
        SelectedCommitmentInput(
            bundle=bundle,
            catalog=catalog,
            selection=selection,
            proposal=proposal,
            assessment_input=ProposalAssessmentInput(
                proposal=proposal,
                snapshot=snapshot,
                predictor_request=requests[proposal.action.action_digest],
                evidence=evidences[proposal.action.action_digest],
                claim=Claim(
                    claim_id="reference-claim-g3-stale",
                    layer=ClaimLayer.PREDICTIVE,
                    text="The registered route and compatible resource support response.",
                    created_at=datetime(2026, 1, 17, 4, 16, 40, tzinfo=UTC),
                ),
                at_s=1_001,
                created_at=datetime(2026, 1, 17, 4, 16, 41, tzinfo=UTC),
                lineage_key="reference-g3-stale-lineage",
            ),
            consumer_action_id="reference-consumer-g3-stale",
        )
    )
    assert closure.assessment.commitment_decision == CommitmentDecision.HOLD
    assert closure.commitment is None
    assert closure.commitment_envelope is None
    assert gateway.runtime.commitments.all() == []


def test_g3_predictor_binding_requires_complete_exact_action_coverage(
    decision_fixture,
) -> None:
    _, _, proposals = decision_fixture
    with pytest.raises(ValueError, match="cover every action exactly"):
        bind_predictor_evidence(proposals, {})
