"""Digest-bound contracts for the non-LEAP Reference G3 handoff gate."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel
from trace_reference.decision.canonical import model_digest

REFERENCE_G3_GATE_IDS = (
    "G3-PUB-001",
    "G3-PUB-002",
    "G3-PUB-003",
    "G3-PUB-004",
    "G3-ARCH-001",
    "G3-ARCH-002",
    "G3-PROP-001",
    "G3-ADEQ-001",
    "G3-ADEQ-002",
    "G3-ADEQ-003",
    "G3-ADEQ-004",
    "G3-AUTH-001",
    "G3-SAFE-001",
    "G3-BUNDLE-001",
    "G3-BUNDLE-002",
    "G3-BUNDLE-003",
    "G3-BUNDLE-004",
    "G3-BUNDLE-005",
    "G3-ACQ-001",
    "G3-ACQ-002",
    "G3-ACQ-003",
    "G3-TIME-001",
    "G3-TIME-002",
    "G3-COMMIT-001",
    "G3-COMMIT-002",
    "G3-CONCUR-001",
    "G3-COST-001",
    "G3-COST-002",
    "G3-COST-003",
    "G3-MODEL-001",
    "G3-MODEL-002",
    "G3-MODEL-003",
    "G3-MODEL-004",
    "G3-REPLAY-001",
    "G3-REPLAY-002",
    "G3-TAMPER-001",
    "G3-SEC-001",
    "G3-SEC-002",
    "G3-OFFLINE-001",
    "G3-SMALL-001",
    "G3-CHAR-001",
)


class ReferenceG3TestGate(DeltaModel):
    """One exact ADR gate and the tests that establish it."""

    gate_id: str = Field(pattern=r"^G3-[A-Z]+-[0-9]{3}$")
    test_node_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_nodes(self) -> ReferenceG3TestGate:
        if len(set(self.test_node_ids)) != len(self.test_node_ids):
            raise ValueError("Reference G3 test node IDs must be unique")
        for node_id in self.test_node_ids:
            path = PurePosixPath(node_id.split("::", maxsplit=1)[0])
            if path.is_absolute() or ".." in path.parts or path.suffix != ".py":
                raise ValueError("Reference G3 test node ID contains an unsafe source path")
            if not path.as_posix().startswith("tests/"):
                raise ValueError("Reference G3 test node ID must name a repository test")
        return self


class ReferenceG3AcceptanceRegistry(DeltaModel):
    """The complete set of the corrected ADR's 41 engineering gates."""

    registry_version: Literal["delta-reference-g3-acceptance-registry-v1"]
    adr_sha256: Literal["2af2b3b9e24040cb7fa0efa146b6e5cc9a3ad0805e53050494888a095b54403d"]
    gates: tuple[ReferenceG3TestGate, ...] = Field(min_length=41, max_length=41)

    @model_validator(mode="after")
    def validate_gates(self) -> ReferenceG3AcceptanceRegistry:
        gate_ids = tuple(item.gate_id for item in self.gates)
        if gate_ids != REFERENCE_G3_GATE_IDS:
            raise ValueError("Reference G3 gates must exactly follow the corrected ADR")
        return self


