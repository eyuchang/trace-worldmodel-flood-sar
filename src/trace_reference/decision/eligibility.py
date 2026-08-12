"""TRACE-bound eligibility classification and response-bundle construction."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from trace_jepa.contracts import CommitmentDecision

from .canonical import decision_digest, verify_model_digest
from .domain import (
    ControllerVisibleSnapshot,
    EligibilityKind,
    EligibilityReceipt,
    EvidenceAcquisitionOffer,
    PhysicalActionProposal,
    ProposalEligibility,
    ProposalSet,
    ReferenceTraceAssessment,
    ResponseBundle,
    ResponseBundleCatalog,
    ResponseBundleKind,
    SafeAlternativeProposal,
)


def _id(prefix: str, *parts: object) -> str:
    value = hashlib.sha256("|".join(str(item) for item in parts).encode()).hexdigest()
    return f"{prefix}-{value[:20]}"


def _action_eligibility(
    proposal: PhysicalActionProposal | SafeAlternativeProposal,
    assessment: ReferenceTraceAssessment | None,
) -> ProposalEligibility:
    safe = isinstance(proposal, SafeAlternativeProposal)
    kind = EligibilityKind.SAFE_ALTERNATIVE if safe else EligibilityKind.ACT_NOW
    missing = assessment is None
    eligible = bool(
        assessment is not None
        and assessment.proposal_digest == proposal.proposal_digest
        and assessment.commitment_decision == CommitmentDecision.CLEAR
        and assessment.authorization_sufficient_for_action
    )
    failed = (
        ("trace-assessment-missing",)
        if missing
        else assessment.failed_gates
        if assessment is not None
        else ()
    )
    body = {
        "proposal_id": proposal.proposal_id,
        "proposal_digest": proposal.proposal_digest,
        "eligibility_kind": (kind if eligible else EligibilityKind.EXCLUDED).value,
        "eligible": eligible,
        "trace_assessment_digest": (
            assessment.assessment_digest if assessment is not None else None
        ),
        "failed_gates": failed,
        "reason": (
            "TRACE independently authorized this public action proposal."
            if eligible
            else "The proposal lacks a current action-sufficient TRACE authorization."
        ),
    }
    return ProposalEligibility(**body, classification_digest=decision_digest(body))


def _acquisition_eligibility(offer: EvidenceAcquisitionOffer) -> ProposalEligibility:
    failures = []
    if offer.clear_probability_micros < offer.required_clear_probability_micros:
        failures.append("preposterior-adequacy")
    if offer.requested_at_s + offer.expected_latency_s > offer.latest_useful_delivery_s:
        failures.append("deadline-feasibility")
    if offer.value_of_information_microunits <= offer.physical_cost.quantity_microunits:
        failures.append("positive-net-value")
    if not offer.provider_available:
        failures.append("provider-availability")
    if not offer.authority_present:
        failures.append("authority")
    if not offer.minimum_interval_clear:
        failures.append("minimum-interval")
    if not offer.no_pending_request:
        failures.append("pending-request")
    eligible = not failures
    body = {
        "proposal_id": offer.proposal_id,
        "proposal_digest": offer.proposal_digest,
        "eligibility_kind": (
            EligibilityKind.ACQUIRE_THEN_REASSESS if eligible else EligibilityKind.EXCLUDED
        ).value,
        "eligible": eligible,
        "trace_assessment_digest": None,
        "failed_gates": tuple(failures),
        "reason": (
            "Physical acquisition is adequate, deadline-feasible, positive-net, and guard-clear."
            if eligible
            else "Physical acquisition failed one or more pre-selection eligibility gates."
        ),
    }
    return ProposalEligibility(**body, classification_digest=decision_digest(body))


def classify_reference_proposals(
    snapshot: ControllerVisibleSnapshot,
    proposals: ProposalSet,
    trace_assessments: Mapping[str, ReferenceTraceAssessment],
) -> EligibilityReceipt:
    """Classify every root before selection using exact TRACE assessment receipts."""

    if not verify_model_digest(snapshot, digest_field="snapshot_digest"):
        raise ValueError("Reference public snapshot digest is invalid")
    if not verify_model_digest(proposals, digest_field="proposal_set_digest"):
        raise ValueError("Reference proposal-set digest is invalid")
    if not verify_model_digest(proposals.enumeration_receipt, digest_field="receipt_digest"):
        raise ValueError("Reference proposal enumeration digest is invalid")
    nested = (
        *proposals.physical_actions,
        *proposals.acquisition_offers,
        *proposals.safe_alternatives,
    )
    if any(not verify_model_digest(item, digest_field="proposal_digest") for item in nested):
        raise ValueError("Reference nested proposal digest is invalid")
    if any(
        not verify_model_digest(item, digest_field="assessment_digest")
        for item in trace_assessments.values()
    ):
        raise ValueError("Reference TRACE assessment digest is invalid")
    if not proposals.enumeration_receipt.complete_for_declared_grammar:
        trace_assessments = {}
    classifications = [
        _action_eligibility(item, trace_assessments.get(item.proposal_digest))
        for item in proposals.physical_actions
    ]
    classifications.extend(
        _action_eligibility(item, trace_assessments.get(item.proposal_digest))
        for item in proposals.safe_alternatives
    )
    classifications.extend(_acquisition_eligibility(item) for item in proposals.acquisition_offers)
    classifications.sort(key=lambda item: item.proposal_id)
    body = {
        "schema_version": "delta-reference-eligibility-receipt-v1",
        "decision_id": proposals.decision_id,
        "public_snapshot_digest": snapshot.snapshot_digest,
        "proposal_set_digest": proposals.proposal_set_digest,
        "classified_at_s": snapshot.at_s,
        "classifications": [item.model_dump(mode="json") for item in classifications],
    }
    return EligibilityReceipt(**body, eligibility_receipt_digest=decision_digest(body))


def _bundle(
    proposal: PhysicalActionProposal | SafeAlternativeProposal | EvidenceAcquisitionOffer,
    classification: ProposalEligibility,
    snapshot: ControllerVisibleSnapshot,
) -> ResponseBundle:
    reversible: bool | None
    if isinstance(proposal, EvidenceAcquisitionOffer):
        kind = ResponseBundleKind.ACQUIRE_THEN_REASSESS
        action = None
        acquisition = proposal
        consequence = "low"
        reversible = None
        authority_requirement = None
        authority_evidence_ids: tuple[str, ...] = ()
        deadline = proposal.latest_useful_delivery_s
    elif isinstance(proposal, SafeAlternativeProposal):
        kind = ResponseBundleKind.SAFE_ALTERNATIVE
        action = proposal.action
        acquisition = None
        consequence = proposal.consequence_class
        reversible = proposal.reversible
        authority_requirement = proposal.authority_requirement
        authority_evidence_ids = proposal.current_authority_evidence_ids
        deadline = proposal.action.execution_not_after_s
    else:
        kind = ResponseBundleKind.ACT_NOW
        action = proposal.action
        acquisition = None
        consequence = proposal.consequence_class
        reversible = proposal.reversible
        authority_requirement = proposal.authority_requirement
        authority_evidence_ids = proposal.current_authority_evidence_ids
        deadline = proposal.action.execution_not_after_s
    body = {
        "schema_version": "delta-reference-response-bundle-v1",
        "decision_id": snapshot.decision_id,
        "bundle_id": _id("bundle", proposal.proposal_id, classification.classification_digest),
        "kind": kind.value,
        "proposal_digest": proposal.proposal_digest,
        "classification_digest": classification.classification_digest,
        "public_snapshot_digest": snapshot.snapshot_digest,
        "action": action.model_dump(mode="json") if action is not None else None,
        "acquisition": acquisition.model_dump(mode="json") if acquisition is not None else None,
        "deadline_s": deadline,
        "consequence_class": consequence,
        "reversible": reversible,
        "authority_requirement": authority_requirement,
        "current_authority_evidence_ids": authority_evidence_ids,
        "fallback_disposition": CommitmentDecision.HOLD.value,
    }
    return ResponseBundle(**body, bundle_digest=decision_digest(body))


def build_response_bundle_catalog(
    snapshot: ControllerVisibleSnapshot,
    proposals: ProposalSet,
    eligibility: EligibilityReceipt,
) -> ResponseBundleCatalog:
    """Materialize every eligible root without ranking, truncation, or fallback roots."""

    if eligibility.proposal_set_digest != proposals.proposal_set_digest:
        raise ValueError("Reference eligibility receipt does not bind the proposal set")
    if not verify_model_digest(snapshot, digest_field="snapshot_digest"):
        raise ValueError("Reference public snapshot digest is invalid")
    if not verify_model_digest(eligibility, digest_field="eligibility_receipt_digest"):
        raise ValueError("Reference eligibility-receipt digest is invalid")
    if any(
        not verify_model_digest(item, digest_field="classification_digest")
        for item in eligibility.classifications
    ):
        raise ValueError("Reference proposal-classification digest is invalid")
    proposal_by_id: dict[
        str,
        PhysicalActionProposal | SafeAlternativeProposal | EvidenceAcquisitionOffer,
    ] = {}
    for proposal in proposals.physical_actions:
        proposal_by_id[proposal.proposal_id] = proposal
    for offer in proposals.acquisition_offers:
        proposal_by_id[offer.proposal_id] = offer
    for alternative in proposals.safe_alternatives:
        proposal_by_id[alternative.proposal_id] = alternative
    classifications = {item.proposal_id: item for item in eligibility.classifications}
    bundles = [
        _bundle(proposal_by_id[proposal_id], classification, snapshot)
        for proposal_id, classification in classifications.items()
        if classification.eligible
    ]
    consequence_order = {"low": 0, "moderate": 1, "high": 2}
    kind_order = {
        ResponseBundleKind.ACT_NOW: 0,
        ResponseBundleKind.SAFE_ALTERNATIVE: 1,
        ResponseBundleKind.ACQUIRE_THEN_REASSESS: 2,
    }
    bundles.sort(
        key=lambda item: (
            consequence_order[item.consequence_class],
            item.deadline_s,
            kind_order[item.kind],
            item.bundle_id,
        )
    )
    excluded = tuple(
        sorted(
            item.classification_digest for item in eligibility.classifications if not item.eligible
        )
    )
    complete = proposals.enumeration_receipt.complete_for_declared_grammar
    body = {
        "schema_version": "delta-reference-response-bundle-catalog-v1",
        "decision_id": proposals.decision_id,
        "bundles": [item.model_dump(mode="json") for item in bundles] if complete else [],
        "excluded_classification_digests": excluded,
        "proposal_enumeration_receipt_digest": proposals.enumeration_receipt.receipt_digest,
        "eligibility_receipt_digest": eligibility.eligibility_receipt_digest,
        "complete_for_declared_grammar": complete,
        "trace_prefix_digest": snapshot.trace_prefix_digest,
    }
    return ResponseBundleCatalog(**body, catalog_digest=decision_digest(body))
