"""Generate keyed zero/one/many Reference reports and delivery envelopes."""

from __future__ import annotations

import hashlib
import hmac
import math
from dataclasses import dataclass
from typing import Literal

from trace_jepa.support import canonical_json_bytes
from trace_reference.domain.exposure import ReferenceExposureScenario, ReferenceSyntheticPerson
from trace_reference.domain.observations import (
    ReferenceAuthorityId,
    ReferenceChannel,
    ReferenceDeliveryEnvelopeScenario,
    ReferenceHiddenObservationLineage,
    ReferenceHiddenReportLineage,
    ReferenceLineageRelationship,
    ReferenceMedicalDescriptor,
    ReferenceObservationArtifacts,
    ReferencePublicLocation,
    ReferencePublicTaxonomy,
    ReferenceRawObservationScenario,
    ReferenceRawReport,
    ReferenceReportEnvelope,
)
from trace_reference.domain.truth import (
    ReferenceIncidentType,
    ReferenceTruthIncident,
    ReferenceTruthScenario,
)

from .randomness import standard_normal, uniform_micros

_RANDOMNESS_NAMESPACE = "reference-observations-v1"
_FIXTURE_SIGNING_MATERIAL = b"WF-DFLD-01-REFERENCE non-secret test signing fixture v1"

_TAXONOMY = {
    ReferenceIncidentType.STRANDED_STRUCTURE: ReferencePublicTaxonomy.C_STR,
    ReferenceIncidentType.VEHICLE_RESCUE: ReferencePublicTaxonomy.C_VEH,
    ReferenceIncidentType.LEVEE_INSPECTION: ReferencePublicTaxonomy.C_LEV,
    ReferenceIncidentType.MEDICAL_ACCESS: ReferencePublicTaxonomy.C_MED,
    ReferenceIncidentType.WELFARE_CHECK: ReferencePublicTaxonomy.C_WEL,
    ReferenceIncidentType.MISSING_PERSON: ReferencePublicTaxonomy.C_MIS,
    ReferenceIncidentType.ANIMAL_RESCUE: ReferencePublicTaxonomy.C_ANI,
    ReferenceIncidentType.INFORMATION_NEED: ReferencePublicTaxonomy.C_INF,
    ReferenceIncidentType.HAZARD_RESPONSE: ReferencePublicTaxonomy.C_HAZ,
}

_DESCRIPTORS = {
    ReferencePublicTaxonomy.C_STR: ("water-rising", "upper-floor", "porch-visible"),
    ReferencePublicTaxonomy.C_VEH: ("road-water", "vehicle-stalled", "near-crossing"),
    ReferencePublicTaxonomy.C_LEV: ("wet-slope", "possible-seepage", "public-observation"),
    ReferencePublicTaxonomy.C_MED: ("access-limited", "medication-needed", "mobility-help"),
    ReferencePublicTaxonomy.C_WEL: ("relative-unreachable", "check-request", "last-contact"),
    ReferencePublicTaxonomy.C_MIS: ("last-seen", "vehicle-description", "route-unknown"),
    ReferencePublicTaxonomy.C_ANI: ("animals-present", "pen-flooding", "owner-request"),
    ReferencePublicTaxonomy.C_INF: ("road-question", "shelter-question", "route-question"),
    ReferencePublicTaxonomy.C_HAZ: ("utility-hazard", "debris", "odor-reported"),
}


@dataclass(frozen=True)
class _Draft:
    draft_key: str
    observed_at_s: int
    delivery_delay_s: int
    truth_incident: ReferenceTruthIncident | None
    relationship: ReferenceLineageRelationship
    channel: ReferenceChannel
    callback_person: ReferenceSyntheticPerson | None
    taxonomy: ReferencePublicTaxonomy
    taxonomy_truthful: bool
    revision_of_key: str | None = None


