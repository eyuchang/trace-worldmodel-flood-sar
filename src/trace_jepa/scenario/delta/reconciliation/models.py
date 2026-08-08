"""Typed, controller-visible reconciliation graph contracts."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain import DeltaModel
from trace_jepa.scenario.delta.domain.types import ReconciliationLinkStatus


class ReconciliationLink(DeltaModel):
    link_id: str
    source_call_id: str
    target_call_id: str
    status: ReconciliationLinkStatus
    evidence_families: tuple[str, ...]
    reason: str
    supersedes_link_id: str | None = None

    @model_validator(mode="after")
    def validate_status(self) -> ReconciliationLink:
        if self.status not in {"confirmed", "suspected", "rejected", "superseded"}:
            raise ValueError("unknown reconciliation link status")
        if self.status == "superseded" and self.supersedes_link_id is None:
            raise ValueError("superseded links must identify the replaced link")
        return self


class ReconciliationNode(DeltaModel):
    call_id: str
    controller_available_s: int = Field(ge=0)
    belief_cluster_id: str


class ReconciliationArtifact(DeltaModel):
    schema_version: str = "delta-reconciliation-v3"
    algorithm_id: str
    hidden_lineage_used: bool = False
    nodes: tuple[ReconciliationNode, ...]
    links: tuple[ReconciliationLink, ...]
    cluster_by_call: dict[str, str]


@dataclass(frozen=True)
class ReconciliationStep:
    belief_cluster_id: str
    confirmed_link: ReconciliationLink | None
    emitted_links: tuple[ReconciliationLink, ...]

    @property
    def visible_evidence_basis(self) -> tuple[str, ...]:
        if self.confirmed_link is None:
            return ()
        return (*self.confirmed_link.evidence_families, self.confirmed_link.target_call_id)
