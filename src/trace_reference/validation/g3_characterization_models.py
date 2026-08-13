"""Digest-bound feature-off characterization contracts for the G3 handoff."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal, TypeAlias

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel
from trace_reference.decision.canonical import model_digest

ReferenceG3FixtureId: TypeAlias = Literal[
    "nominal",
    "faulted-restart",
    "acquisition-success",
    "acquisition-timeout",
    "empty-catalog-fallback",
]
ReferenceG3ArtifactFamily: TypeAlias = Literal[
    "public-events",
    "decision-handoffs",
    "decision-costs",
    "trace-chain",
    "evidence-chain",
    "commitment-chain",
]
ReferenceG3RuntimeProfileId: TypeAlias = Literal[
    "reference-nominal-v1",
    "reference-faulted-v1",
]
ReferenceG3AcquisitionOutcomeStatus: TypeAlias = Literal[
    "evidence-accepted",
    "provider-timeout",
]
ReferenceG3FallbackDisposition: TypeAlias = Literal["hold"]


class ReferenceG3ArtifactFamilyDigest(DeltaModel):
    """Ordered aggregate binding every canonical member of one artifact family."""

    family: ReferenceG3ArtifactFamily
    member_count: int = Field(ge=0)
    canonical_byte_length: int = Field(ge=0)
    aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReferenceG3CharacterizationFixtureManifest(DeltaModel):
    """One feature-off base-Reference fixture without hidden/evaluator content."""

    schema_version: Literal["delta-reference-g3-characterization-fixture-v1"]
    scientific_status: Literal["development-characterization-not-validation-evidence"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    scenario_seed: int = Field(ge=0, le=2_147_483_647)
    fixture_id: ReferenceG3FixtureId
    runtime_profile_id: ReferenceG3RuntimeProfileId
    through_s: Literal[345600]
    selector_id: Literal["reference-base-selector-v1"]
    public_model_id: Literal["reference-public-one-step-model-v1"]
    decision_extension_id: None = None
    artifact_families: tuple[ReferenceG3ArtifactFamilyDigest, ...] = Field(min_length=1)
    acquisition_outcome_status: ReferenceG3AcquisitionOutcomeStatus | None
    physical_evidence_count: int = Field(ge=0)
    selected_catalog_bundle_count: int | None = Field(default=None, ge=0)
    fallback_disposition: ReferenceG3FallbackDisposition | None
    restart_public_state_equivalent: bool | None
    restart_durable_state_equivalent: bool | None
    leap_implementation_present: Literal[False]
    effectiveness_evidence_present: Literal[False]
    fixture_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_fixture(self) -> ReferenceG3CharacterizationFixtureManifest:
        families = tuple(item.family for item in self.artifact_families)
        expected_families: tuple[ReferenceG3ArtifactFamily, ...] = (
            "commitment-chain",
            "decision-costs",
            "decision-handoffs",
            "evidence-chain",
            "public-events",
            "trace-chain",
        )
        if families != expected_families:
            raise ValueError("Reference G3 fixture artifact families are incomplete or unordered")
        if self.fixture_id == "faulted-restart":
            if (
                not self.restart_public_state_equivalent
                or not self.restart_durable_state_equivalent
            ):
                raise ValueError("Reference fault/restart fixture must establish both equivalences")
        elif self.restart_public_state_equivalent is not None or (
            self.restart_durable_state_equivalent is not None
        ):
            raise ValueError(
                "Only the Reference fault/restart fixture declares restart equivalence"
            )
        if self.fixture_id == "acquisition-success" and (
            self.acquisition_outcome_status != "evidence-accepted"
            or self.physical_evidence_count != 1
        ):
            raise ValueError("Reference acquisition-success fixture is incomplete")
        if self.fixture_id == "acquisition-timeout" and (
            self.acquisition_outcome_status != "provider-timeout"
            or self.physical_evidence_count != 0
        ):
            raise ValueError("Reference acquisition-timeout fixture fabricated evidence")
        if self.fixture_id == "empty-catalog-fallback" and (
            self.selected_catalog_bundle_count != 0 or self.fallback_disposition != "hold"
        ):
            raise ValueError("Reference empty-catalog fixture did not fail closed")
        if self.fixture_id not in {"acquisition-success", "acquisition-timeout"} and (
            self.acquisition_outcome_status is not None or self.physical_evidence_count != 0
        ):
            raise ValueError("Non-acquisition Reference fixture declares acquisition evidence")
        if self.fixture_id != "empty-catalog-fallback" and (
            self.selected_catalog_bundle_count is not None or self.fallback_disposition is not None
        ):
            raise ValueError("Only the empty-catalog fixture declares fallback semantics")
        if model_digest(self, digest_field="fixture_digest") != self.fixture_digest:
            raise ValueError("Reference G3 fixture digest is invalid")
        return self


class ReferenceG3CharacterizationIndex(DeltaModel):
    """Canonical registry of the five required feature-off fixture manifests."""

    schema_version: Literal["delta-reference-g3-characterization-index-v1"]
    scientific_status: Literal["development-characterization-not-validation-evidence"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    scenario_seed: int = Field(ge=0, le=2_147_483_647)
    fixtures: tuple[ReferenceG3CharacterizationFixtureManifest, ...] = Field(
        min_length=5,
        max_length=5,
    )
    integrity_report_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    leap_implementation_present: Literal[False]
    effectiveness_evidence_present: Literal[False]
    index_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_index(self) -> ReferenceG3CharacterizationIndex:
        expected: tuple[ReferenceG3FixtureId, ...] = (
            "acquisition-success",
            "acquisition-timeout",
            "empty-catalog-fallback",
            "faulted-restart",
            "nominal",
        )
        if tuple(item.fixture_id for item in self.fixtures) != expected:
            raise ValueError("Reference G3 characterization fixtures are incomplete or unordered")
        if any(item.scenario_seed != self.scenario_seed for item in self.fixtures):
            raise ValueError("Reference G3 characterization mixes scenario seeds")
        if len({item.fixture_digest for item in self.fixtures}) != len(self.fixtures):
            raise ValueError("Reference G3 characterization fixture digests must be unique")
        if model_digest(self, digest_field="index_digest") != self.index_digest:
            raise ValueError("Reference G3 characterization index digest is invalid")
        return self


class ReferenceG3CharacterizationFileBinding(DeltaModel):
    """One compact generated characterization product and both of its bindings."""

    relative_path: str = Field(pattern=r"^[a-z0-9_./-]+\.(json|py)$")
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_relative_path(self) -> ReferenceG3CharacterizationFileBinding:
        path = PurePosixPath(self.relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Reference G3 characterization binding path is unsafe")
        return self


class ReferenceG3CharacterizationBenchmarkRun(DeltaModel):
    """Bounded local execution observation for deterministic development QA."""

    role: Literal[
        "pre-streaming-contract-test",
        "pre-streaming-independent-reproduction",
        "streaming-equivalence",
        "complete-timeout-reassessment",
    ]
    elapsed_milliseconds: int = Field(gt=0)
    transient_output_bytes: int = Field(gt=0, le=1_073_741_824)
    execution_succeeded: Literal[True]
    peak_memory_bytes: None = None
    memory_measurement_note: Literal["direct-peak-memory-unavailable-sandboxed-macos-sysctl"]


class ReferenceG3CharacterizationBenchmarkReceipt(DeltaModel):
    """Development-only evidence that the five fixture manifests reproduce exactly."""

    schema_version: Literal["delta-reference-g3-characterization-benchmark-v2"]
    scientific_status: Literal["development-characterization-not-validation-evidence"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    scenario_seed: int = Field(ge=0, le=2_147_483_647)
    runtime_base_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    execution_python: Literal["3.13.1"]
    pre_completion_characterization_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_files: tuple[ReferenceG3CharacterizationFileBinding, ...] = Field(
        min_length=4,
        max_length=4,
    )
    products: tuple[ReferenceG3CharacterizationFileBinding, ...] = Field(
        min_length=6,
        max_length=6,
    )
    runs: tuple[ReferenceG3CharacterizationBenchmarkRun, ...] = Field(
        min_length=4,
        max_length=4,
    )
    pre_completion_products_byte_identical: Literal[True]
    final_products_match_pre_completion: Literal[False]
    changed_product_reason: Literal["timeout-fixture-now-binds-required-post-outcome-reassessment"]
    receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_receipt(self) -> ReferenceG3CharacterizationBenchmarkReceipt:
        expected_roles = (
            "pre-streaming-contract-test",
            "pre-streaming-independent-reproduction",
            "streaming-equivalence",
            "complete-timeout-reassessment",
        )
        if tuple(item.role for item in self.runs) != expected_roles:
            raise ValueError("Reference G3 characterization benchmark roles are invalid")
        if len({item.relative_path for item in self.products}) != len(self.products):
            raise ValueError("Reference G3 characterization products must be unique")
        if tuple(item.relative_path for item in self.implementation_files) != tuple(
            sorted(item.relative_path for item in self.implementation_files)
        ):
            raise ValueError("Reference G3 implementation bindings must be ordered")
        if tuple(item.relative_path for item in self.products) != tuple(
            sorted(item.relative_path for item in self.products)
        ):
            raise ValueError("Reference G3 product bindings must be ordered")
        if model_digest(self, digest_field="receipt_digest") != self.receipt_digest:
            raise ValueError("Reference G3 characterization benchmark digest is invalid")
        return self
