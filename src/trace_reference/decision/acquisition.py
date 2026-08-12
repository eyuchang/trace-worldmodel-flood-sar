"""Idempotent physical-acquisition requests and authenticated provider ingestion."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel
from trace_jepa.support import canonical_json_bytes

from .canonical import decision_digest, verify_model_digest
from .domain import CostAmount, ResponseBundle, ResponseBundleKind

_PROVIDER_TEST_KEY = b"WF-DFLD-01-REFERENCE project-owned provider fixture key v1"
AcquisitionOutcomeStatus: TypeAlias = Literal[
    "evidence-accepted",
    "provider-timeout",
    "provider-partial",
    "provider-malformed",
    "provider-failed",
    "late-after-useful-deadline",
    "invalid-authentication",
    "unknown-request",
    "duplicate-receipt-ignored",
]
AcquisitionResult: TypeAlias = tuple[
    "AcquisitionOutcomeReceipt", "ReferencePhysicalEvidence | None"
]


class AcquisitionRequestReceipt(DeltaModel):
    schema_version: Literal["delta-reference-acquisition-request-v2"]
    request_id: str
    idempotency_key: str
    decision_id: str
    bundle_id: str
    bundle_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    offer_id: str
    provider_id: str
    channel_id: str
    evidence_schema_version: str
    target_call_id: str = Field(pattern=r"^RC-[0-9a-f]{16}$")
    target_resource_ids: tuple[str, ...] = Field(min_length=1)
    target_route_plan_ids: tuple[str, ...] = Field(min_length=1)
    route_catalog_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    requested_at_s: int = Field(ge=-172_800, le=345_600)
    expected_latency_s: int = Field(ge=1, le=43_200)
    expected_delivery_s: int = Field(ge=-172_800, le=388_800)
    latest_useful_delivery_s: int = Field(ge=-172_800, le=345_600)
    expected_physical_cost: CostAmount
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_route_targets(self) -> AcquisitionRequestReceipt:
        if len(self.target_resource_ids) != len(self.target_route_plan_ids):
            raise ValueError("Reference acquisition request route targets do not align")
        if len(set(self.target_resource_ids)) != len(self.target_resource_ids):
            raise ValueError("Reference acquisition request resource targets repeat")
        if len(set(self.target_route_plan_ids)) != len(self.target_route_plan_ids):
            raise ValueError("Reference acquisition request route targets repeat")
        return self


class ReferenceRouteVerificationObservation(DeltaModel):
    requested_resource_id: str = Field(pattern=r"^RR-[0-9a-f]{16}$")
    requested_route_plan_id: str = Field(pattern=r"^REF-ROUTE-[0-9a-f]{20}$")
    observed_route_plan_id: str = Field(pattern=r"^REF-ROUTE-[0-9a-f]{20}$")
    observed_route_plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_status: Literal["open", "blocked", "unknown", "unavailable"]
    observed_at_s: int = Field(ge=-172_800, le=388_800)
    observation_semantics: Literal["synthetic-direct-route-observation-not-operational-status"]


class ReferenceRouteVerificationPayload(DeltaModel):
    schema_version: Literal["reference-route-evidence-v1"]
    request_id: str
    call_id: str = Field(pattern=r"^RC-[0-9a-f]{16}$")
    route_catalog_digest_at_request: str = Field(pattern=r"^[0-9a-f]{64}$")
    observations: tuple[ReferenceRouteVerificationObservation, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_observations(self) -> ReferenceRouteVerificationPayload:
        resource_ids = tuple(item.requested_resource_id for item in self.observations)
        if len(set(resource_ids)) != len(resource_ids):
            raise ValueError("Reference route verification repeats a physical resource")
        if self.observations != tuple(
            sorted(self.observations, key=lambda item: item.requested_resource_id)
        ):
            raise ValueError("Reference route verification observations must be ordered")
        return self


class ProviderReceipt(DeltaModel):
    schema_version: Literal["delta-reference-provider-receipt-v1"]
    receipt_id: str
    request_id: str
    provider_id: str
    status: Literal["success", "timeout", "partial", "malformed", "failed"]
    started_at_s: int = Field(ge=-172_800, le=388_800)
    observed_at_s: int | None = Field(default=None, ge=-172_800, le=388_800)
    delivered_at_s: int = Field(ge=-172_800, le=388_800)
    payload_json: str | None = Field(default=None, max_length=65_536)
    payload_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_identity: str
    key_version: Literal["reference-provider-test-key-v1"]
    integrity_token: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_payload_status(self) -> ProviderReceipt:
        success = self.status == "success"
        if success != (self.payload_json is not None and self.payload_sha256 is not None):
            raise ValueError("Only a successful provider receipt carries a complete payload")
        if success != (self.observed_at_s is not None):
            raise ValueError("Only a successful provider receipt names an observation time")
        if self.delivered_at_s < self.started_at_s:
            raise ValueError("Provider delivery cannot precede request start")
        if self.observed_at_s is not None and self.observed_at_s < self.started_at_s:
            raise ValueError("Provider observation cannot precede request start")
        if self.observed_at_s is not None and self.observed_at_s > self.delivered_at_s:
            raise ValueError("Provider observation cannot follow provider delivery")
        return self


class ReferencePhysicalEvidence(DeltaModel):
    schema_version: Literal["delta-reference-physical-evidence-v1"]
    semantic_role: Literal["physical_observation"]
    evidence_id: str
    request_id: str
    provider_receipt_id: str
    channel_id: str
    evidence_schema_version: str
    source_identity: str
    observed_at_s: int = Field(ge=-172_800, le=388_800)
    delivered_at_s: int = Field(ge=-172_800, le=388_800)
    payload_json: str
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class AcquisitionOutcomeReceipt(DeltaModel):
    schema_version: Literal["delta-reference-acquisition-outcome-v1"]
    request_id: str
    request_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    provider_receipt_id: str
    provider_receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome_status: AcquisitionOutcomeStatus
    evidence_id: str | None
    requested_at_s: int = Field(ge=-172_800, le=345_600)
    started_at_s: int = Field(ge=-172_800, le=388_800)
    observed_at_s: int | None = Field(default=None, ge=-172_800, le=388_800)
    delivered_at_s: int = Field(ge=-172_800, le=388_800)
    ingested_at_s: int = Field(ge=-172_800, le=388_800)
    expected_physical_cost: CostAmount | None
    charged_physical_cost: CostAmount | None
    expected_latency_s: int | None = Field(default=None, ge=1, le=43_200)
    realized_latency_s: int | None = Field(default=None, ge=0, le=86_400)
    reason: str
    outcome_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ProviderReceiptInput:
    """Trusted project-fixture inputs used to construct one provider receipt."""

    receipt_id: str
    request: AcquisitionRequestReceipt
    status: Literal["success", "timeout", "partial", "malformed", "failed"]
    started_at_s: int
    observed_at_s: int | None
    delivered_at_s: int
    payload_json: str | None


@dataclass(frozen=True)
class AcquisitionOutcomeInput:
    """Executor-known context required to persist one acquisition outcome."""

    request: AcquisitionRequestReceipt | None
    provider_receipt_digest: str
    ingested_at_s: int
    status: AcquisitionOutcomeStatus
    evidence_id: str | None
    charged_cost: CostAmount | None
    reason: str
    realized_latency_s: int | None = None


def sign_provider_receipt(values: ProviderReceiptInput) -> ProviderReceipt:
    """Create one deterministic project-fixture receipt; this is not a production key."""

    payload_hash = (
        hashlib.sha256(values.payload_json.encode("utf-8")).hexdigest()
        if values.payload_json is not None
        else None
    )
    body = {
        "schema_version": "delta-reference-provider-receipt-v1",
        "receipt_id": values.receipt_id,
        "request_id": values.request.request_id,
        "provider_id": values.request.provider_id,
        "status": values.status,
        "started_at_s": values.started_at_s,
        "observed_at_s": values.observed_at_s,
        "delivered_at_s": values.delivered_at_s,
        "payload_json": values.payload_json,
        "payload_sha256": payload_hash,
        "source_identity": "reference-physical-channel-fixture",
        "key_version": "reference-provider-test-key-v1",
    }
    token = hmac.new(_PROVIDER_TEST_KEY, canonical_json_bytes(body), hashlib.sha256).hexdigest()
    return ProviderReceipt(**body, integrity_token=token)


def verify_provider_receipt(receipt: ProviderReceipt) -> bool:
    body = receipt.model_dump(mode="json", exclude={"integrity_token"})
    expected = hmac.new(_PROVIDER_TEST_KEY, canonical_json_bytes(body), hashlib.sha256).hexdigest()
    payload_valid = (
        receipt.payload_json is None
        or hashlib.sha256(receipt.payload_json.encode("utf-8")).hexdigest()
        == receipt.payload_sha256
    )
    return hmac.compare_digest(expected, receipt.integrity_token) and payload_valid


class EvidenceAcquisitionExecutor:
    """Stateful idempotency boundary; it cannot commit a downstream action."""

    def __init__(self) -> None:
        self._requests: dict[str, AcquisitionRequestReceipt] = {}
        self._seen_receipts: dict[str, str] = {}

    def request(self, bundle: ResponseBundle) -> AcquisitionRequestReceipt:
        if not verify_model_digest(bundle, digest_field="bundle_digest"):
            raise ValueError("Reference acquisition bundle digest is invalid")
        if bundle.kind != ResponseBundleKind.ACQUIRE_THEN_REASSESS:
            raise ValueError("Only an acquisition response bundle can create a request")
        offer = bundle.acquisition
        if offer is None:
            raise ValueError("Reference acquisition bundle is missing its offer")
        request_id = f"acq-request-{bundle.bundle_id}"
        existing = self._requests.get(request_id)
        if existing is not None:
            if existing.bundle_digest != bundle.bundle_digest:
                raise ValueError("Reference acquisition request ID was reused by another bundle")
            return existing
        body = {
            "schema_version": "delta-reference-acquisition-request-v2",
            "request_id": request_id,
            "idempotency_key": f"acq-idempotency-{bundle.bundle_digest[:24]}",
            "decision_id": bundle.decision_id,
            "bundle_id": bundle.bundle_id,
            "bundle_digest": bundle.bundle_digest,
            "proposal_digest": bundle.proposal_digest,
            "public_snapshot_digest": bundle.public_snapshot_digest,
            "offer_id": offer.offer_id,
            "provider_id": offer.provider_id,
            "channel_id": offer.channel_id,
            "evidence_schema_version": offer.evidence_schema_version,
            "target_call_id": offer.target_call_id,
            "target_resource_ids": offer.target_resource_ids,
            "target_route_plan_ids": offer.target_route_plan_ids,
            "route_catalog_digest": offer.route_catalog_digest,
            "requested_at_s": offer.requested_at_s,
            "expected_latency_s": offer.expected_latency_s,
            "expected_delivery_s": offer.requested_at_s + offer.expected_latency_s,
            "latest_useful_delivery_s": offer.latest_useful_delivery_s,
            "expected_physical_cost": offer.physical_cost.model_dump(mode="json"),
        }
        receipt = AcquisitionRequestReceipt(**body, request_digest=decision_digest(body))
        self._requests[request_id] = receipt
        return receipt

    def restore_request(self, request: AcquisitionRequestReceipt) -> None:
        """Restore one digest-verified durable request without issuing it again."""

        if not verify_model_digest(request, digest_field="request_digest"):
            raise ValueError("Reference restored acquisition request digest is invalid")
        existing = self._requests.get(request.request_id)
        if existing is not None and existing != request:
            raise ValueError("Reference restored acquisition request conflicts with durable state")
        self._requests[request.request_id] = request

    def ingest(
        self,
        receipt: ProviderReceipt,
        *,
        ingested_at_s: int | None = None,
    ) -> AcquisitionResult:
        ingestion_time = receipt.delivered_at_s if ingested_at_s is None else ingested_at_s
        if ingestion_time < receipt.delivered_at_s:
            raise ValueError("Provider receipt cannot be ingested before delivery")
        receipt_digest = decision_digest(receipt.model_dump(mode="json"))
        request = self._requests.get(receipt.request_id)
        if receipt.receipt_id in self._seen_receipts:
            return self._duplicate_outcome(receipt, request, receipt_digest, ingestion_time)
        if request is None:
            return self._unknown_request_outcome(receipt, receipt_digest, ingestion_time)
        if receipt.provider_id != request.provider_id or not verify_provider_receipt(receipt):
            return self._invalid_authentication_outcome(
                receipt, request, receipt_digest, ingestion_time
            )
        self._seen_receipts[receipt.receipt_id] = receipt_digest
        terminal = self._terminal_authenticated_outcome(
            receipt, request, receipt_digest, ingestion_time
        )
        if terminal is not None:
            return terminal
        return self._accept_evidence(receipt, request, receipt_digest, ingestion_time)

    def _terminal_authenticated_outcome(
        self,
        receipt: ProviderReceipt,
        request: AcquisitionRequestReceipt,
        receipt_digest: str,
        ingested_at_s: int,
    ) -> AcquisitionResult | None:
        latency = receipt.delivered_at_s - request.requested_at_s
        if receipt.started_at_s < request.requested_at_s:
            return self._no_evidence_outcome(
                receipt,
                AcquisitionOutcomeInput(
                    request=request,
                    provider_receipt_digest=receipt_digest,
                    ingested_at_s=ingested_at_s,
                    status="provider-malformed",
                    evidence_id=None,
                    charged_cost=request.expected_physical_cost,
                    reason="Provider work began before the registered acquisition request.",
                    realized_latency_s=latency,
                ),
            )
        if receipt.delivered_at_s > request.latest_useful_delivery_s:
            return self._no_evidence_outcome(
                receipt,
                AcquisitionOutcomeInput(
                    request=request,
                    provider_receipt_digest=receipt_digest,
                    ingested_at_s=ingested_at_s,
                    status="late-after-useful-deadline",
                    evidence_id=None,
                    charged_cost=request.expected_physical_cost,
                    reason="Authenticated evidence arrived after the registered useful deadline.",
                    realized_latency_s=latency,
                ),
            )
        failure_status = _provider_failure_status(receipt.status)
        if failure_status is not None:
            return self._no_evidence_outcome(
                receipt,
                AcquisitionOutcomeInput(
                    request=request,
                    provider_receipt_digest=receipt_digest,
                    ingested_at_s=ingested_at_s,
                    status=failure_status,
                    evidence_id=None,
                    charged_cost=request.expected_physical_cost,
                    reason="The authenticated provider did not return complete usable evidence.",
                    realized_latency_s=latency,
                ),
            )
        if not _payload_is_valid_object(receipt.payload_json):
            return self._no_evidence_outcome(
                receipt,
                AcquisitionOutcomeInput(
                    request=request,
                    provider_receipt_digest=receipt_digest,
                    ingested_at_s=ingested_at_s,
                    status="provider-malformed",
                    evidence_id=None,
                    charged_cost=request.expected_physical_cost,
                    reason="Authenticated provider payload did not satisfy the object schema.",
                    realized_latency_s=latency,
                ),
            )
        return None

    def _accept_evidence(
        self,
        receipt: ProviderReceipt,
        request: AcquisitionRequestReceipt,
        receipt_digest: str,
        ingested_at_s: int,
    ) -> AcquisitionResult:
        if (
            receipt.payload_json is None
            or receipt.payload_sha256 is None
            or receipt.observed_at_s is None
        ):
            raise RuntimeError("Successful provider receipt invariant was not enforced")
        evidence_id = f"physical-evidence-{receipt.receipt_id}"
        evidence_body = {
            "schema_version": "delta-reference-physical-evidence-v1",
            "semantic_role": "physical_observation",
            "evidence_id": evidence_id,
            "request_id": request.request_id,
            "provider_receipt_id": receipt.receipt_id,
            "channel_id": request.channel_id,
            "evidence_schema_version": request.evidence_schema_version,
            "source_identity": receipt.source_identity,
            "observed_at_s": receipt.observed_at_s,
            "delivered_at_s": receipt.delivered_at_s,
            "payload_json": receipt.payload_json,
            "payload_sha256": receipt.payload_sha256,
        }
        evidence = ReferencePhysicalEvidence(
            **evidence_body, evidence_digest=decision_digest(evidence_body)
        )
        return self._outcome(
            receipt,
            AcquisitionOutcomeInput(
                request=request,
                provider_receipt_digest=receipt_digest,
                ingested_at_s=ingested_at_s,
                status="evidence-accepted",
                evidence_id=evidence_id,
                charged_cost=request.expected_physical_cost,
                reason="Authenticated complete physical evidence passed schema and timing checks.",
                realized_latency_s=receipt.delivered_at_s - request.requested_at_s,
            ),
        ), evidence

    def _duplicate_outcome(
        self,
        receipt: ProviderReceipt,
        request: AcquisitionRequestReceipt | None,
        receipt_digest: str,
        ingested_at_s: int,
    ) -> AcquisitionResult:
        identical = self._seen_receipts[receipt.receipt_id] == receipt_digest
        return self._outcome(
            receipt,
            AcquisitionOutcomeInput(
                request=request,
                provider_receipt_digest=receipt_digest,
                ingested_at_s=ingested_at_s,
                status="duplicate-receipt-ignored" if identical else "invalid-authentication",
                evidence_id=None,
                charged_cost=None,
                reason=(
                    "An identical provider receipt was already ingested."
                    if identical
                    else "A receipt ID was replayed with different content."
                ),
            ),
        ), None

    def _unknown_request_outcome(
        self,
        receipt: ProviderReceipt,
        receipt_digest: str,
        ingested_at_s: int,
    ) -> AcquisitionResult:
        return self._outcome(
            receipt,
            AcquisitionOutcomeInput(
                request=None,
                provider_receipt_digest=receipt_digest,
                ingested_at_s=ingested_at_s,
                status="unknown-request",
                evidence_id=None,
                charged_cost=None,
                reason="The provider receipt does not bind a registered acquisition request.",
            ),
        ), None

    def _invalid_authentication_outcome(
        self,
        receipt: ProviderReceipt,
        request: AcquisitionRequestReceipt,
        receipt_digest: str,
        ingested_at_s: int,
    ) -> AcquisitionResult:
        return self._outcome(
            receipt,
            AcquisitionOutcomeInput(
                request=request,
                provider_receipt_digest=receipt_digest,
                ingested_at_s=ingested_at_s,
                status="invalid-authentication",
                evidence_id=None,
                charged_cost=None,
                reason="Provider source, signature, or payload digest verification failed.",
            ),
        ), None

    def _no_evidence_outcome(
        self,
        receipt: ProviderReceipt,
        values: AcquisitionOutcomeInput,
    ) -> AcquisitionResult:
        return self._outcome(receipt, values), None

    @staticmethod
    def _outcome(
        receipt: ProviderReceipt,
        values: AcquisitionOutcomeInput,
    ) -> AcquisitionOutcomeReceipt:
        body = {
            "schema_version": "delta-reference-acquisition-outcome-v1",
            "request_id": receipt.request_id,
            "request_digest": (
                values.request.request_digest if values.request is not None else None
            ),
            "provider_receipt_id": receipt.receipt_id,
            "provider_receipt_digest": values.provider_receipt_digest,
            "outcome_status": values.status,
            "evidence_id": values.evidence_id,
            "requested_at_s": (
                values.request.requested_at_s
                if values.request is not None
                else receipt.started_at_s
            ),
            "started_at_s": receipt.started_at_s,
            "observed_at_s": receipt.observed_at_s,
            "delivered_at_s": receipt.delivered_at_s,
            "ingested_at_s": values.ingested_at_s,
            "expected_physical_cost": (
                values.request.expected_physical_cost.model_dump(mode="json")
                if values.request is not None
                else None
            ),
            "charged_physical_cost": (
                values.charged_cost.model_dump(mode="json")
                if values.charged_cost is not None
                else None
            ),
            "expected_latency_s": (
                values.request.expected_latency_s if values.request is not None else None
            ),
            "realized_latency_s": values.realized_latency_s,
            "reason": values.reason,
        }
        return AcquisitionOutcomeReceipt(**body, outcome_digest=decision_digest(body))


def _provider_failure_status(
    status: Literal["success", "timeout", "partial", "malformed", "failed"],
) -> AcquisitionOutcomeStatus | None:
    if status == "timeout":
        return "provider-timeout"
    if status == "partial":
        return "provider-partial"
    if status == "malformed":
        return "provider-malformed"
    if status == "failed":
        return "provider-failed"
    return None


def _payload_is_valid_object(payload_json: str | None) -> bool:
    if payload_json is None:
        return False
    try:
        payload: Any = json.loads(payload_json)
    except json.JSONDecodeError:
        return False
    return isinstance(payload, dict)
