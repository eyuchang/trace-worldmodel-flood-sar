"""Typed deterministic artifact and replay contracts for Reference development."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel
from trace_jepa.support import canonical_json_bytes


class ReferenceArtifactDescriptor(DeltaModel):
    """One bounded canonical file in a Reference replay bundle."""

    name: str = Field(min_length=1, max_length=80)
    file_name: str = Field(pattern=r"^[a-z][a-z0-9_]*\.json$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_length: int = Field(ge=0, le=128 * 1024 * 1024)
    contains_hidden_truth: bool


class ReferenceFileInput(DeltaModel):
    """One caller-rooted file that directly controls Reference generation."""

    name: str = Field(min_length=1, max_length=100)
    repository_relative_path: str = Field(min_length=1, max_length=240)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_length: int = Field(ge=1, le=256 * 1024 * 1024)


class ReferenceValueInput(DeltaModel):
    """One canonical non-file input, such as predictor or protocol identity."""

    name: str = Field(min_length=1, max_length=100)
    identifier: str = Field(min_length=1, max_length=160)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReferenceReplayManifest(DeltaModel):
    """Deterministic development manifest; execution metadata is kept separate."""

    schema_version: Literal["delta-reference-replay-manifest-v1"]
    scientific_status: Literal["development-only-not-validation-evidence"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    generator_version: Literal["delta-reference-generator-v3"]
    seed: int = Field(ge=0)
    randomness_namespace: Literal["delta-reference-randomness-v1"]
    generation_order: tuple[str, ...]
    scenario_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_profile_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_event_prefix_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    trace_prefix_digest: str = Field(pattern=r"^(GENESIS|[0-9a-f]{64})$")
    evidence_prefix_digest: str = Field(pattern=r"^(GENESIS|[0-9a-f]{64})$")
    commitment_prefix_digest: str = Field(pattern=r"^(GENESIS|[0-9a-f]{64})$")
    source_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    file_inputs: tuple[ReferenceFileInput, ...]
    value_inputs: tuple[ReferenceValueInput, ...]
    artifacts: tuple[ReferenceArtifactDescriptor, ...]
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_canonical_inventory(self) -> ReferenceReplayManifest:
        file_paths = tuple(item.repository_relative_path for item in self.file_inputs)
        if file_paths != tuple(sorted(file_paths)) or len(set(file_paths)) != len(file_paths):
            raise ValueError("Reference file inputs must be unique and canonically ordered")
        artifact_names = tuple(item.name for item in self.artifacts)
        artifact_files = tuple(item.file_name for item in self.artifacts)
        if artifact_names != tuple(sorted(artifact_names)):
            raise ValueError("Reference artifact descriptors must be name-ordered")
        if len(set(artifact_names)) != len(artifact_names) or len(set(artifact_files)) != len(
            artifact_files
        ):
            raise ValueError("Reference artifact descriptor identity is duplicated")
        value_names = tuple(item.name for item in self.value_inputs)
        if value_names != tuple(sorted(value_names)) or len(set(value_names)) != len(value_names):
            raise ValueError("Reference value inputs must be unique and canonically ordered")
        if sum(item.byte_length for item in self.artifacts) > 512 * 1024 * 1024:
            raise ValueError("Reference replay bundle exceeds its registered size bound")
        body = self.model_dump(mode="json", exclude={"manifest_digest"})
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != self.manifest_digest:
            raise ValueError("Reference replay manifest digest is invalid")
        return self


class ReferenceResultSummary(DeltaModel):
    """Aggregate development result without hidden entity identifiers."""

    schema_version: Literal["delta-reference-result-summary-v1"]
    scientific_status: Literal["development-descriptive-not-validation-evidence"]
    seed: int = Field(ge=0)
    report_count: int = Field(ge=0)
    evaluation_report_count: int = Field(ge=0)
    truth_incident_count: int = Field(ge=0)
    evaluation_truth_incident_count: int = Field(ge=0)
    decision_count: int = Field(ge=0)
    allocation_count: int = Field(ge=0)
    refusal_count: int = Field(ge=0)
    outcome_count: int = Field(ge=0)
    compensation_count: int = Field(ge=0)
    consistency_debt_count: int = Field(ge=0)
    peak_finite_strict_concurrent_load_ratio_milli: int = Field(ge=0)
    strict_unserviceable_window_count: int = Field(ge=0, le=384)
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_digest(self) -> ReferenceResultSummary:
        body = self.model_dump(mode="json", exclude={"result_digest"})
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != self.result_digest:
            raise ValueError("Reference result summary digest is invalid")
        return self