class ReferenceG3FileBinding(DeltaModel):
    """One trusted repository file bound by relative path, length, and digest."""

    relative_path: str = Field(min_length=1, max_length=300)
    byte_length: int = Field(gt=0, le=268_435_456)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_path(self) -> ReferenceG3FileBinding:
        path = PurePosixPath(self.relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Reference G3 file binding path is unsafe")
        return self


class ReferenceG3GateResult(DeltaModel):
    """Deterministic pass binding for one gate's exact test sources and node IDs."""

    gate_id: str = Field(pattern=r"^G3-[A-Z]+-[0-9]{3}$")
    test_node_ids: tuple[str, ...] = Field(min_length=1)
    test_source_aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: Literal["passed"]
    passing_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_result(self) -> ReferenceG3GateResult:
        if model_digest(self, digest_field="passing_result_sha256") != (self.passing_result_sha256):
            raise ValueError("Reference G3 passing-result digest is invalid")
        return self


class ReferenceG3AcceptanceReceipt(DeltaModel):
    """Canonical local engineering receipt produced only after every gate passes."""

    schema_version: Literal["delta-reference-g3-acceptance-receipt-v1"]
    scientific_status: Literal["development-engineering-gate-not-validation-evidence"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    registry: ReferenceG3FileBinding
    test_sources: tuple[ReferenceG3FileBinding, ...] = Field(min_length=1)
    gate_results: tuple[ReferenceG3GateResult, ...] = Field(min_length=41, max_length=41)
    all_gates_pass: Literal[True]
    execution_python: str = Field(pattern=r"^3\.[0-9]+\.[0-9]+$")
    receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_receipt(self) -> ReferenceG3AcceptanceReceipt:
        source_paths = tuple(item.relative_path for item in self.test_sources)
        if source_paths != tuple(sorted(set(source_paths))):
            raise ValueError("Reference G3 test-source bindings must be unique and ordered")
        gate_ids = tuple(item.gate_id for item in self.gate_results)
        if gate_ids != REFERENCE_G3_GATE_IDS:
            raise ValueError("Reference G3 passing results do not cover the corrected ADR")
        if model_digest(self, digest_field="receipt_digest") != self.receipt_digest:
            raise ValueError("Reference G3 acceptance-receipt digest is invalid")
        return self


class ReferenceG3ComponentBinding(DeltaModel):
    """Version and source identity for one stable G3 component."""

    component: Literal["base-selector", "public-model", "physical-channel", "cost-ledger"]
    version: str = Field(min_length=3, max_length=100)
    source: ReferenceG3FileBinding


class ReferenceG3HandoffManifest(DeltaModel):
    """Final non-LEAP G3 gate passed to later base-Reference validation."""

    schema_version: Literal["delta-reference-g3-handoff-manifest-v1"]
    scientific_status: Literal["development-engineering-gate-not-validation-evidence"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    adr_version: Literal["reference-leap-handoff-adr-v2"]
    adr: ReferenceG3FileBinding
    mechanism_identity_audit: ReferenceG3FileBinding
    scientific_input_manifest: ReferenceG3FileBinding
    scientific_input_aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scientific_input_member_count: int = Field(gt=0)
    public_schema_versions: tuple[str, ...] = Field(min_length=8)
    components: tuple[ReferenceG3ComponentBinding, ...] = Field(min_length=4, max_length=4)
    acceptance_registry: ReferenceG3FileBinding
    acceptance_receipt: ReferenceG3FileBinding
    acceptance_receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    characterization_index: ReferenceG3FileBinding
    characterization_index_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    characterization_fixtures: tuple[ReferenceG3FileBinding, ...] = Field(
        min_length=5, max_length=5
    )
    small_baseline_registry: ReferenceG3FileBinding
    small_baseline_source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    small_baseline_verified_file_count: int = Field(gt=0)
    environment_contract: ReferenceG3FileBinding
    dependency_lock: ReferenceG3FileBinding
    leap_implementation_present: Literal[False]
    effectiveness_evidence_present: Literal[False]
    g3_ready: Literal[True]
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_manifest(self) -> ReferenceG3HandoffManifest:
        expected_components = (
            "base-selector",
            "cost-ledger",
            "physical-channel",
            "public-model",
        )
        if tuple(item.component for item in self.components) != expected_components:
            raise ValueError("Reference G3 component bindings are incomplete or unordered")
        if self.public_schema_versions != tuple(sorted(set(self.public_schema_versions))):
            raise ValueError("Reference G3 public schemas must be unique and ordered")
        fixture_paths = tuple(item.relative_path for item in self.characterization_fixtures)
        if fixture_paths != tuple(sorted(set(fixture_paths))):
            raise ValueError("Reference G3 fixture bindings must be unique and ordered")
        if model_digest(self, digest_field="manifest_digest") != self.manifest_digest:
            raise ValueError("Reference G3 handoff-manifest digest is invalid")
        return self
