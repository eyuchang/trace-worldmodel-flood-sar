"""Logical-authority evidence-delivery contracts for Reference."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel


class ReferenceCoordinationDelivery(DeltaModel):
    delivery_id: str = Field(pattern=r"^CD-[0-9a-f]{16}$")
    evidence_kind: Literal["public-report-envelope", "resource-telemetry"]
    evidence_id: str = Field(pattern=r"^(RE|RT)-[0-9a-f]{16}$")
    source_authority_id: Literal["AUTH-01", "AUTH-02", "AUTH-03", "AUTH-04"]
    recipient_authority_id: Literal["AUTH-01", "AUTH-02", "AUTH-03", "AUTH-04"]
    recipient_partition_id: str = Field(pattern=r"^AUTH-0[1-4]-P[0-9]{2}$")
    source_available_at_s: int = Field(ge=-172_800, le=352_800)
    delivered_at_s: int = Field(ge=-172_800, le=359_999)
    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_delivery_time(self) -> ReferenceCoordinationDelivery:
        if self.delivered_at_s < self.source_available_at_s:
            raise ValueError("Reference coordination delivery cannot precede source evidence")
        return self


class ReferencePublicCoordinationScenario(DeltaModel):
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    schema_version: Literal["delta-reference-coordination-v1"]
    seed: int = Field(ge=0)
    phi: int = Field(ge=1, le=9)
    authority_registry_version: Literal["delta-reference-governance-v1"]
    deliveries: tuple[ReferenceCoordinationDelivery, ...]
    public_coordination_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_order_and_ids(self) -> ReferencePublicCoordinationScenario:
        ordered = tuple(
            sorted(self.deliveries, key=lambda item: (item.delivered_at_s, item.delivery_id))
        )
        if self.deliveries != ordered:
            raise ValueError("Reference coordination deliveries must be canonically ordered")
        ids = tuple(item.delivery_id for item in self.deliveries)
        if len(set(ids)) != len(ids):
            raise ValueError("Reference coordination delivery identifiers must be unique")
        return self


class ReferenceCoordinationAttemptAudit(DeltaModel):
    attempt_id: str = Field(pattern=r"^CA-[0-9a-f]{16}$")
    evidence_kind: Literal["public-report-envelope", "resource-telemetry"]
    evidence_id: str = Field(pattern=r"^(RE|RT)-[0-9a-f]{16}$")
    source_authority_id: Literal["AUTH-01", "AUTH-02", "AUTH-03", "AUTH-04"]
    recipient_authority_id: Literal["AUTH-01", "AUTH-02", "AUTH-03", "AUTH-04"]
    recipient_partition_id: str = Field(pattern=r"^AUTH-0[1-4]-P[0-9]{2}$")
    source_available_at_s: int = Field(ge=-172_800, le=352_800)
    latency_s: int = Field(ge=0, le=7_200)
    disposition: Literal["delivered", "lost-before-delivery"]
    delivered_public_id: str | None = Field(default=None, pattern=r"^CD-[0-9a-f]{16}$")

    @model_validator(mode="after")
    def validate_disposition(self) -> ReferenceCoordinationAttemptAudit:
        delivered = self.disposition == "delivered"
        if delivered != (self.delivered_public_id is not None):
            raise ValueError("Reference coordination disposition and public ID disagree")
        return self


class ReferenceHiddenCoordinationAudit(DeltaModel):
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    schema_version: Literal["delta-reference-coordination-audit-v1"]
    seed: int = Field(ge=0)
    phi: int = Field(ge=1, le=9)
    attempts: tuple[ReferenceCoordinationAttemptAudit, ...]
    hidden_coordination_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReferenceCoordinationArtifacts(DeltaModel):
    public: ReferencePublicCoordinationScenario
    hidden: ReferenceHiddenCoordinationAudit

    @model_validator(mode="after")
    def validate_public_audit_join(self) -> ReferenceCoordinationArtifacts:
        delivered = {
            item.delivered_public_id
            for item in self.hidden.attempts
            if item.delivered_public_id is not None
        }
        if delivered != {item.delivery_id for item in self.public.deliveries}:
            raise ValueError("Reference coordination public/audit deliveries do not join")
        return self
