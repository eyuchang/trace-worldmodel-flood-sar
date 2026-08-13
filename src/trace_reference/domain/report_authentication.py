"""Project-owned authentication for synthetic Reference report envelopes."""

from __future__ import annotations

import hashlib
import hmac

from trace_jepa.support import canonical_json_bytes

from .observations import (
    ReferenceAuthorityId,
    ReferenceRawReport,
    ReferenceReportEnvelope,
)

_FIXTURE_SIGNING_MATERIAL = b"WF-DFLD-01-REFERENCE non-secret test signing fixture v1"


def _integrity_token(
    report: ReferenceRawReport,
    envelope_body: dict[str, object],
) -> str:
    signed = {"raw_report": report.model_dump(mode="json"), "delivery_envelope": envelope_body}
    return hmac.new(
        _FIXTURE_SIGNING_MATERIAL,
        canonical_json_bytes(signed),
        hashlib.sha256,
    ).hexdigest()


def verify_reference_envelope(
    report: ReferenceRawReport,
    envelope: ReferenceReportEnvelope,
) -> bool:
    """Authenticate a fixture envelope without declaring its report truthful."""

    body = envelope.model_dump(mode="json", exclude={"integrity_token"})
    return hmac.compare_digest(_integrity_token(report, body), envelope.integrity_token)


def sign_reference_envelope(
    report: ReferenceRawReport,
    *,
    envelope_id: str,
    delivered_at_s: int,
    initial_authority_id: ReferenceAuthorityId,
) -> ReferenceReportEnvelope:
    """Sign one synthetic public report with the project-owned fixture identity."""

    body: dict[str, object] = {
        "envelope_id": envelope_id,
        "call_id": report.call_id,
        "delivered_at_s": delivered_at_s,
        "initial_authority_id": initial_authority_id,
        "authentication_status": "fixture-valid",
        "key_version": "reference-test-key-v1",
    }
    return ReferenceReportEnvelope(
        **body,
        integrity_token=_integrity_token(report, body),
    )
