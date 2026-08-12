"""Logical-authority evidence-delivery contracts for Reference."""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel
from trace_jepa.support import canonical_json_bytes

from .resources import ReferenceMutualAidTier, ReferenceResourceState


class ReferenceResourceActivationPhase(str, Enum):
    REQUESTED = "requested"
    APPROVED = "approved"
    MOBILIZED = "mobilized"
    STAGED = "staged"
    ARRIVED = "arrived"
    AVAILABLE = "available"


class ReferenceActivationParameters(DeltaModel):
    """Synthetic phase anchors and message-delay rule for resource activation."""

    parameter_version: Literal["delta-reference-activation-parameters-v1"]
    scientific_status: Literal["development-synthetic-role-workflow-not-legal-or-operational-claim"]
    requesting_authority_id: Literal["AUTH-01"]
    tier_request_anchor_s: dict[ReferenceMutualAidTier, int]
    cross_role_latency_limit_s_per_phi: int = Field(ge=60, le=1_800)
    limitations: tuple[str, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_tiers(self) -> ReferenceActivationParameters:
        if set(self.tier_request_anchor_s) != set(ReferenceMutualAidTier):
            raise ValueError("Reference activation anchors must cover T0 through T4")
        anchors = tuple(self.tier_request_anchor_s[item] for item in ReferenceMutualAidTier)
        if anchors != tuple(sorted(anchors)):
            raise ValueError("Reference activation anchors must be tier-monotone")
        if not all(-172_800 <= item <= 345_600 for item in anchors):
            raise ValueError("Reference activation anchor is outside the scenario window")
        return self


class ReferenceResourceActivationEvent(DeltaModel):
    """One controller-visible activation phase delivered to one logical role."""

    schema_version: Literal["delta-reference-resource-activation-event-v1"]
    event_id: str = Field(pattern=r"^RME-[0-9a-f]{16}$")
    activation_id: str = Field(pattern=r"^RMA-[0-9a-f]{16}$")
    resource_id: str = Field(pattern=r"^RR-[0-9a-f]{16}$")
    tier: ReferenceMutualAidTier
    phase: ReferenceResourceActivationPhase
    observed_at_s: int = Field(ge=-172_800, le=345_600)
    delivered_at_s: int = Field(ge=-172_800, le=359_999)
    requesting_authority_id: Literal["AUTH-01"]
    approving_authority_id: Literal["AUTH-01", "AUTH-02", "AUTH-03", "AUTH-04"]
    recipient_authority_id: Literal["AUTH-01", "AUTH-02", "AUTH-03", "AUTH-04"]
    reported_state: ReferenceResourceState
    predecessor_event_id: str | None = Field(
        default=None,
        pattern=r"^RME-[0-9a-f]{16}$",
    )
    event_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_delivery(self) -> ReferenceResourceActivationEvent:
        if self.delivered_at_s < self.observed_at_s:
            raise ValueError("Reference activation delivery cannot precede observation")
        first = self.phase == ReferenceResourceActivationPhase.REQUESTED
        if first == (self.predecessor_event_id is not None):
            raise ValueError("Reference activation predecessor binding is inconsistent")
        body = self.model_dump(mode="json", exclude={"event_digest"})
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != self.event_digest:
            raise ValueError("Reference activation event digest is invalid")
        return self


def _validate_activation_history(
    values: list[ReferenceResourceActivationEvent],
) -> None:
    phase_order = tuple(ReferenceResourceActivationPhase)
    by_phase = tuple(sorted(values, key=lambda item: phase_order.index(item.phase)))
    if tuple(item.phase for item in by_phase) != phase_order:
        raise ValueError("Reference activation recipient history is incomplete")
    observed = tuple(item.observed_at_s for item in by_phase)
    if observed != tuple(sorted(observed)):
        raise ValueError("Reference activation phase time moves backwards")
    delivered = tuple(item.delivered_at_s for item in by_phase)
    if delivered != tuple(sorted(delivered)):
        raise ValueError("Reference activation delivery precedes its predecessor")
    expected_predecessors = (None, *(item.event_id for item in by_phase[:-1]))
    if tuple(item.predecessor_event_id for item in by_phase) != expected_predecessors:
        raise ValueError("Reference activation predecessor chain is invalid")


def _validate_activation_audience(
    events: tuple[ReferenceResourceActivationEvent, ...],
    *,
    phi: int,
) -> None:
    recipient_count = 1 if phi == 1 else 4
    recipients_by_activation: dict[str, set[str]] = {}
    activation_ids_by_resource: dict[str, set[str]] = {}
    for event in events:
        recipients_by_activation.setdefault(event.activation_id, set()).add(
            event.recipient_authority_id
        )
        activation_ids_by_resource.setdefault(event.resource_id, set()).add(event.activation_id)
    if any(len(recipients) != recipient_count for recipients in recipients_by_activation.values()):
        raise ValueError("Reference activation audience does not match phi")
    if any(len(values) != 1 for values in activation_ids_by_resource.values()):
        raise ValueError("Reference resource has multiple activation identities")
    if len(recipients_by_activation) != len(activation_ids_by_resource):
        raise ValueError("Reference activation identity is reused across resources")


class ReferenceResourceActivationSchedule(DeltaModel):
    """Future-safe runtime input; phases enter controller state only when delivered."""

    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    schema_version: Literal["delta-reference-resource-activation-schedule-v1"]
    parameter_version: Literal["delta-reference-activation-parameters-v1"]
    scientific_status: Literal["development-synthetic-role-workflow-not-legal-or-operational-claim"]
    resource_catalog_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    seed: int = Field(ge=0)
    phi: int = Field(ge=1, le=9)
    events: tuple[ReferenceResourceActivationEvent, ...]
    schedule_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_events(self) -> ReferenceResourceActivationSchedule:
        ordered = tuple(sorted(self.events, key=lambda item: (item.delivered_at_s, item.event_id)))
        if self.events != ordered:
            raise ValueError("Reference activation events must use canonical delivery order")
        event_ids = tuple(item.event_id for item in self.events)
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("Reference activation event identifiers must be unique")
        grouped: dict[tuple[str, str], list[ReferenceResourceActivationEvent]] = {}
        for event in self.events:
            grouped.setdefault(
                (event.resource_id, event.recipient_authority_id),
                [],
            ).append(event)
        for values in grouped.values():
            _validate_activation_history(values)
        _validate_activation_audience(self.events, phi=self.phi)
        body = self.model_dump(mode="json", exclude={"schedule_digest"})
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != self.schedule_digest:
            raise ValueError("Reference activation schedule digest is invalid")
        return self


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
    activations: ReferenceResourceActivationSchedule

    @model_validator(mode="after")
    def validate_public_audit_join(self) -> ReferenceCoordinationArtifacts:
        delivered = {
            item.delivered_public_id
            for item in self.hidden.attempts
            if item.delivered_public_id is not None
        }
        if delivered != {item.delivery_id for item in self.public.deliveries}:
            raise ValueError("Reference coordination public/audit deliveries do not join")
        if (self.public.seed, self.public.phi) != (
            self.activations.seed,
            self.activations.phi,
        ):
            raise ValueError("Reference coordination and activation schedules disagree")
        return self
