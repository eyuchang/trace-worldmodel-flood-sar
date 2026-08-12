from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import pytest

from trace_jepa.predictor import ToyActionPrefixPredictor
from trace_reference.decision.domain import (
    ControllerVisibleSnapshot,
    PhysicalActionProposal,
    ProposalRequest,
)
from trace_reference.decision.proposals import propose_reference_actions
from trace_reference.decision.visibility import (
    SnapshotInput,
    build_controller_visible_snapshot,
)
from trace_reference.domain.observations import ReferenceRawReport
from trace_reference.domain.routing import ReferencePublicRouteCatalog
from trace_reference.domain.scenario import ReferenceScenarioArtifacts
from trace_reference.generation import generate_reference_scenario
from trace_reference.runtime import (
    ReferencePredictorEvidenceInput,
    ReferenceRouteService,
    ReferenceScenarioIndex,
    build_reference_predictor_evidence,
    core_action_from_proposal,
)

ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class _PredictorFixture:
    aggregate: ReferenceScenarioArtifacts
    report: ReferenceRawReport
    proposal: PhysicalActionProposal
    snapshot: ControllerVisibleSnapshot
    route_catalog: ReferencePublicRouteCatalog
    at_s: int
    coordination_latency_s: int
    index: ReferenceScenarioIndex


@pytest.fixture(scope="module")
def predictor_fixture() -> _PredictorFixture:
    aggregate = generate_reference_scenario(ROOT, seed=20260812)
    index = ReferenceScenarioIndex.from_physical(
        aggregate.geography,
        aggregate.gauge_context,
        aggregate.physical,
    )
    route_service = ReferenceRouteService(index)
    envelope_by_call = {item.call_id: item for item in aggregate.observations.delivery.envelopes}
    for report in aggregate.observations.raw.reports:
        envelope = envelope_by_call[report.call_id]
        delivery = next(
            (
                item
                for item in aggregate.coordination.public.deliveries
                if item.evidence_id == envelope.envelope_id
                and item.recipient_authority_id == envelope.initial_authority_id
            ),
            None,
        )
        if delivery is None or not 0 <= delivery.delivered_at_s <= 340_000:
            continue
        at_s = delivery.delivered_at_s
        predictor = ToyActionPrefixPredictor()
        snapshot = build_controller_visible_snapshot(
            SnapshotInput(
                mission_id="reference-predictor-evidence-test",
                decision_id=f"decision-{report.call_id}",
                controller_authority_id=envelope.initial_authority_id,
                at_s=at_s,
                delivered_coordination_ids=frozenset(
                    item.delivery_id
                    for item in aggregate.coordination.public.deliveries
                    if item.delivered_at_s <= at_s
                ),
                evidence_prefix_digest="1" * 64,
                trace_prefix_digest="GENESIS",
                commitment_prefix_digest="GENESIS",
                environment_beliefs=(),
                active_commitments=(),
                known_outcomes=(),
                prior_profile_id=aggregate.prior.profile_id,
                policy_version="trace-reference-development-v1",
                environment_contract_version="trace-reference-python311-v1",
            ),
            aggregate.resources.public,
            aggregate.resources.public_catalog,
            aggregate.coordination.public,
            predictor.provenance(),
        )
        route_catalog = route_service.build_catalog(
            report,
            aggregate.resources.public_catalog,
            at_s=at_s,
        )
        request = ProposalRequest(
            schema_version="delta-reference-proposal-request-v2",
            decision_id=snapshot.decision_id,
            public_snapshot_digest=snapshot.snapshot_digest,
            target_public_incident_id=f"public-cluster-{report.call_id}",
            public_taxonomy=report.taxonomy.value,
            route_catalog=route_catalog,
            decision_deadline_s=min(345_600, at_s + 3_600),
            policy_version=snapshot.policy_version,
            proposal_namespace="reference-public-proposal-grammar-v1",
        )
        proposals = propose_reference_actions(request, snapshot)
        if proposals.physical_actions:
            return _PredictorFixture(
                aggregate=aggregate,
                report=report,
                proposal=proposals.physical_actions[0],
                snapshot=snapshot,
                route_catalog=route_catalog,
                at_s=at_s,
                coordination_latency_s=delivery.delivered_at_s - delivery.source_available_at_s,
                index=index,
            )
    raise AssertionError("development fixture produced no routable public proposal")


def _build(fixture: _PredictorFixture, *, report: ReferenceRawReport | None = None):
    aggregate = fixture.aggregate
    proposal = fixture.proposal
    snapshot = fixture.snapshot
    route_catalog = fixture.route_catalog
    predictor = ToyActionPrefixPredictor()
    return build_reference_predictor_evidence(
        ReferencePredictorEvidenceInput(
            proposal=proposal,
            snapshot=snapshot,
            report=report or fixture.report,
            route_catalog=route_catalog,
            resource_catalog=aggregate.resources.public_catalog,
            prior=aggregate.prior,
            index=fixture.index,
            predictor=predictor,
            at_s=fixture.at_s,
            coordination_latency_s=fixture.coordination_latency_s,
            created_at=(
                aggregate.config.timeline.evaluation_start_iso8601 + timedelta(seconds=fixture.at_s)
            ),
        )
    )


def test_predictor_request_binds_route_gauge_weather_resources_and_prior(
    predictor_fixture: _PredictorFixture,
) -> None:
    package = _build(predictor_fixture)
    proposal = predictor_fixture.proposal
    assert package.request.plan.first_action == core_action_from_proposal(proposal)
    route = package.request.observation.routes[0]
    assert route.route_id == proposal.action.route_id
    assert route.gauge_id == proposal.action.route_gauge_id
    assert route.gauge_threshold_status == "unavailable-non-operative"
    assert route.observation_age_s == predictor_fixture.at_s - route.crossing_sample_time_s
    assert package.request.observation.context.prior_profile.profile_id == (
        predictor_fixture.aggregate.prior.profile_id
    )
    assert package.request.observation.context.compatible_resources
    assert package.evidence.observation_window_hash == package.binding.predictor_request_digest
    assert package.binding.action_digest == proposal.action.action_digest
    assert package.claim.grounding["route_plan_digest"] == proposal.action.route_plan_digest
    assert package.evidence.observation_age_s == max(
        predictor_fixture.at_s - predictor_fixture.report.observed_at_s,
        route.observation_age_s,
        predictor_fixture.coordination_latency_s,
    )


def test_complete_request_digest_changes_with_visible_report_content(
    predictor_fixture: _PredictorFixture,
) -> None:
    baseline = _build(predictor_fixture)
    changed_report = predictor_fixture.report.model_copy(
        update={"descriptor_tokens": ("boat-ramp",)}
    )
    changed = _build(predictor_fixture, report=changed_report)
    assert baseline.request != changed.request
    assert baseline.binding.predictor_request_digest != changed.binding.predictor_request_digest
    assert baseline.evidence.evidence_id != changed.evidence.evidence_id
    assert baseline.binding.predictor_evidence_digest != changed.binding.predictor_evidence_digest


def test_predictor_surface_contains_no_hidden_truth(predictor_fixture: _PredictorFixture) -> None:
    package = _build(predictor_fixture)
    serialized = (
        f"{package.request.model_dump_json()}|"
        f"{package.evidence.model_dump_json()}|"
        f"{package.claim.model_dump_json()}"
    )
    for forbidden in (
        "truth_incident",
        "truth_person",
        "candidate_audit",
        "hidden_lineage",
        "breach_active",
    ):
        assert forbidden not in serialized
