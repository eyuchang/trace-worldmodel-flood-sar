"""Runtime-only public reports selected by the registered fault schedule."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from trace_jepa.support import canonical_json_bytes
from trace_reference.domain import (
    ReferenceCoordinationDelivery,
    ReferenceCoordinationFaultAttempt,
    ReferenceFaultSchedule,
    ReferenceRawReport,
    ReferenceReportEnvelope,
    ReferenceScenarioArtifacts,
)
from trace_reference.domain.observations import (
    ReferencePublicLocation,
    ReferencePublicTaxonomy,
)
from trace_reference.generation import sign_reference_envelope

from .fault_overlay import ReferenceCoordinationOverlay


@dataclass(frozen=True)
class ReferenceInjectedReport:
    """One public report/envelope pair absent from the common exogenous artifacts."""

    fault_id: str
    report: ReferenceRawReport
    envelope: ReferenceReportEnvelope


@dataclass(frozen=True)
class ReferenceReportFaultOverlay:
    """Injected public evidence and its minimal authority-delivery attempts."""

    reports: tuple[ReferenceInjectedReport, ...]
    coordination: ReferenceCoordinationOverlay


def _hex(*parts: object) -> str:
    return hashlib.sha256("|".join(str(item) for item in parts).encode()).hexdigest()


def _delivery(injected: ReferenceInjectedReport) -> ReferenceCoordinationFaultAttempt:
    envelope = injected.envelope
    authority = envelope.initial_authority_id
    delivery = ReferenceCoordinationDelivery(
        delivery_id=f"CD-{_hex(injected.fault_id, envelope.envelope_id, authority)[:16]}",
        evidence_kind="public-report-envelope",
        evidence_id=envelope.envelope_id,
        source_authority_id=authority,
        recipient_authority_id=authority,
        recipient_partition_id=f"{authority}-P01",
        source_available_at_s=envelope.delivered_at_s,
        delivered_at_s=envelope.delivered_at_s,
        source_content_digest=hashlib.sha256(
            canonical_json_bytes(envelope.model_dump(mode="json"))
        ).hexdigest(),
    )
    return ReferenceCoordinationFaultAttempt(
        attempt_id=f"reference-fault-attempt-{_hex('injected', delivery.delivery_id)[:20]}",
        at_s=delivery.delivered_at_s,
        delivery=delivery,
        behavior="deliver",
    )


def _authenticated_false_report(
    scenario: ReferenceScenarioArtifacts,
    schedule: ReferenceFaultSchedule,
) -> ReferenceInjectedReport:
    trigger = next(
        item for item in schedule.triggers if item.family == "authenticated-false-report"
    )
    anchor = scenario.geography.islands[0].anchor
    call_id = f"RC-{_hex(trigger.fault_id, 'public-report')[:16]}"
    report = ReferenceRawReport(
        call_id=call_id,
        observed_at_s=trigger.anchor_s,
        channel="social-relay",
        callback_token=None,
        callback_failed=True,
        call_dropped=False,
        third_party=True,
        language_access="english",
        location=ReferencePublicLocation(
            easting_mm_epsg26910=anchor.easting_mm_epsg26910,
            northing_mm_epsg26910=anchor.northing_mm_epsg26910,
            precision_m=800,
            method="landmark",
            stated_descriptor="public island landmark",
        ),
        taxonomy=ReferencePublicTaxonomy.C_LEV,
        reported_occupants=None,
        medical_descriptors=(),
        descriptor_tokens=("possible-seepage", "source-unverified"),
    )
    envelope = sign_reference_envelope(
        report,
        envelope_id=f"RE-{_hex(trigger.fault_id, 'delivery-envelope')[:16]}",
        delivered_at_s=trigger.anchor_s,
        initial_authority_id="AUTH-02",
    )
    return ReferenceInjectedReport(trigger.fault_id, report, envelope)


def _identity_revision(
    scenario: ReferenceScenarioArtifacts,
    schedule: ReferenceFaultSchedule,
) -> ReferenceInjectedReport | None:
    trigger = next(
        item for item in schedule.triggers if item.family == "identity-dispute-visible-revision"
    )
    envelopes = {item.call_id: item for item in scenario.observations.delivery.envelopes}
    eligible = tuple(
        sorted(
            (
                (envelopes[report.call_id], report)
                for report in scenario.observations.raw.reports
                if report.callback_token is not None
                and envelopes[report.call_id].delivered_at_s >= trigger.anchor_s
            ),
            key=lambda item: (item[0].delivered_at_s, item[0].envelope_id),
        )
    )
    index = trigger.ordinal - 1
    if index >= len(eligible):
        return None
    source_envelope, source = eligible[index]
    delivered_at_s = source_envelope.delivered_at_s + trigger.delivery_offset_s
    report = ReferenceRawReport.model_validate(
        {
            **source.model_dump(mode="json"),
            "call_id": f"RC-{_hex(trigger.fault_id, source.call_id)[:16]}",
            "observed_at_s": min(345_300, source_envelope.delivered_at_s),
            "channel": "911",
            "callback_failed": False,
            "call_dropped": False,
            "reported_occupants": (
                None
                if source.reported_occupants is None
                else min(24, source.reported_occupants + 1)
            ),
            "descriptor_tokens": source.descriptor_tokens,
            "revision_of_call_id": source.call_id,
        }
    )
    envelope = sign_reference_envelope(
        report,
        envelope_id=f"RE-{_hex(trigger.fault_id, source_envelope.envelope_id)[:16]}",
        delivered_at_s=delivered_at_s,
        initial_authority_id=source_envelope.initial_authority_id,
    )
    return ReferenceInjectedReport(trigger.fault_id, report, envelope)


def build_reference_report_fault_overlay(
    scenario: ReferenceScenarioArtifacts,
    schedule: ReferenceFaultSchedule | None,
) -> ReferenceReportFaultOverlay:
    """Create fault-profile evidence without mutating common raw observations."""

    if schedule is None:
        return ReferenceReportFaultOverlay((), ReferenceCoordinationOverlay((), (), ()))
    injected = [_authenticated_false_report(scenario, schedule)]
    revision = _identity_revision(scenario, schedule)
    unreachable: tuple[str, ...] = ()
    if revision is None:
        trigger = next(
            item for item in schedule.triggers if item.family == "identity-dispute-visible-revision"
        )
        unreachable = (trigger.fault_id,)
    else:
        injected.append(revision)
    injected.sort(key=lambda item: (item.envelope.delivered_at_s, item.envelope.envelope_id))
    attempts = tuple(_delivery(item) for item in injected)
    selected = tuple((item.fault_id, item.envelope.envelope_id) for item in injected)
    return ReferenceReportFaultOverlay(
        tuple(injected),
        ReferenceCoordinationOverlay(attempts, selected, unreachable),
    )
