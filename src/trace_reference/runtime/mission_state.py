"""Small typed state values shared by Reference mission execution and recovery."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum

from trace_jepa.contracts import Commitment
from trace_jepa.support import canonical_json_bytes
from trace_reference.decision import (
    AcquisitionRequestReceipt,
    ReferenceServiceOutcome,
    ServiceOutcomeInput,
    build_service_outcome,
)
from trace_reference.decision.domain import PublicCommitmentBelief
from trace_reference.domain import (
    ReferenceMissionDecision,
    ReferenceRawReport,
    ReferenceReportEnvelope,
    ReferenceScenarioArtifacts,
)
from trace_reference.domain.observations import ReferenceAuthorityId
from trace_reference.reconciliation import (
    ReferenceReconciliationArtifact,
    ReferenceReconciliationStep,
)

EVALUATION_END_S = 345_600


class ReferenceInputKind(str, Enum):
    PHYSICAL = "physical"
    PROVIDER = "provider"
    OUTCOME = "outcome"
    REPORT = "report"
    TELEMETRY = "telemetry"
    COORDINATION = "coordination"


@dataclass(order=True, frozen=True)
class ReferenceScheduledInput:
    """One queue item; payload is excluded from ordering and never copied."""

    at_s: int
    priority: int
    stable_id: str
    kind: ReferenceInputKind = field(compare=False)
    payload: object = field(compare=False)


@dataclass(frozen=True)
class ReferencePendingOutcome:
    outcome: ReferenceServiceOutcome
    resource_id: str


@dataclass(frozen=True)
class ReferencePendingAcquisition:
    request: AcquisitionRequestReceipt
    report: ReferenceRawReport
    envelope: ReferenceReportEnvelope
    reconciliation: ReferenceReconciliationStep
    original_decision: ReferenceMissionDecision


@dataclass(frozen=True)
class ReferenceActiveCommitment:
    belief: PublicCommitmentBelief
    scheduled_outcome: ReferenceServiceOutcome


@dataclass(frozen=True)
class ReferenceMissionRun:
    """Bounded in-memory view; the append-only stores remain authoritative."""

    through_s: int
    complete: bool
    decisions: tuple[ReferenceMissionDecision, ...]
    outcomes: tuple[ReferenceServiceOutcome, ...]
    reconciliations: tuple[ReferenceReconciliationArtifact, ...]
    event_prefix_digest: str
    trace_prefix_digest: str
    evidence_prefix_digest: str
    commitment_prefix_digest: str


ReferenceDecisionKey = tuple[ReferenceAuthorityId, str]


def reference_content_digest(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def reference_scenario_input_digest(scenario: ReferenceScenarioArtifacts) -> str:
    return reference_content_digest(
        {
            "config": scenario.config.model_dump(mode="json"),
            "geography": reference_content_digest(scenario.geography.model_dump(mode="json")),
            "physical": scenario.physical.physical_digest,
            "exposure": scenario.exposure.exposure_digest,
            "truth": scenario.truth.truth_digest,
            "raw_reports": scenario.observations.raw.raw_reports_digest,
            "delivery_envelopes": scenario.observations.delivery.delivery_envelopes_digest,
            "hidden_lineage": scenario.observations.hidden.hidden_digest,
            "resource_truth": scenario.resources.hidden.hidden_resource_digest,
            "resource_catalog": scenario.resources.public_catalog.resource_catalog_digest,
            "resource_telemetry": scenario.resources.public.telemetry_digest,
            "coordination": scenario.coordination.public.public_coordination_digest,
            "prior": scenario.prior.model_dump(mode="json"),
        }
    )


def reference_outcome_for_commitment(
    commitment: Commitment,
    scheduled_completion_s: int,
) -> ReferenceServiceOutcome:
    within = scheduled_completion_s <= EVALUATION_END_S
    return build_service_outcome(
        ServiceOutcomeInput(
            outcome_id=f"reference-outcome-{commitment.commitment_id[-20:]}",
            commitment_id=commitment.commitment_id,
            status=("completed_within_window" if within else "active_at_scenario_censoring"),
            scheduled_completion_s=scheduled_completion_s,
            observed_completion_s=scheduled_completion_s if within else None,
            authorizing_trace_record_id=commitment.authorizing_record_id,
            authorizing_trace_record_version=commitment.authorizing_record_version,
        )
    )
