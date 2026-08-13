"""Typed, non-inferential contracts for Reference Phase 6 acceptance."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal, TypeAlias

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel
from trace_reference.decision.canonical import model_digest

from .models import ReferenceG3IntegrityReport

ReferencePhase6CheckId: TypeAlias = Literal[
    "P6-SOURCE-BOUND",
    "P6-SPENT-SEED",
    "P6-DETERMINISM",
    "P6-NOMINAL-RUNTIME",
    "P6-FAULT-COVERAGE",
    "P6-RESTART-EQUIVALENCE",
    "P6-CHAIN-INTEGRITY",
    "P6-HIDDEN-SEPARATION",
    "P6-AXIS-ISOLATION",
    "P6-CONSERVATION",
    "P6-CAPACITY-ACCOUNTING",
    "P6-EXACT-REPLAY",
    "P6-PUBLICATION-REGENERATION",
    "P6-OFFLINE-EXECUTION",
]
ReferencePhase6AxisId: TypeAlias = Literal[
    "sigma",
    "kappa",
    "mu",
    "iota",
    "phi",
    "pi",
    "epsilon",
    "delta",
]

REFERENCE_PHASE6_CHECK_IDS: tuple[ReferencePhase6CheckId, ...] = (
    "P6-SOURCE-BOUND",
    "P6-SPENT-SEED",
    "P6-DETERMINISM",
    "P6-NOMINAL-RUNTIME",
    "P6-FAULT-COVERAGE",
    "P6-RESTART-EQUIVALENCE",
    "P6-CHAIN-INTEGRITY",
    "P6-HIDDEN-SEPARATION",
    "P6-AXIS-ISOLATION",
    "P6-CONSERVATION",
    "P6-CAPACITY-ACCOUNTING",
    "P6-EXACT-REPLAY",
    "P6-PUBLICATION-REGENERATION",
    "P6-OFFLINE-EXECUTION",
)
REFERENCE_PHASE6_AXIS_IDS: tuple[ReferencePhase6AxisId, ...] = (
    "sigma",
    "kappa",
    "mu",
    "iota",
    "phi",
    "pi",
    "epsilon",
    "delta",
)


class ReferencePhase6FileBinding(DeltaModel):
    """One trusted repository input bound by path, length, and digest."""

    repository_relative_path: str = Field(pattern=r"^[a-zA-Z0-9_./-]+$")
    byte_length: int = Field(gt=0, le=268_435_456)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_path(self) -> ReferencePhase6FileBinding:
        path = PurePosixPath(self.repository_relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Reference Phase 6 file binding path is unsafe")
        return self


class ReferencePhase6AxisResult(DeltaModel):
    """One causal-isolation result without statistical interpretation."""

    axis: ReferencePhase6AxisId
    baseline_value: str = Field(min_length=1, max_length=80)
    variant_value: str = Field(min_length=1, max_length=80)
    unchanged_stage_names: tuple[str, ...] = Field(min_length=1)
    changed_stage_names: tuple[str, ...] = Field(min_length=1)
    mechanism_checks: tuple[tuple[str, bool], ...] = Field(min_length=1)
    observed_digests: tuple[tuple[str, str], ...] = Field(min_length=1)
    keyed_draw_identity_preserved: bool
    passed: bool
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_axis_result(self) -> ReferencePhase6AxisResult:
        if self.unchanged_stage_names != tuple(sorted(set(self.unchanged_stage_names))):
            raise ValueError("Reference unchanged axis stages must be unique and ordered")
        if self.changed_stage_names != tuple(sorted(set(self.changed_stage_names))):
            raise ValueError("Reference changed axis stages must be unique and ordered")
        if set(self.unchanged_stage_names) & set(self.changed_stage_names):
            raise ValueError("Reference axis stage cannot be both changed and unchanged")
        if self.mechanism_checks != tuple(sorted(self.mechanism_checks)):
            raise ValueError("Reference axis mechanism checks must be ordered")
        if len({name for name, _passed in self.mechanism_checks}) != len(self.mechanism_checks):
            raise ValueError("Reference axis mechanism check names must be unique")
        if self.observed_digests != tuple(sorted(self.observed_digests)):
            raise ValueError("Reference axis observed digests must be ordered")
        if len({name for name, _digest in self.observed_digests}) != len(self.observed_digests):
            raise ValueError("Reference axis observed-digest names must be unique")
        if any(
            len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest)
            for _name, digest in self.observed_digests
        ):
            raise ValueError("Reference axis observations must contain SHA-256 digests")
        if self.passed != (
            self.keyed_draw_identity_preserved
            and all(passed for _name, passed in self.mechanism_checks)
        ):
            raise ValueError("Reference axis aggregate status disagrees with its checks")
        if self.passed and not self.keyed_draw_identity_preserved:
            raise ValueError("Reference axis cannot pass without keyed-draw identity")
        if model_digest(self, digest_field="evidence_digest") != self.evidence_digest:
            raise ValueError("Reference axis result digest is invalid")
        return self


class ReferencePhase6CheckResult(DeltaModel):
    """One deterministic integration-acceptance result."""

    check_id: ReferencePhase6CheckId
    passed: bool
    evidence_digests: tuple[str, ...] = Field(min_length=1)
    note: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def validate_evidence(self) -> ReferencePhase6CheckResult:
        if self.evidence_digests != tuple(sorted(set(self.evidence_digests))):
            raise ValueError("Reference Phase 6 evidence digests must be unique and ordered")
        if any(
            len(item) != 64 or any(char not in "0123456789abcdef" for char in item)
            for item in self.evidence_digests
        ):
            raise ValueError("Reference Phase 6 evidence digests must be SHA-256 values")
        return self


class ReferencePhase6ResourceReceipt(DeltaModel):
    """Bounded execution observation separated from scientific outputs."""

    schema_version: Literal["delta-reference-phase6-resource-receipt-v1"]
    measurement_role: Literal["local-preflight", "canonical"]
    platform: str = Field(min_length=3, max_length=160)
    python_version: str = Field(pattern=r"^3\.[0-9]+\.[0-9]+$")
    elapsed_milliseconds: int = Field(gt=0)
    peak_resident_memory_bytes: int | None = Field(default=None, gt=0)
    transient_output_bytes: int = Field(ge=0)
    wall_time_limit_s: Literal[900]
    peak_memory_limit_bytes: Literal[2147483648]
    transient_output_limit_bytes: Literal[1073741824]
    wall_time_within_limit: bool
    peak_memory_within_limit: bool | None
    transient_output_within_limit: bool
    canonical_gate_status: Literal["passed", "failed", "pending-canonical-environment"]
    receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_receipt(self) -> ReferencePhase6ResourceReceipt:
        if self.wall_time_within_limit != (self.elapsed_milliseconds <= 900_000):
            raise ValueError("Reference Phase 6 wall-time status is inconsistent")
        expected_memory = (
            None
            if self.peak_resident_memory_bytes is None
            else self.peak_resident_memory_bytes <= self.peak_memory_limit_bytes
        )
        if self.peak_memory_within_limit != expected_memory:
            raise ValueError("Reference Phase 6 memory status is inconsistent")
        if self.transient_output_within_limit != (
            self.transient_output_bytes <= self.transient_output_limit_bytes
        ):
            raise ValueError("Reference Phase 6 disk status is inconsistent")
        if self.measurement_role == "canonical":
            expected_status = (
                "passed"
                if self.wall_time_within_limit
                and self.peak_memory_within_limit is True
                and self.transient_output_within_limit
                else "failed"
            )
        else:
            expected_status = "pending-canonical-environment"
        if self.canonical_gate_status != expected_status:
            raise ValueError("Reference Phase 6 canonical resource status is inconsistent")
        if model_digest(self, digest_field="receipt_digest") != self.receipt_digest:
            raise ValueError("Reference Phase 6 resource receipt digest is invalid")
        return self


class ReferencePhase6CoreReceipt(DeltaModel):
    """Nominal run, exact replay, publication, and bounded resource evidence."""

    schema_version: Literal["delta-reference-phase6-core-receipt-v1"]
    scientific_status: Literal["development-integration-check-not-validation-evidence"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    seed: Literal[20260812]
    scientific_input_aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    nominal_replay_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    nominal_scenario_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    exact_replay_byte_identical: bool
    publication_regeneration_byte_identical: bool
    nominal_runtime_complete: bool
    event_chain_valid: bool
    trace_chain_valid: bool
    evidence_chain_valid: bool
    commitment_chain_valid: bool
    authorization_joins_valid: bool
    correction_joins_valid: bool
    resource_crew_conservation_valid: bool
    commitment_conservation_valid: bool
    outcome_censoring_valid: bool
    capacity_accounting_valid: bool
    public_bundle_hidden_free: bool
    offline_execution_guarded: bool
    resource_receipt: ReferencePhase6ResourceReceipt
    all_checks_pass: bool
    receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_core_receipt(self) -> ReferencePhase6CoreReceipt:
        checks = (
            self.exact_replay_byte_identical,
            self.publication_regeneration_byte_identical,
            self.nominal_runtime_complete,
            self.event_chain_valid,
            self.trace_chain_valid,
            self.evidence_chain_valid,
            self.commitment_chain_valid,
            self.authorization_joins_valid,
            self.correction_joins_valid,
            self.resource_crew_conservation_valid,
            self.commitment_conservation_valid,
            self.outcome_censoring_valid,
            self.capacity_accounting_valid,
            self.public_bundle_hidden_free,
            self.offline_execution_guarded,
        )
        if self.all_checks_pass != all(checks):
            raise ValueError("Reference Phase 6 core aggregate status is inconsistent")
        if model_digest(self, digest_field="receipt_digest") != self.receipt_digest:
            raise ValueError("Reference Phase 6 core receipt digest is invalid")
        return self


class ReferencePhase6IsolationReceipt(DeltaModel):
    """Full-run hidden-lineage and causal-axis development checks."""

    schema_version: Literal["delta-reference-phase6-isolation-receipt-v1"]
    scientific_status: Literal["development-integration-check-not-validation-evidence"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    seed: Literal[20260812]
    scientific_input_aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    nominal_replay_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    hidden_lineage_removed: Literal[True]
    public_decisions_byte_equivalent: bool
    public_outcomes_byte_equivalent: bool
    public_reconciliations_byte_equivalent: bool
    public_event_projection_byte_equivalent: bool
    trace_chain_byte_equivalent: bool
    evidence_chain_byte_equivalent: bool
    commitment_chain_byte_equivalent: bool
    axis_results: tuple[ReferencePhase6AxisResult, ...] = Field(min_length=8, max_length=8)
    all_checks_pass: bool
    receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_isolation_receipt(self) -> ReferencePhase6IsolationReceipt:
        if tuple(item.axis for item in self.axis_results) != REFERENCE_PHASE6_AXIS_IDS:
            raise ValueError("Reference Phase 6 isolation receipt has incomplete axes")
        checks = (
            self.public_decisions_byte_equivalent,
            self.public_outcomes_byte_equivalent,
            self.public_reconciliations_byte_equivalent,
            self.public_event_projection_byte_equivalent,
            self.trace_chain_byte_equivalent,
            self.evidence_chain_byte_equivalent,
            self.commitment_chain_byte_equivalent,
            all(item.passed for item in self.axis_results),
        )
        if self.all_checks_pass != all(checks):
            raise ValueError("Reference Phase 6 isolation aggregate status is inconsistent")
        if model_digest(self, digest_field="receipt_digest") != self.receipt_digest:
            raise ValueError("Reference Phase 6 isolation receipt digest is invalid")
        return self


class ReferencePhase6FaultReceipt(DeltaModel):
    """Offline-guarded binding of the registered G3 fault/restart execution."""

    schema_version: Literal["delta-reference-phase6-fault-receipt-v1"]
    scientific_status: Literal["development-integration-check-not-validation-evidence"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    seed: Literal[20260812]
    offline_execution_guarded: Literal[True]
    integrity_report: ReferenceG3IntegrityReport
    all_checks_pass: bool
    receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_fault_receipt(self) -> ReferencePhase6FaultReceipt:
        if self.all_checks_pass != self.integrity_report.all_checks_pass:
            raise ValueError("Reference Phase 6 fault status disagrees with G3 integrity")
        if self.integrity_report.scenario_seed != self.seed:
            raise ValueError("Reference Phase 6 fault receipt mixes scenario seeds")
        if model_digest(self, digest_field="receipt_digest") != self.receipt_digest:
            raise ValueError("Reference Phase 6 fault receipt digest is invalid")
        return self


class ReferencePhase6AcceptanceReport(DeltaModel):
    """Source-bound Phase 6 result with no inferential or holdout authority."""

    schema_version: Literal["delta-reference-phase6-development-acceptance-v1"]
    scientific_status: Literal["development-integration-acceptance-not-validation-evidence"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    seed: Literal[20260812]
    seed_status: Literal["spent-development-illustrative"]
    protocol: ReferencePhase6FileBinding
    scientific_input_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    g3_handoff_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    nominal_replay_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    fault_integrity_report_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    checks: tuple[ReferencePhase6CheckResult, ...] = Field(min_length=14, max_length=14)
    axis_results: tuple[ReferencePhase6AxisResult, ...] = Field(min_length=8, max_length=8)
    resource_receipt: ReferencePhase6ResourceReceipt
    all_nonperformance_checks_pass: bool
    canonical_performance_status: Literal["passed", "failed", "pending-canonical-environment"]
    selection_validation_or_confirmatory_authority: Literal[False]
    leap_behavior_present: Literal[False]
    report_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_report(self) -> ReferencePhase6AcceptanceReport:
        if tuple(item.check_id for item in self.checks) != REFERENCE_PHASE6_CHECK_IDS:
            raise ValueError("Reference Phase 6 checks are incomplete or unordered")
        if tuple(item.axis for item in self.axis_results) != REFERENCE_PHASE6_AXIS_IDS:
            raise ValueError("Reference Phase 6 axes are incomplete or unordered")
        if self.all_nonperformance_checks_pass != all(item.passed for item in self.checks):
            raise ValueError("Reference Phase 6 aggregate check status is inconsistent")
        if self.canonical_performance_status != self.resource_receipt.canonical_gate_status:
            raise ValueError("Reference Phase 6 performance status disagrees with its receipt")
        if model_digest(self, digest_field="report_digest") != self.report_digest:
            raise ValueError("Reference Phase 6 acceptance report digest is invalid")
        return self
