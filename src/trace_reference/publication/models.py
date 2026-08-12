"""Typed deterministic manifest and result table for Reference publication output."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel
from trace_jepa.support import canonical_json_bytes


class ReferencePublicationArtifact(DeltaModel):
    name: str = Field(min_length=1, max_length=80)
    file_name: str = Field(pattern=r"^[a-z][a-z0-9_]*\.(svg|json)$")
    media_type: Literal["image/svg+xml", "application/json"]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_length: int = Field(ge=1, le=64 * 1024 * 1024)


class ReferencePublicationResultTable(DeltaModel):
    schema_version: Literal["delta-reference-publication-result-table-v1"]
    scientific_status: Literal["development-descriptive-not-validation-evidence"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    seed: int = Field(ge=0)
    report_count: int = Field(ge=0)
    evaluation_report_count: int = Field(ge=0)
    truth_incident_count: int = Field(ge=0)
    evaluation_truth_incident_count: int = Field(ge=0)
    decision_count: int = Field(ge=0)
    allocation_count: int = Field(ge=0)
    refusal_count: int = Field(ge=0)
    acquisition_request_count: int = Field(ge=0)
    completed_within_window_count: int = Field(ge=0)
    active_at_censoring_count: int = Field(ge=0)
    confirmed_visible_link_count: int = Field(ge=0)
    suspected_visible_link_count: int = Field(ge=0)
    peak_finite_strict_concurrent_load_ratio_milli: int = Field(ge=0)
    strict_unserviceable_window_count: int = Field(ge=0, le=384)
    peak_finite_uncapped_compatible_load_ratio_milli: int = Field(ge=0)
    peak_finite_historical_normalized_coverable_load_index_milli: int = Field(ge=0)
    peak_finite_residual_strict_pressure_ratio_milli: int = Field(ge=0)
    residual_unserviceable_window_count: int = Field(ge=0, le=384)
    table_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_table(self) -> ReferencePublicationResultTable:
        body = self.model_dump(mode="json", exclude={"table_digest"})
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != self.table_digest:
            raise ValueError("Reference publication result table digest is invalid")
        return self


class ReferencePublicationManifest(DeltaModel):
    schema_version: Literal["delta-reference-publication-manifest-v1"]
    scientific_status: Literal["development-descriptive-not-validation-evidence"]
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    source_replay_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_replay_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifacts: tuple[ReferencePublicationArtifact, ...]
    manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_manifest(self) -> ReferencePublicationManifest:
        names = tuple(item.name for item in self.artifacts)
        files = tuple(item.file_name for item in self.artifacts)
        if names != tuple(sorted(names)) or len(set(names)) != len(names):
            raise ValueError("Reference publication artifacts must be unique and name-ordered")
        if len(set(files)) != len(files):
            raise ValueError("Reference publication file name is duplicated")
        body = self.model_dump(mode="json", exclude={"manifest_digest"})
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != self.manifest_digest:
            raise ValueError("Reference publication manifest digest is invalid")
        return self
