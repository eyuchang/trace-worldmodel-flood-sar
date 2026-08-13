"""Generate deterministic, lossy evidence sharing among logical authorities."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from trace_jepa.support import canonical_json_bytes
from trace_reference.domain.coordination import (
    ReferenceActivationParameters,
    ReferenceCoordinationArtifacts,
    ReferenceCoordinationAttemptAudit,
    ReferenceCoordinationDelivery,
    ReferenceHiddenCoordinationAudit,
    ReferencePublicCoordinationScenario,
    ReferenceResourceActivationEvent,
    ReferenceResourceActivationPhase,
    ReferenceResourceActivationSchedule,
)
from trace_reference.domain.observations import (
    ReferenceAuthorityId,
    ReferenceDeliveryEnvelopeScenario,
)
from trace_reference.domain.resources import (
    ReferencePublicResourceTelemetryScenario,
    ReferenceResourceArtifacts,
    ReferenceResourceState,
)
from trace_reference.models import ReferenceGovernanceRegistry

from .randomness import uniform_micros

_NAMESPACE = "reference-coordination-v2"

_PHASE_STATE = {
    ReferenceResourceActivationPhase.REQUESTED: ReferenceResourceState.AWAITING_REQUEST,
    ReferenceResourceActivationPhase.APPROVED: ReferenceResourceState.ACTIVATION_APPROVED,
    ReferenceResourceActivationPhase.MOBILIZED: ReferenceResourceState.MOBILIZING,
    ReferenceResourceActivationPhase.STAGED: ReferenceResourceState.IN_TRANSIT,
    ReferenceResourceActivationPhase.ARRIVED: (
        ReferenceResourceState.ARRIVED_AWAITING_AVAILABILITY
    ),
    ReferenceResourceActivationPhase.AVAILABLE: ReferenceResourceState.AVAILABLE_STAGED,
}


@dataclass(frozen=True)
class _Evidence:
    kind: Literal["public-report-envelope", "resource-telemetry"]
    evidence_id: str
    source_authority_id: ReferenceAuthorityId
    available_at_s: int
    content_digest: str


def _id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256("|".join(str(item) for item in parts).encode()).hexdigest()
    return f"{prefix}-{digest[:16]}"


def _public_evidence(
    report_envelopes: ReferenceDeliveryEnvelopeScenario,
    resource_telemetry: ReferencePublicResourceTelemetryScenario,
) -> tuple[_Evidence, ...]:
    reports = (
        _Evidence(
            kind="public-report-envelope",
            evidence_id=item.envelope_id,
            source_authority_id=item.initial_authority_id,
            available_at_s=item.delivered_at_s,
            content_digest=hashlib.sha256(
                canonical_json_bytes(item.model_dump(mode="json"))
            ).hexdigest(),
        )
        for item in report_envelopes.envelopes
    )
    telemetry = (
        _Evidence(
            kind="resource-telemetry",
            evidence_id=item.telemetry_id,
            source_authority_id=item.owning_authority_id,
            available_at_s=item.delivered_at_s,
            content_digest=hashlib.sha256(
                canonical_json_bytes(item.model_dump(mode="json"))
            ).hexdigest(),
        )
        for item in resource_telemetry.telemetry
    )
    return tuple(
        sorted((*reports, *telemetry), key=lambda item: (item.available_at_s, item.evidence_id))
    )


def _partition_id(authority_id: ReferenceAuthorityId, evidence_id: str, phi: int) -> str:
    partitions_for_role = max(1, (phi + 3) // 4)
    partition = int(hashlib.sha256(evidence_id.encode()).hexdigest()[:8], 16) % partitions_for_role
    return f"{authority_id}-P{partition + 1:02d}"


def _cross_role_latency(
    parameters: ReferenceActivationParameters,
    *,
    seed: int,
    phi: int,
    source: ReferenceAuthorityId,
    recipient: ReferenceAuthorityId,
    key: tuple[object, ...],
) -> int:
    if phi == 1 or source == recipient:
        return 0
    limit = min(7_200, parameters.cross_role_latency_limit_s_per_phi * phi)
    return uniform_micros(seed, _NAMESPACE, *key, "activation-latency") % (limit + 1)


def _first_available_time(
    resources: ReferenceResourceArtifacts,
    *,
    resource_id: str,
    arrived_at_s: int,
) -> int | None:
    return next(
        (
            item.at_s
            for item in resources.hidden.state_samples
            if item.resource_id == resource_id
            and item.at_s >= arrived_at_s
            and item.crew_on_duty
            and item.state != ReferenceResourceState.INITIAL_OUTAGE
        ),
        None,
    )


def _activation_schedule(
    resources: ReferenceResourceArtifacts,
    parameters: ReferenceActivationParameters,
    *,
    seed: int,
    phi: int,
) -> ReferenceResourceActivationSchedule:
    recipients: tuple[ReferenceAuthorityId, ...] = (
        ("AUTH-01",) if phi == 1 else ("AUTH-01", "AUTH-02", "AUTH-03", "AUTH-04")
    )
    events: list[ReferenceResourceActivationEvent] = []
    requester: ReferenceAuthorityId = parameters.requesting_authority_id
    for resource in resources.hidden.resources:
        approver: ReferenceAuthorityId = resource.owning_authority_id
        requested_at_s = parameters.tier_request_anchor_s[resource.tier]
        approval_latency_s = _cross_role_latency(
            parameters,
            seed=seed,
            phi=phi,
            source=requester,
            recipient=approver,
            key=(resource.resource_id, "approval"),
        )
        approved_at_s = requested_at_s + approval_latency_s
        mobilized_at_s = approved_at_s + resource.activation_delay_s
        staged_at_s = mobilized_at_s + resource.staging_delay_s
        arrived_at_s = staged_at_s + resource.nominal_travel_s
        available_at_s = _first_available_time(
            resources,
            resource_id=resource.resource_id,
            arrived_at_s=arrived_at_s,
        )
        phase_times = [
            (ReferenceResourceActivationPhase.REQUESTED, requested_at_s),
            (ReferenceResourceActivationPhase.APPROVED, approved_at_s),
            (ReferenceResourceActivationPhase.MOBILIZED, mobilized_at_s),
            (ReferenceResourceActivationPhase.STAGED, staged_at_s),
            (ReferenceResourceActivationPhase.ARRIVED, arrived_at_s),
        ]
        if available_at_s is not None:
            phase_times.append((ReferenceResourceActivationPhase.AVAILABLE, available_at_s))
        activation_id = _id("RMA", seed, resource.resource_id)
        predecessor_by_recipient: dict[ReferenceAuthorityId, str] = {}
        predecessor_delivery_by_recipient: dict[ReferenceAuthorityId, int] = {}
        for phase, observed_at_s in phase_times:
            source = requester if phase == ReferenceResourceActivationPhase.REQUESTED else approver
            for recipient in recipients:
                latency_s = _cross_role_latency(
                    parameters,
                    seed=seed,
                    phi=phi,
                    source=source,
                    recipient=recipient,
                    key=(resource.resource_id, phase.value, recipient),
                )
                delivered_at_s = max(
                    observed_at_s + latency_s,
                    predecessor_delivery_by_recipient.get(recipient, -172_801) + 1,
                )
                event_id = _id("RME", seed, resource.resource_id, phase.value, recipient)
                event_body = {
                    "schema_version": "delta-reference-resource-activation-event-v1",
                    "event_id": event_id,
                    "activation_id": activation_id,
                    "resource_id": resource.resource_id,
                    "tier": resource.tier.value,
                    "phase": phase.value,
                    "observed_at_s": observed_at_s,
                    "delivered_at_s": delivered_at_s,
                    "requesting_authority_id": requester,
                    "approving_authority_id": approver,
                    "recipient_authority_id": recipient,
                    "reported_state": _PHASE_STATE[phase].value,
                    "predecessor_event_id": predecessor_by_recipient.get(recipient),
                }
                event = ReferenceResourceActivationEvent(
                    **event_body,
                    event_digest=hashlib.sha256(canonical_json_bytes(event_body)).hexdigest(),
                )
                events.append(event)
                predecessor_by_recipient[recipient] = event.event_id
                predecessor_delivery_by_recipient[recipient] = event.delivered_at_s
    events.sort(key=lambda item: (item.delivered_at_s, item.event_id))
    schedule_body: dict[str, object] = {
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "schema_version": "delta-reference-resource-activation-schedule-v1",
        "parameter_version": parameters.parameter_version,
        "scientific_status": parameters.scientific_status,
        "resource_catalog_digest": resources.public_catalog.resource_catalog_digest,
        "seed": seed,
        "phi": phi,
        "events": [item.model_dump(mode="json") for item in events],
    }
    return ReferenceResourceActivationSchedule(
        **schedule_body,
        schedule_digest=hashlib.sha256(canonical_json_bytes(schedule_body)).hexdigest(),
    )


def generate_reference_coordination(
    report_envelopes: ReferenceDeliveryEnvelopeScenario,
    resources: ReferenceResourceArtifacts,
    governance: ReferenceGovernanceRegistry,
    activation_parameters: ReferenceActivationParameters,
    *,
    seed: int,
    phi: int = 4,
) -> ReferenceCoordinationArtifacts:
    """Route public evidence without exposing either hidden lineage or resource truth."""

    if not 1 <= phi <= 9:
        raise ValueError("Reference phi is outside the registered range")
    authorities = tuple(item.authority_id for item in governance.authorities)
    if authorities != ("AUTH-01", "AUTH-02", "AUTH-03", "AUTH-04"):
        raise ValueError("Reference governance must bind the four approved logical roles")
    active_authorities: tuple[ReferenceAuthorityId, ...] = ("AUTH-01",) if phi == 1 else authorities
    deliveries: list[ReferenceCoordinationDelivery] = []
    attempts: list[ReferenceCoordinationAttemptAudit] = []
    for evidence in _public_evidence(report_envelopes, resources.public):
        for recipient in active_authorities:
            partition_id = _partition_id(recipient, evidence.evidence_id, phi)
            local = recipient == evidence.source_authority_id or phi == 1
            semantic_key = (evidence.evidence_id, recipient)
            identity_key = (*semantic_key, partition_id)
            latency_draw_micros = uniform_micros(
                seed,
                _NAMESPACE,
                *semantic_key,
                "latency",
            )
            loss_draw_micros = uniform_micros(
                seed,
                _NAMESPACE,
                *semantic_key,
                "loss",
            )
            latency_limit = 0 if local else min(7_200, 300 * phi)
            latency = 0 if latency_limit == 0 else latency_draw_micros % (latency_limit + 1)
            loss_probability = 0 if local else min(300_000, 20_000 * phi)
            lost = not local and loss_draw_micros < loss_probability
            attempt_id = _id("CA", seed, *identity_key)
            delivery_id = None if lost else _id("CD", seed, *identity_key)
            attempts.append(
                ReferenceCoordinationAttemptAudit(
                    attempt_id=attempt_id,
                    evidence_kind=evidence.kind,
                    evidence_id=evidence.evidence_id,
                    source_authority_id=evidence.source_authority_id,
                    recipient_authority_id=recipient,
                    recipient_partition_id=partition_id,
                    source_available_at_s=evidence.available_at_s,
                    latency_draw_micros=latency_draw_micros,
                    loss_draw_micros=loss_draw_micros,
                    latency_s=latency,
                    disposition="lost-before-delivery" if lost else "delivered",
                    delivered_public_id=delivery_id,
                )
            )
            if delivery_id is not None:
                deliveries.append(
                    ReferenceCoordinationDelivery(
                        delivery_id=delivery_id,
                        evidence_kind=evidence.kind,
                        evidence_id=evidence.evidence_id,
                        source_authority_id=evidence.source_authority_id,
                        recipient_authority_id=recipient,
                        recipient_partition_id=partition_id,
                        source_available_at_s=evidence.available_at_s,
                        delivered_at_s=evidence.available_at_s + latency,
                        source_content_digest=evidence.content_digest,
                    )
                )
    deliveries.sort(key=lambda item: (item.delivered_at_s, item.delivery_id))
    attempts.sort(key=lambda item: item.attempt_id)
    public_body = {
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "schema_version": "delta-reference-coordination-v2",
        "seed": seed,
        "phi": phi,
        "authority_registry_version": governance.registry_version,
        "deliveries": [item.model_dump(mode="json") for item in deliveries],
    }
    hidden_body = {
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "schema_version": "delta-reference-coordination-audit-v2",
        "seed": seed,
        "phi": phi,
        "attempts": [item.model_dump(mode="json") for item in attempts],
    }
    return ReferenceCoordinationArtifacts(
        public=ReferencePublicCoordinationScenario(
            **public_body,
            public_coordination_digest=hashlib.sha256(
                canonical_json_bytes(public_body)
            ).hexdigest(),
        ),
        hidden=ReferenceHiddenCoordinationAudit(
            **hidden_body,
            hidden_coordination_digest=hashlib.sha256(
                canonical_json_bytes(hidden_body)
            ).hexdigest(),
        ),
        activations=_activation_schedule(
            resources,
            activation_parameters,
            seed=seed,
            phi=phi,
        ),
    )
