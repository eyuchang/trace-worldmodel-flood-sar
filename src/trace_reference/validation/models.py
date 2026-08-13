"""Typed reports for constructed Reference runtime-integrity checks."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel
from trace_reference.decision.canonical import model_digest
from trace_reference.domain.faults import ReferenceFaultFamily


class ReferenceRuntimeCounts(DeltaModel):
    """Descriptive counts from one complete Reference mission execution."""

    decisions: int = Field(ge=0)
    allocations: int = Field(ge=0)
    refusals: int = Field(ge=0)
    acquisition_requests: int = Field(ge=0)
    outcomes: int = Field(ge=0)
    reconciliations: int = Field(ge=0)
    compensations: int = Field(ge=0)
    consistency_debts: int = Field(ge=0)


class ReferenceG3IntegrityReport(DeltaModel):
    """Constructed engineering evidence; it is not a statistical validation result."""

    schema_version: Literal["delta-reference-g3-runtime-integrity-v2"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    scenario_seed: int = Field(ge=0, le=2_147_483_647)
    scientific_input_aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scenario_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    scientific_status: Literal["development-integration-check-not-validation-evidence"]
    fault_profile_id: Literal["reference-faulted-v1"]
    expected_fault_families: tuple[ReferenceFaultFamily, ...]
    observed_fault_families: tuple[ReferenceFaultFamily, ...]
    faulted_counts: ReferenceRuntimeCounts
    event_chains_valid: bool
    trace_chains_valid: bool
    evidence_chains_valid: bool
    commitment_chains_valid: bool
    fault_coverage_complete: bool
    fault_targets_all_reachable: bool
    exogenous_inputs_byte_equivalent: bool
    restart_public_state_equivalent: bool
    restart_durable_state_equivalent: bool
    authorization_joins_valid: bool
    correction_joins_valid: bool
    public_artifacts_hidden_free: bool
    all_checks_pass: bool
    report_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_report(self) -> ReferenceG3IntegrityReport:
        if self.expected_fault_families != tuple(sorted(set(self.expected_fault_families))):
            raise ValueError("Reference expected fault families must be unique and ordered")
        if self.observed_fault_families != tuple(sorted(set(self.observed_fault_families))):
            raise ValueError("Reference observed fault families must be unique and ordered")
        checks = (
            self.event_chains_valid,
            self.trace_chains_valid,
            self.evidence_chains_valid,
            self.commitment_chains_valid,
            self.fault_coverage_complete,
            self.fault_targets_all_reachable,
            self.exogenous_inputs_byte_equivalent,
            self.restart_public_state_equivalent,
            self.restart_durable_state_equivalent,
            self.authorization_joins_valid,
            self.correction_joins_valid,
            self.public_artifacts_hidden_free,
        )
        if self.all_checks_pass != all(checks):
            raise ValueError("Reference G3 aggregate status disagrees with its checks")
        if model_digest(self, digest_field="report_digest") != self.report_digest:
            raise ValueError("Reference G3 integrity report digest is invalid")
        return self