@dataclass(frozen=True)
class _DraftSpec:
    relationship: ReferenceLineageRelationship
    suffix: str
    onset_offset_s: int
    maximum_delay_s: int
    channel: ReferenceChannel
    taxonomy: ReferencePublicTaxonomy | None = None
    taxonomy_truthful: bool = True
    callback: bool = True
    revision_of_key: str | None = None


@dataclass(frozen=True)
class _OptionalReportSpec:
    relationship: Literal["duplicate", "multi-channel", "conflict"]
    base_probability_micros: int
    onset_offset_s: int
    maximum_delay_s: int
    channel: ReferenceChannel
    callback: bool


def _probability(base_micros: int, iota_micros: int, *, inverse: bool = False) -> int:
    quality = iota_micros / 700_000
    scaled = base_micros / quality if inverse else base_micros * quality
    return min(950_000, max(10_000, round(scaled)))


def _draw(seed: int, draft_key: str, mechanism: str) -> int:
    return uniform_micros(seed, _RANDOMNESS_NAMESPACE, draft_key, mechanism)


def _draft(
    incident: ReferenceTruthIncident,
    people_by_id: dict[str, ReferenceSyntheticPerson],
    *,
    seed: int,
    spec: _DraftSpec,
) -> _Draft:
    key = f"{incident.truth_incident_id}|{spec.suffix}"
    affected = tuple(people_by_id[item] for item in incident.affected_truth_person_ids)
    return _Draft(
        draft_key=key,
        observed_at_s=min(345_300, incident.onset_s + spec.onset_offset_s),
        delivery_delay_s=_draw(seed, key, "delivery-delay") % (spec.maximum_delay_s + 1),
        truth_incident=incident,
        relationship=spec.relationship,
        channel=spec.channel,
        callback_person=affected[0] if affected and spec.callback else None,
        taxonomy=spec.taxonomy or _TAXONOMY[incident.incident_type],
        taxonomy_truthful=spec.taxonomy_truthful,
        revision_of_key=spec.revision_of_key,
    )


def _incident_drafts(
    incident: ReferenceTruthIncident,
    people_by_id: dict[str, ReferenceSyntheticPerson],
    *,
    seed: int,
    iota_micros: int,
) -> list[_Draft]:
    key = incident.truth_incident_id
    if _draw(seed, key, "report") >= _probability(760_000, iota_micros):
        return []
    initial_key = f"{key}|initial"
    drafts = [
        _draft(
            incident,
            people_by_id,
            seed=seed,
            spec=_DraftSpec(
                relationship="initial",
                suffix="initial",
                onset_offset_s=60,
                maximum_delay_s=1_800,
                channel="911",
            ),
        )
    ]
    optional_reports = (
        _OptionalReportSpec("duplicate", 300_000, 120, 3_600, "social-relay", True),
        _OptionalReportSpec("multi-channel", 140_000, 300, 3_600, "radio-relay", False),
        _OptionalReportSpec("conflict", 160_000, 480, 3_600, "311", True),
    )
    for optional in optional_reports:
        if _draw(seed, key, optional.relationship) >= _probability(
            optional.base_probability_micros, iota_micros, inverse=True
        ):
            continue
        is_conflict = optional.relationship == "conflict"
        drafts.append(
            _draft(
                incident,
                people_by_id,
                seed=seed,
                spec=_DraftSpec(
                    relationship=optional.relationship,
                    suffix=optional.relationship,
                    onset_offset_s=optional.onset_offset_s,
                    maximum_delay_s=optional.maximum_delay_s,
                    channel=optional.channel,
                    taxonomy=(
                        ReferencePublicTaxonomy.C_WEL
                        if is_conflict
                        and incident.incident_type != ReferenceIncidentType.WELFARE_CHECK
                        else None
                    ),
                    taxonomy_truthful=not is_conflict,
                    callback=optional.callback,
                ),
            )
        )
    affected = tuple(people_by_id[item] for item in incident.affected_truth_person_ids)
    vulnerable = any(
        person.mobility != "standard" or person.medical_dependency != "none" for person in affected
    )
    if vulnerable and _draw(seed, key, "third-party-welfare") < _probability(
        120_000, iota_micros, inverse=True
    ):
        drafts.append(
            _draft(
                incident,
                people_by_id,
                seed=seed,
                spec=_DraftSpec(
                    relationship="third-party-welfare",
                    suffix="third-party-welfare",
                    onset_offset_s=900,
                    maximum_delay_s=3_600,
                    channel="311",
                    taxonomy=ReferencePublicTaxonomy.C_WEL,
                    taxonomy_truthful=incident.incident_type == ReferenceIncidentType.WELFARE_CHECK,
                    callback=False,
                ),
            )
        )
    if incident.incident_type == ReferenceIncidentType.STRANDED_STRUCTURE and _draw(
        seed, key, "revision"
    ) < _probability(400_000, iota_micros, inverse=True):
        drafts.append(
            _draft(
                incident,
                people_by_id,
                seed=seed,
                spec=_DraftSpec(
                    relationship="revision",
                    suffix="revision",
                    onset_offset_s=1_800,
                    maximum_delay_s=900,
                    channel="911",
                    revision_of_key=initial_key,
                ),
            )
        )
    return drafts


