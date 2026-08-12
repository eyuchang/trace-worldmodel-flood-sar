"""Deterministic authenticated project-fixture provider for route observations."""

from __future__ import annotations

from dataclasses import dataclass

from trace_jepa.support import canonical_json_bytes
from trace_reference.decision import (
    AcquisitionRequestReceipt,
    ProviderReceipt,
    ProviderReceiptInput,
    ReferenceRouteVerificationObservation,
    ReferenceRouteVerificationPayload,
    sign_provider_receipt,
)
from trace_reference.decision.canonical import verify_model_digest
from trace_reference.domain import ReferenceRawReport, ReferenceResourceArtifacts

from .routing import ReferenceRouteService


@dataclass(frozen=True)
class ReferenceRouteProviderInput:
    request: AcquisitionRequestReceipt
    report: ReferenceRawReport
    route_service: ReferenceRouteService
    resources: ReferenceResourceArtifacts
    observed_at_s: int | None = None
    delivered_at_s: int | None = None
    receipt_id_suffix: str | None = None


def build_reference_route_provider_receipt(
    values: ReferenceRouteProviderInput,
) -> ProviderReceipt:
    """Observe only requested routes at the registered observation time.

    Delivery may occur later under a registered fault. The fixture authenticates
    simulation-state observations and does not infer an open route when the
    underlying reduced-order model remains unknown.
    """

    request = values.request
    if not verify_model_digest(request, digest_field="request_digest"):
        raise ValueError("Reference route provider request digest is invalid")
    if request.channel_id != "reference-physical-route-verification-v1":
        raise ValueError("Reference route provider received an unsupported channel")
    if request.evidence_schema_version != "reference-route-evidence-v1":
        raise ValueError("Reference route provider received an unsupported evidence schema")
    if request.target_call_id != values.report.call_id:
        raise ValueError("Reference route provider request names another public report")
    observed_at_s = (
        request.expected_delivery_s if values.observed_at_s is None else values.observed_at_s
    )
    delivered_at_s = (
        request.expected_delivery_s if values.delivered_at_s is None else values.delivered_at_s
    )
    if not request.requested_at_s <= observed_at_s <= delivered_at_s:
        raise ValueError("Reference route provider observation/delivery interval is invalid")
    catalog = values.route_service.build_catalog(
        values.report,
        values.resources.public_catalog,
        at_s=observed_at_s,
    )
    current = {item.resource_id: item for item in catalog.routes}
    requested = tuple(zip(request.target_resource_ids, request.target_route_plan_ids, strict=True))
    if any(resource_id not in current for resource_id, _route_id in requested):
        raise ValueError("Reference route provider request names an absent resource")
    observations = tuple(
        ReferenceRouteVerificationObservation(
            requested_resource_id=resource_id,
            requested_route_plan_id=requested_route_id,
            observed_route_plan_id=current[resource_id].route_plan_id,
            observed_route_plan_digest=current[resource_id].route_plan_digest,
            observed_status=current[resource_id].status.value,
            observed_at_s=current[resource_id].sample_time_s,
            observation_semantics=("synthetic-direct-route-observation-not-operational-status"),
        )
        for resource_id, requested_route_id in sorted(requested)
    )
    payload = ReferenceRouteVerificationPayload(
        schema_version="reference-route-evidence-v1",
        request_id=request.request_id,
        call_id=request.target_call_id,
        route_catalog_digest_at_request=request.route_catalog_digest,
        observations=observations,
    )
    receipt_id = f"provider-receipt-{request.request_digest[:24]}"
    if values.receipt_id_suffix is not None:
        if not values.receipt_id_suffix.replace("-", "").isalnum():
            raise ValueError("Reference provider receipt suffix is unsafe")
        receipt_id += f"-{values.receipt_id_suffix}"
    return sign_provider_receipt(
        ProviderReceiptInput(
            receipt_id=receipt_id,
            request=request,
            status="success",
            started_at_s=request.requested_at_s,
            observed_at_s=max(item.observed_at_s for item in observations),
            delivered_at_s=delivered_at_s,
            payload_json=canonical_json_bytes(payload.model_dump(mode="json"))
            .decode("utf-8")
            .rstrip("\n"),
        )
    )


def build_reference_route_provider_timeout(
    request: AcquisitionRequestReceipt,
) -> ProviderReceipt:
    """Create the authenticated client-visible timeout half of a silent success."""

    if not verify_model_digest(request, digest_field="request_digest"):
        raise ValueError("Reference route provider request digest is invalid")
    return sign_provider_receipt(
        ProviderReceiptInput(
            receipt_id=f"provider-timeout-{request.request_digest[:24]}",
            request=request,
            status="timeout",
            started_at_s=request.requested_at_s,
            observed_at_s=None,
            delivered_at_s=request.expected_delivery_s,
            payload_json=None,
        )
    )
