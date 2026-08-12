from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from trace_jepa.contracts import CommitmentDecision, WorldModelEvidence
from trace_jepa.predictor import ToyActionPrefixPredictor
from trace_reference import load_reference_resource_parameters
from trace_reference.decision.canonical import decision_digest
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
    delivery = ReferenceCoordinationDelivery(
        delivery_id="CD-0000000000000001",
        evidence_kind="resource-telemetry",
        evidence_id=telemetry[0].telemetry_id,
        source_authority_id="AUTH-04",
        recipient_authority_id="AUTH-01",
        recipient_partition_id="AUTH-01-P01",
        source_available_at_s=900,
        delivered_at_s=900,
        source_content_digest="2" * 64,
    )
    coordination = ReferencePublicCoordinationScenario(
        scenario_id="WF-DFLD-01-REFERENCE",
        schema_version="delta-reference-coordination-v1",
        seed=20260812,
        phi=4,
        authority_registry_version="delta-reference-governance-v1",
        deliveries=(delivery,),
        public_coordination_digest="3" * 64,
    )
    snapshot = build_controller_visible_snapshot(
        SnapshotInput(
            mission_id="reference-mission-development",
            decision_id="reference-decision-001",
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