def _report_drafts(
    truth: ReferenceTruthScenario,
    people_by_id: dict[str, ReferenceSyntheticPerson],
    *,
    seed: int,
    iota_micros: int,
) -> list[_Draft]:
    drafts = [
        draft
        for incident in truth.incidents
        for draft in _incident_drafts(incident, people_by_id, seed=seed, iota_micros=iota_micros)
    ]
    for hour_start in range(-172_800, 345_600, 3_600):
        key = f"false-benign-levee|{hour_start}"
        if _draw(seed, key, "report") >= _probability(90_000, iota_micros, inverse=True):
            continue
        drafts.append(
            _Draft(
                draft_key=key,
                observed_at_s=hour_start + 900,
                delivery_delay_s=_draw(seed, key, "delivery-delay") % 1_801,
                truth_incident=None,
                relationship="false-benign-levee",
                channel="311",
                callback_person=None,
                taxonomy=ReferencePublicTaxonomy.C_LEV,
                taxonomy_truthful=False,
            )
        )
    return sorted(drafts, key=lambda item: item.draft_key)


def _public_id(seed: int, draft_key: str) -> str:
    value = hashlib.sha256(f"Reference-public-report|{seed}|{draft_key}".encode()).hexdigest()
    return f"RC-{value[:16]}"


def _envelope_id(seed: int, draft_key: str) -> str:
    value = hashlib.sha256(f"Reference-delivery-envelope|{seed}|{draft_key}".encode()).hexdigest()
    return f"RE-{value[:16]}"


def _location(
    draft: _Draft,
    *,
    seed: int,
    iota_micros: int,
) -> tuple[ReferencePublicLocation, int]:
    method_draw = _draw(seed, draft.draft_key, "location-method")
    quality_share = iota_micros / 700_000
    gps_limit = round(250_000 * quality_share)
    address_limit = gps_limit + round(200_000 * quality_share)
    landmark_limit = min(900_000, address_limit + 300_000)
    if method_draw < gps_limit:
        method, lower, upper = "gps", 15, 75
    elif method_draw < address_limit:
        method, lower, upper = "address-intersection", 30, 120
    elif method_draw < landmark_limit:
        method, lower, upper = "landmark", 200, 800
    else:
        method, lower, upper = "cell-sector", 400, 1_500
    quality_scale = min(3.0, 700_000 / iota_micros)
    precision = max(
        15,
        round((lower + (upper - lower) * (method_draw % 10_000) / 10_000) * quality_scale),
    )
    angle = 2 * math.pi * _draw(seed, draft.draft_key, "location-angle") / 1_000_000
    distance = (
        abs(standard_normal(seed, _RANDOMNESS_NAMESPACE, draft.draft_key, "location-distance"))
        * precision
    )
    incident = draft.truth_incident
    true_x = incident.location_easting_mm if incident else 621_000_000
    true_y = incident.location_northing_mm if incident else 4_223_000_000
    descriptor_index = _draw(seed, draft.draft_key, "location-descriptor") % 3
    return (
        ReferencePublicLocation(
            easting_mm_epsg26910=true_x + round(math.cos(angle) * distance * 1_000),
            northing_mm_epsg26910=true_y + round(math.sin(angle) * distance * 1_000),
            precision_m=min(4_500, precision),
            method=method,
            stated_descriptor=("near crossing", "island road", "visible landmark")[
                descriptor_index
            ],
        ),
        round(distance),
    )


