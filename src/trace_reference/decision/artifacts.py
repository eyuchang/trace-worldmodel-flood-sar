"""Commitment, outcome, compensation, and decision-manifest envelopes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel

from .canonical import decision_digest


class ReferenceCommitmentEnvelope(DeltaModel):
    schema_version: Literal["delta-reference-commitment-envelope-v1"]
    commitment_id: str
    authorizing_trace_record_id: str
    authorizing_trace_record_version: int = Field(ge=1)
    selected_bundle_id: str
    selected_bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    committed_at_s: int = Field(ge=-172_800, le=345_600)
    envelope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReferenceServiceOutcome(DeltaModel):
    schema_version: Literal["delta-reference-service-outcome-v1"]
    outcome_id: str
    commitment_id: str
    status: Literal["completed_within_window", "active_at_scenario_censoring"]
    scheduled_completion_s: int
    observed_completion_s: int | None
    censoring_s: Literal[345600]
    authorizing_trace_record_id: str
    authorizing_trace_record_version: int = Field(ge=1)
    outcome_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_censoring(self) -> ReferenceServiceOutcome:
        within = self.scheduled_completion_s <= self.censoring_s
        if within != (self.status == "completed_within_window"):
            raise ValueError("Reference service outcome status disagrees with censoring")
        if within != (self.observed_completion_s == self.scheduled_completion_s):
            raise ValueError("Reference completion observation disagrees with schedule")
        return self


class ReferenceCompensationRecord(DeltaModel):
    schema_version: Literal["delta-reference-compensation-v1"]
    compensation_id: str
    invalidated_commitment_id: str
    triggering_trace_record_id: str
    triggering_trace_record_version: int = Field(ge=1)
    attempted_at_s: int = Field(ge=-172_800, le=345_600)
    status: Literal["completed", "failed", "not-required"]
    reason: str
    compensation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReferenceDecisionManifest(DeltaModel):
    schema_version: Literal["delta-reference-decision-manifest-v1"]
    decision_id: str
    public_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    eligibility_receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    acquisition_request_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    acquisition_outcome_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    post_delay_trace_record_id: str | None
    post_delay_trace_record_version: int | None = Field(default=None, ge=1)
    commitment_envelope_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    cost_delta_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_trace_pair(self) -> ReferenceDecisionManifest:
        if (self.post_delay_trace_record_id is None) != (
            self.post_delay_trace_record_version is None
        ):
            raise ValueError("Reference decision manifest TRACE identity is incomplete")
        return self


@dataclass(frozen=True)
class CommitmentEnvelopeInput:
    commitment_id: str
    authorizing_trace_record_id: str
    authorizing_trace_record_version: int
    selected_bundle_id: str
    selected_bundle_digest: str
    selection_digest: str
    public_snapshot_digest: str
    committed_at_s: int


@dataclass(frozen=True)
class ServiceOutcomeInput:
    outcome_id: str
    commitment_id: str
    status: Literal["completed_within_window", "active_at_scenario_censoring"]
    scheduled_completion_s: int
    observed_completion_s: int | None
    authorizing_trace_record_id: str
    authorizing_trace_record_version: int


@dataclass(frozen=True)
class CompensationRecordInput:
    compensation_id: str
    invalidated_commitment_id: str
    triggering_trace_record_id: str
    triggering_trace_record_version: int
    attempted_at_s: int
    status: Literal["completed", "failed", "not-required"]
    reason: str


@dataclass(frozen=True)
class DecisionManifestInput:
    decision_id: str
    public_snapshot_digest: str
    proposal_set_digest: str
    eligibility_receipt_digest: str
    catalog_digest: str
    selection_digest: str
    cost_delta_digest: str
    acquisition_request_digest: str | None = None
    acquisition_outcome_digest: str | None = None
    post_delay_trace_record_id: str | None = None
    post_delay_trace_record_version: int | None = None
    commitment_envelope_digest: str | None = None


def build_commitment_envelope(
    values: CommitmentEnvelopeInput,
) -> ReferenceCommitmentEnvelope:
    body = {
        "schema_version": "delta-reference-commitment-envelope-v1",
        **values.__dict__,
    }
    return ReferenceCommitmentEnvelope(**body, envelope_digest=decision_digest(body))


def build_service_outcome(values: ServiceOutcomeInput) -> ReferenceServiceOutcome:
    body = {
        "schema_version": "delta-reference-service-outcome-v1",
        **values.__dict__,
        "censoring_s": 345_600,
    }
    return ReferenceServiceOutcome(**body, outcome_digest=decision_digest(body))


def build_compensation_record(
    values: CompensationRecordInput,
) -> ReferenceCompensationRecord:
    body = {"schema_version": "delta-reference-compensation-v1", **values.__dict__}
    return ReferenceCompensationRecord(**body, compensation_digest=decision_digest(body))


def build_decision_manifest(values: DecisionManifestInput) -> ReferenceDecisionManifest:
    body = {"schema_version": "delta-reference-decision-manifest-v1", **values.__dict__}
    return ReferenceDecisionManifest(**body, manifest_digest=decision_digest(body))
