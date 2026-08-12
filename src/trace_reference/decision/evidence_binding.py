"""Bind complete predictor requests and evidence to enumerated action proposals."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .canonical import decision_digest, verify_model_digest
from .domain import (
    PhysicalActionProposal,
    ProposalSet,
    SafeAlternativeProposal,
)


@dataclass(frozen=True)
class PredictorEvidenceBinding:
    action_digest: str
    predictor_request_digest: str
    predictor_evidence_digest: str


def _bind_action_proposal(
    proposal: PhysicalActionProposal | SafeAlternativeProposal,
    binding: PredictorEvidenceBinding,
) -> PhysicalActionProposal | SafeAlternativeProposal:
    if proposal.action.action_digest != binding.action_digest:
        raise ValueError("Reference predictor binding names another action")
    body = proposal.model_dump(mode="json", exclude={"proposal_digest"})
    body["predictor_request_digest"] = binding.predictor_request_digest
    body["predictor_evidence_digest"] = binding.predictor_evidence_digest
    if isinstance(proposal, PhysicalActionProposal):
        return PhysicalActionProposal(**body, proposal_digest=decision_digest(body))
    return SafeAlternativeProposal(**body, proposal_digest=decision_digest(body))


def bind_predictor_evidence(
    proposals: ProposalSet,
    bindings: Mapping[str, PredictorEvidenceBinding],
) -> ProposalSet:
    """Return the same complete grammar with exact per-action evidence bindings."""

    if not verify_model_digest(proposals, digest_field="proposal_set_digest"):
        raise ValueError("Reference proposal set digest is invalid")
    action_digests = {item.action.action_digest for item in proposals.physical_actions} | {
        item.action.action_digest for item in proposals.safe_alternatives
    }
    if set(bindings) != action_digests:
        raise ValueError("Reference predictor bindings must cover every action exactly")
    physical = tuple(
        _bind_action_proposal(item, bindings[item.action.action_digest])
        for item in proposals.physical_actions
    )
    safe = tuple(
        _bind_action_proposal(item, bindings[item.action.action_digest])
        for item in proposals.safe_alternatives
    )
    body = proposals.model_dump(mode="json", exclude={"proposal_set_digest"})
    body["physical_actions"] = [item.model_dump(mode="json") for item in physical]
    body["safe_alternatives"] = [item.model_dump(mode="json") for item in safe]
    return ProposalSet(**body, proposal_set_digest=decision_digest(body))
