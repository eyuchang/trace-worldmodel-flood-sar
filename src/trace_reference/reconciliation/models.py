"""Typed public-only evidence-graph artifacts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel


class ReferenceReconciliationLink(DeltaModel):
    schema_version: Literal["delta-reference-reconciliation-link-v1"]
    link_id: str = Field(pattern=r"^RRL-[0-9a-f]{16}$")
    source_call_id: str = Field(pattern=r"^RC-[0-9a-f]{16}$")
    target_call_id: str = Field(pattern=r"^RC-[0-9a-f]{16}$")
    status: Literal["confirmed", "suspected", "rejected"]
    evidence_families: tuple[str, ...] = Field(min_length=1)
    decided_at_s: int = Field(ge=-172_800, le=359_999)
    link_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReferenceBeliefCluster(DeltaModel):
    cluster_id: str = Field(pattern=r"^RBC-[0-9a-f]{16}$")
    call_ids: tuple[str, ...] = Field(min_length=1)
    earliest_observed_at_s: int
    latest_observed_at_s: int

    @model_validator(mode="after")
    def validate_cluster(self) -> ReferenceBeliefCluster:
        if self.call_ids != tuple(sorted(set(self.call_ids))):
            raise ValueError("Reference belief-cluster calls must be unique and ordered")
        if self.earliest_observed_at_s > self.latest_observed_at_s:
            raise ValueError("Reference belief-cluster interval is invalid")
        return self


class ReferenceReconciliationStep(DeltaModel):
    call_id: str = Field(pattern=r"^RC-[0-9a-f]{16}$")
    controller_authority_id: Literal["AUTH-01", "AUTH-02", "AUTH-03", "AUTH-04"]
    belief_cluster_id: str = Field(pattern=r"^RBC-[0-9a-f]{16}$")
    relationship_status: Literal["new", "confirmed", "suspected"]
    visible_evidence_basis: tuple[str, ...]
    created_link_ids: tuple[str, ...]
    repaired_prior_belief: bool
    step_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReferenceReconciliationArtifact(DeltaModel):
    schema_version: Literal["delta-reference-reconciliation-v1"]
    algorithm_id: Literal["reference-visible-evidence-graph-q075-v1"]
    controller_authority_id: Literal["AUTH-01", "AUTH-02", "AUTH-03", "AUTH-04"]
    clusters: tuple[ReferenceBeliefCluster, ...]
    links: tuple[ReferenceReconciliationLink, ...]
    artifact_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