def _initial_authority(draft: _Draft) -> ReferenceAuthorityId:
    if draft.taxonomy == ReferencePublicTaxonomy.C_LEV:
        return "AUTH-02"
    if draft.taxonomy in {ReferencePublicTaxonomy.C_VEH, ReferencePublicTaxonomy.C_HAZ}:
        return "AUTH-03"
    if draft.channel == "radio-relay":
        return "AUTH-04"
    return "AUTH-01"


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
    """Verify one project-fixture envelope without treating its content as true."""

    body = envelope.model_dump(mode="json", exclude={"integrity_token"})
    expected = _integrity_token(report, body)
    return hmac.compare_digest(expected, envelope.integrity_token)


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


def _medical_descriptors(
    affected: tuple[str, ...],
    people_by_id: dict[str, ReferenceSyntheticPerson],
) -> tuple[ReferenceMedicalDescriptor, ...]:
    values: set[ReferenceMedicalDescriptor] = set()
    for person_id in affected:
        dependency = people_by_id[person_id].medical_dependency
        if dependency == "oxygen":
            values.add("oxygen")
        elif dependency == "dialysis":
            values.add("dialysis")
        elif dependency == "insulin":
            values.add("insulin")
        if people_by_id[person_id].mobility != "standard":
            values.add("mobility")
    return tuple(sorted(values))


def _reported_occupants(
    draft: _Draft,
    affected: tuple[str, ...],
    *,
    seed: int,
) -> int | None:
    if not affected:
        return None
    truth_count = len(affected)
    if draft.relationship == "revision":
        return truth_count
    noise_options = (-1, 0, 0, 1, 2)
    noise = noise_options[_draw(seed, draft.draft_key, "occupants") % len(noise_options)]
    if draft.relationship == "conflict" and noise == 0:
        noise = 2
    return max(0, truth_count + noise)


def _language_delay(draft: _Draft, *, seed: int) -> int:
    person = draft.callback_person
    if person is None or person.language_access == "english":
        return 0
    return 300 + _draw(seed, draft.draft_key, "language-delay") % 601


