"""Public decision-result contracts for the Reference mission runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel
from trace_reference.decision import (
    AcquisitionRequestReceipt,
    BaseSelectionReceipt,
    EligibilityReceipt,
    ReferenceCommitmentEnvelope,
    ReferenceDecisionManifest,
    ReferenceTraceAssessment,
    ResponseBundleCatalog,
)
from trace_reference.decision.domain import ProposalSet
from trace_reference.reconciliation import ReferenceReconciliationStep


class ReferenceMissionDecision(DeltaModel):
    schema_version: Literal["delta-reference-mission-decision-v1"]
    decision_id: str
    call_id: str = Field(pattern=r"^RC-[0-9a-f]{16}$")
    controller_authority_id: Literal["AUTH-01", "AUTH-02", "AUTH-03", "AUTH-04"]
    belief_cluster_id: str = Field(pattern=r"^RBC-[0-9a-f]{16}$")
    decided_at_s: int = Field(ge=0, le=345_600)
    disposition: Literal["allocated", "refused", "acquisition-requested"]
    selected_bundle_id: str | None
    selected_resource_id: str | None = Field(default=None, pattern=r"^RR-[0-9a-f]{16}$")
    trace_record_id: str | None
    trace_record_version: int | None = Field(default=None, ge=1)
    commitment_id: str | None
    acquisition_request_id: str | None
    reason: str = Field(min_length=8)
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_disposition(self) -> ReferenceMissionDecision:
        allocated = self.disposition == "allocated"
        acquiring = self.disposition == "acquisition-requested"
        if allocated != (self.commitment_id is not None and self.selected_resource_id is not None):
            raise ValueError("Reference allocation disposition lacks exact commitment identity")
        if acquiring != (self.acquisition_request_id is not None):
            raise ValueError("Reference acquisition disposition lacks exact request identity")
        if (self.trace_record_id is None) != (self.trace_record_version is None):
            raise ValueError("Reference decision TRACE identity is incomplete")
        return self


@dataclass(frozen=True)
class ReferenceDecisionExecution:
    """Typed in-memory result; durable public identity is ReferenceMissionDecision."""

    result: ReferenceMissionDecision
    reconciliation: ReferenceReconciliationStep
    proposals: ProposalSet
    assessments: tuple[ReferenceTraceAssessment, ...]
    eligibility: EligibilityReceipt
    catalog: ResponseBundleCatalog
    selection: BaseSelectionReceipt
    commitment: ReferenceCommitmentEnvelope | None
    acquisition_request: AcquisitionRequestReceipt | None
    manifest: ReferenceDecisionManifest
