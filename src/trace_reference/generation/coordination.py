"""Generate deterministic, lossy evidence sharing among logical authorities."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from trace_jepa.support import canonical_json_bytes
from trace_reference.domain.coordination import (
    ReferenceCoordinationArtifacts,
    ReferenceCoordinationAttemptAudit,
    ReferenceCoordinationDelivery,
    ReferenceHiddenCoordinationAudit,
    ReferencePublicCoordinationScenario,
)
from trace_reference.domain.observations import (
    ReferenceAuthorityId,
    ReferenceDeliveryEnvelopeScenario,
)
from trace_reference.domain.resources import ReferencePublicResourceTelemetryScenario
from trace_reference.models import ReferenceGovernanceRegistry

from .randomness import uniform_micros

_NAMESPACE = "reference-coordination-v1"


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


def generate_reference_coordination(
    report_envelopes: ReferenceDeliveryEnvelopeScenario,
    resource_telemetry: ReferencePublicResourceTelemetryScenario,
    governance: ReferenceGovernanceRegistry,
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
    for evidence in _public_evidence(report_envelopes, resource_telemetry):
        for recipient in active_authorities:
            partition_id = _partition_id(recipient, evidence.evidence_id, phi)
            local = recipient == evidence.source_authority_id or phi == 1
            key = (evidence.evidence_id, recipient, partition_id)
            latency_limit = 0 if local else min(7_200, 300 * phi)
            latency = (
                0
                if latency_limit == 0
                else uniform_micros(seed, _NAMESPACE, *key, "latency") % (latency_limit + 1)
            )
            loss_probability = 0 if local else min(300_000, 20_000 * phi)
            lost = not local and uniform_micros(seed, _NAMESPACE, *key, "loss") < loss_probability
            attempt_id = _id("CA", seed, *key)
            delivery_id = None if lost else _id("CD", seed, *key)
            attempts.append(
                ReferenceCoordinationAttemptAudit(
                    attempt_id=attempt_id,
                    evidence_kind=evidence.kind,
                    evidence_id=evidence.evidence_id,
                    source_authority_id=evidence.source_authority_id,
                    recipient_authority_id=recipient,
                    recipient_partition_id=partition_id,
                    source_available_at_s=evidence.available_at_s,
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
        "schema_version": "delta-reference-coordination-v1",
        "seed": seed,
        "phi": phi,
        "authority_registry_version": governance.registry_version,
        "deliveries": [item.model_dump(mode="json") for item in deliveries],
    }
    hidden_body = {
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "schema_version": "delta-reference-coordination-audit-v1",
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
    )