def generate_reference_observations(
    truth: ReferenceTruthScenario,
    exposure: ReferenceExposureScenario,
    *,
    seed: int,
    iota: float = 0.7,
) -> ReferenceObservationArtifacts:
    """Transform hidden truth into separately checksummed raw, delivery, and lineage data."""

    if not 0.3 <= iota <= 1.0:
        raise ValueError("Reference iota must remain within the registered axis range")
    iota_micros = round(iota * 1_000_000)
    people_by_id = {item.truth_person_id: item for item in exposure.people}
    drafts = _report_drafts(truth, people_by_id, seed=seed, iota_micros=iota_micros)
    draft_to_call_id = {draft.draft_key: _public_id(seed, draft.draft_key) for draft in drafts}
    if len(set(draft_to_call_id.values())) != len(draft_to_call_id):
        raise RuntimeError("Reference public report identifier collision")

    reports: list[ReferenceRawReport] = []
    envelopes: list[ReferenceReportEnvelope] = []
    lineage: list[ReferenceHiddenReportLineage] = []
    for draft in drafts:
        call_id = draft_to_call_id[draft.draft_key]
        location, location_error_m = _location(draft, seed=seed, iota_micros=iota_micros)
        callback_failed = _draw(seed, draft.draft_key, "callback-failure") < _probability(
            310_000, iota_micros, inverse=True
        )
        call_dropped = _draw(seed, draft.draft_key, "drop") < _probability(
            100_000, iota_micros, inverse=True
        )
        affected = draft.truth_incident.affected_truth_person_ids if draft.truth_incident else ()
        occupant_truth = len(affected) if affected else None
        reported_occupants = _reported_occupants(draft, affected, seed=seed)
        descriptors = _DESCRIPTORS[draft.taxonomy]
        report = ReferenceRawReport(
            call_id=call_id,
            observed_at_s=draft.observed_at_s,
            channel=draft.channel,
            callback_token=(
                None
                if callback_failed or draft.callback_person is None
                else draft.callback_person.synthetic_callback_token
            ),
            callback_failed=callback_failed,
            call_dropped=call_dropped,
            third_party=draft.relationship
            in {"multi-channel", "third-party-welfare", "false-benign-levee"},
            language_access=(
                draft.callback_person.language_access if draft.callback_person else "english"
            ),
            location=location,
            taxonomy=draft.taxonomy,
            reported_occupants=reported_occupants,
            medical_descriptors=_medical_descriptors(affected, people_by_id),
            descriptor_tokens=(
                descriptors[_draw(seed, draft.draft_key, "descriptor") % len(descriptors)],
            ),
            revision_of_call_id=(
                draft_to_call_id[draft.revision_of_key]
                if draft.revision_of_key is not None
                else None
            ),
        )
        envelope = sign_reference_envelope(
            report,
            envelope_id=_envelope_id(seed, draft.draft_key),
            delivered_at_s=(
                draft.observed_at_s + draft.delivery_delay_s + _language_delay(draft, seed=seed)
            ),
            initial_authority_id=_initial_authority(draft),
        )
        reports.append(report)
        envelopes.append(envelope)
        lineage.append(
            ReferenceHiddenReportLineage(
                call_id=call_id,
                truth_incident_id=(
                    draft.truth_incident.truth_incident_id if draft.truth_incident else None
                ),
                relationship=draft.relationship,
                truth_person_ids=affected,
                true_location_error_m=location_error_m,
                taxonomy_truthful=draft.taxonomy_truthful,
                occupant_report_truthful=(
                    reported_occupants == occupant_truth if occupant_truth is not None else None
                ),
            )
        )

    reports.sort(key=lambda item: (item.observed_at_s, item.call_id))
    envelopes.sort(key=lambda item: (item.delivered_at_s, item.envelope_id))
    lineage.sort(key=lambda item: item.call_id)
    raw_body = {
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "schema_version": "delta-reference-observations-v1",
        "coefficient_version": "delta-reference-observation-development-coefficients-v1",
        "scientific_status": "development-coefficients-not-frozen-for-validation",
        "seed": seed,
        "iota_micros": iota_micros,
        "reports": [item.model_dump(mode="json") for item in reports],
    }
    delivery_body = {
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "schema_version": "delta-reference-delivery-envelopes-v1",
        "seed": seed,
        "envelopes": [item.model_dump(mode="json") for item in envelopes],
    }
    hidden_body = {
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "schema_version": "delta-reference-hidden-lineage-v1",
        "entries": [item.model_dump(mode="json") for item in lineage],
    }
    return ReferenceObservationArtifacts(
        raw=ReferenceRawObservationScenario(
            **raw_body,
            raw_reports_digest=hashlib.sha256(canonical_json_bytes(raw_body)).hexdigest(),
        ),
        delivery=ReferenceDeliveryEnvelopeScenario(
            **delivery_body,
            delivery_envelopes_digest=hashlib.sha256(
                canonical_json_bytes(delivery_body)
            ).hexdigest(),
        ),
        hidden=ReferenceHiddenObservationLineage(
            **hidden_body,
            hidden_digest=hashlib.sha256(canonical_json_bytes(hidden_body)).hexdigest(),
        ),
    )
