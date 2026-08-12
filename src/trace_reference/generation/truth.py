"""Generate causal Reference incident episodes from physical state and exposure."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from trace_jepa.support import canonical_json_bytes
from trace_reference.domain.exposure import (
    ReferenceExposureScenario,
    ReferenceSyntheticPerson,
    ReferenceSyntheticStructure,
)
from trace_reference.domain.physical import ReferencePhysicalSample, ReferencePhysicalScenario
from trace_reference.domain.truth import (
    ReferenceIncidentCandidateAttempt,
    ReferenceIncidentCandidateAudit,
    ReferenceIncidentType,
    ReferenceServiceRequirement,
    ReferenceTruthIncident,
    ReferenceTruthScenario,
)

from .randomness import keyed_digest, uniform_micros

_CANDIDATE_TICK_S = 1_800

_DEVELOPMENT_INTERCEPTS_MICROS = {
    ReferenceIncidentType.STRANDED_STRUCTURE: 4_200,
    ReferenceIncidentType.VEHICLE_RESCUE: 1_700,
    ReferenceIncidentType.LEVEE_INSPECTION: 2_100,
    ReferenceIncidentType.MEDICAL_ACCESS: 2_500,
    ReferenceIncidentType.WELFARE_CHECK: 2_500,
    ReferenceIncidentType.MISSING_PERSON: 1_400,
    ReferenceIncidentType.ANIMAL_RESCUE: 1_100,
    ReferenceIncidentType.INFORMATION_NEED: 1_500,
    ReferenceIncidentType.HAZARD_RESPONSE: 1_200,
}

_REQUIREMENTS = {
    ReferenceIncidentType.STRANDED_STRUCTURE: ("water-rescue", 2, 7_200),
    ReferenceIncidentType.VEHICLE_RESCUE: ("road-rescue", 1, 5_400),
    ReferenceIncidentType.LEVEE_INSPECTION: ("levee-inspection", 1, 3_600),
    ReferenceIncidentType.MEDICAL_ACCESS: ("medical-transport", 1, 5_400),
    ReferenceIncidentType.WELFARE_CHECK: ("welfare-check", 1, 3_600),
    ReferenceIncidentType.MISSING_PERSON: ("missing-person-search", 2, 10_800),
    ReferenceIncidentType.ANIMAL_RESCUE: ("animal-rescue", 1, 5_400),
    ReferenceIncidentType.INFORMATION_NEED: ("public-information", 1, 1_800),
    ReferenceIncidentType.HAZARD_RESPONSE: ("hazard-control", 2, 7_200),
}


@dataclass(frozen=True)
class _CandidateContext:
    seed: int
    physical: ReferencePhysicalSample
    structure: ReferenceSyntheticStructure
    occupants: tuple[ReferenceSyntheticPerson, ...]
    away_people: tuple[ReferenceSyntheticPerson, ...]
    incident_type: ReferenceIncidentType


@dataclass
class _EpisodeDraft:
    incident_type: ReferenceIncidentType
    episode_key: str
    anchor_id: str
    eligible_start_s: int
    eligible_end_s: int
    subject_count_at_start: int
    attempt_count: int = 0
    rejected_attempt_count: int = 0
    attempt_trace_sha256: str = "0" * 64
    representative_attempt: ReferenceIncidentCandidateAttempt | None = None
    accepted_truth_incident_id: str | None = None
    suppressed_eligible_ticks: int = 0

    def complete(self) -> ReferenceIncidentCandidateAudit:
        return ReferenceIncidentCandidateAudit(
            incident_type=self.incident_type,
            episode_key=self.episode_key,
            anchor_id=self.anchor_id,
            eligible_start_s=self.eligible_start_s,
            eligible_end_s=self.eligible_end_s,
            subject_count_at_start=self.subject_count_at_start,
            attempt_count=self.attempt_count,
            rejected_attempt_count=self.rejected_attempt_count,
            attempt_trace_sha256=self.attempt_trace_sha256,
            representative_attempt=self._representative_attempt(),
            accepted_truth_incident_id=self.accepted_truth_incident_id,
            suppressed_eligible_ticks=self.suppressed_eligible_ticks,
            suppression_reason=(
                "eligible state and affected subject set persisted after incident acceptance"
                if self.suppressed_eligible_ticks
                else None
            ),
        )

    def _representative_attempt(self) -> ReferenceIncidentCandidateAttempt:
        if self.representative_attempt is None:
            raise RuntimeError("eligible Reference episode has no keyed candidate attempt")
        return self.representative_attempt

    def record(self, attempt: ReferenceIncidentCandidateAttempt) -> None:
        attempt_bytes = canonical_json_bytes(attempt.model_dump(mode="json"))
        self.attempt_trace_sha256 = hashlib.sha256(
            bytes.fromhex(self.attempt_trace_sha256) + attempt_bytes
        ).hexdigest()
        self.attempt_count += 1
        self.rejected_attempt_count += int(attempt.disposition == "draw-rejected")
        self.representative_attempt = attempt


@dataclass
class _TruthAccumulator:
    seed: int
    incidents: list[ReferenceTruthIncident] = field(default_factory=list)
    audit: list[ReferenceIncidentCandidateAudit] = field(default_factory=list)
    episode_state: dict[tuple[ReferenceIncidentType, str], tuple[str, _EpisodeDraft]] = field(
        default_factory=dict
    )

    def observe(
        self,
        context: _CandidateContext,
        *,
        eligible: bool,
        probability: int,
        severity: int,
        signature: str,
    ) -> None:
        at_s = context.physical.at_s
        anchor_key = (context.incident_type, _anchor_id(context))
        if not eligible:
            self._close(anchor_key, at_s)
            return
        draft = self._episode(context, anchor_key, signature)
        if draft.accepted_truth_incident_id is not None:
            draft.suppressed_eligible_ticks += 1
            return
        attempt = self._attempt(context, probability)
        draft.record(attempt)
        if attempt.disposition == "accepted-new-episode":
            incident = _truth_incident(
                context,
                candidate_digest=attempt.candidate_digest,
                episode_key=draft.episode_key,
                severity_micros=severity,
            )
            self.incidents.append(incident)
            draft.accepted_truth_incident_id = incident.truth_incident_id

    def _episode(
        self,
        context: _CandidateContext,
        anchor_key: tuple[ReferenceIncidentType, str],
        signature: str,
    ) -> _EpisodeDraft:
        at_s = context.physical.at_s
        previous = self.episode_state.get(anchor_key)
        if previous is not None and previous[0] == signature:
            previous[1].eligible_end_s = at_s + _CANDIDATE_TICK_S
            return previous[1]
        self._close(anchor_key, at_s)
        draft = _EpisodeDraft(
            incident_type=context.incident_type,
            episode_key=_episode_key(context, signature, at_s),
            anchor_id=_anchor_id(context),
            eligible_start_s=at_s,
            eligible_end_s=at_s + _CANDIDATE_TICK_S,
            subject_count_at_start=len((*context.occupants, *context.away_people)),
        )
        self.episode_state[anchor_key] = (signature, draft)
        return draft

    def _attempt(
        self,
        context: _CandidateContext,
        probability: int,
    ) -> ReferenceIncidentCandidateAttempt:
        at_s = context.physical.at_s
        identifier_parts = (
            at_s,
            context.incident_type.value,
            context.structure.truth_structure_id,
        )
        candidate_digest = keyed_digest(
            self.seed,
            "delta-reference-randomness-v1",
            "truth-candidate",
            *identifier_parts,
        ).hex()
        draw = uniform_micros(
            self.seed,
            "delta-reference-randomness-v1",
            "truth-candidate-draw",
            *identifier_parts,
        )
        return ReferenceIncidentCandidateAttempt(
            candidate_digest=candidate_digest,
            at_s=at_s,
            probability_micros=probability,
            draw_micros=draw,
            disposition=("draw-rejected" if draw >= probability else "accepted-new-episode"),
        )

    def _close(
        self,
        anchor_key: tuple[ReferenceIncidentType, str],
        at_s: int,
    ) -> None:
        completed = self.episode_state.pop(anchor_key, None)
        if completed is not None:
            completed[1].eligible_end_s = at_s
            self.audit.append(completed[1].complete())

    def finish(self) -> None:
        for anchor_key in tuple(self.episode_state):
            self._close(anchor_key, 345_600)


def _person_at(person: ReferenceSyntheticPerson, at_s: int) -> str:
    return max(
        (item for item in person.trajectory if item.at_s <= at_s),
        key=lambda item: item.at_s,
    ).synthetic_structure_id


def _hazard_micros(sample: ReferencePhysicalSample, island_id: str) -> int:
    rain = min(350_000, sample.weather.effective_rain_milli_in_per_hour * 240)
    wind = min(150_000, sample.weather.wind_milli_knots * 4)
    flood = 0
    if island_id == "ISL-01":
        flood = {
            "not-threatened": 0,
            "first-street-flooding": 550_000,
            "one-third-city-synthetic-extent": 900_000,
        }[sample.breach.isleton_flood_state]
    crossing_loss = sum(item.status != "open" for item in sample.crossings) * 35_000
    return min(1_000_000, 100_000 + rain + wind + flood + crossing_loss)


def _subjects_signature(people: Iterable[ReferenceSyntheticPerson]) -> str:
    ids = tuple(sorted(item.truth_person_id for item in people))
    return hashlib.sha256(canonical_json_bytes(ids)).hexdigest()[:16]


def _person_centered_factors(
    context: _CandidateContext,
    *,
    hazard: int,
    access_impaired: bool,
) -> tuple[bool, int, int | None]:
    occupants = context.occupants
    away_people = context.away_people
    incident_type = context.incident_type
    if incident_type == ReferenceIncidentType.STRANDED_STRUCTURE:
        return (
            bool(occupants) and hazard >= 450_000,
            len(occupants) * 170_000,
            850_000 if access_impaired else 500_000,
        )
    if incident_type == ReferenceIncidentType.VEHICLE_RESCUE:
        return (
            bool(away_people) and (access_impaired or hazard >= 350_000),
            len(away_people) * 180_000,
            950_000 if access_impaired else 450_000,
        )
    if incident_type == ReferenceIncidentType.MEDICAL_ACCESS:
        dependent = tuple(item for item in occupants if item.medical_dependency != "none")
        return (
            bool(dependent) and hazard >= 260_000,
            len(dependent) * 320_000,
            950_000 if access_impaired else 600_000,
        )
    if incident_type == ReferenceIncidentType.WELFARE_CHECK:
        vulnerable = tuple(
            item
            for item in occupants
            if item.mobility != "standard" or item.medical_dependency != "none"
        )
        return bool(vulnerable) and hazard >= 200_000, len(vulnerable) * 260_000, 700_000
    if incident_type == ReferenceIncidentType.MISSING_PERSON:
        return (
            bool(away_people) and hazard >= 300_000,
            len(away_people) * 250_000,
            850_000 if access_impaired else 600_000,
        )
    return False, 0, None


def _eligible_and_factors(context: _CandidateContext) -> tuple[bool, int, int, str]:
    sample = context.physical
    structure = context.structure
    occupants = context.occupants
    away_people = context.away_people
    hazard = _hazard_micros(sample, structure.island_id)
    maximum_vulnerability = max(
        (person.vulnerability_micros for person in (*occupants, *away_people)),
        default=structure.vulnerability_micros,
    )
    access_impaired = any(item.status != "open" for item in sample.crossings)
    incident_type = context.incident_type
    eligible, subject_factor, person_access_factor = _person_centered_factors(
        context, hazard=hazard, access_impaired=access_impaired
    )
    if person_access_factor is not None:
        access_factor = person_access_factor
    elif incident_type == ReferenceIncidentType.LEVEE_INSPECTION:
        eligible = structure.island_id == "ISL-01" and sample.at_s >= 144_000
        subject_factor = 700_000
        access_factor = 850_000
    elif incident_type == ReferenceIncidentType.ANIMAL_RESCUE:
        eligible = structure.animal_units > 0 and hazard >= 400_000
        subject_factor = min(1_000_000, structure.animal_units * 180_000)
        access_factor = 750_000
    elif incident_type == ReferenceIncidentType.INFORMATION_NEED:
        eligible = sample.at_s >= 0 and (hazard >= 250_000 or access_impaired)
        subject_factor = 550_000
        maximum_vulnerability = structure.vulnerability_micros
        access_factor = 700_000
    else:
        eligible = sample.at_s >= 0 and (hazard >= 500_000 or access_impaired)
        subject_factor = 600_000
        maximum_vulnerability = structure.vulnerability_micros
        access_factor = 900_000 if access_impaired else 650_000
    subject_factor = min(1_000_000, subject_factor)
    subject_people = (
        away_people
        if incident_type
        in {
            ReferenceIncidentType.VEHICLE_RESCUE,
            ReferenceIncidentType.MISSING_PERSON,
        }
        else occupants
    )
    subject_signature = _subjects_signature(subject_people)
    probability = round(
        _DEVELOPMENT_INTERCEPTS_MICROS[incident_type]
        * hazard
        * max(50_000, subject_factor)
        * max(50_000, maximum_vulnerability)
        * access_factor
        / 10**24
    )
    return eligible, min(1_000_000, probability), hazard, subject_signature


def _episode_key(context: _CandidateContext, subject_signature: str, start_s: int) -> str:
    return (
        f"{context.incident_type.value}|{_anchor_id(context)}|{subject_signature}|start:{start_s}"
    )


def _anchor_id(context: _CandidateContext) -> str:
    return (
        "SIM-RD407-WEST-01"
        if context.incident_type == ReferenceIncidentType.LEVEE_INSPECTION
        else context.structure.truth_structure_id
    )


def _truth_incident(
    context: _CandidateContext,
    *,
    candidate_digest: str,
    episode_key: str,
    severity_micros: int,
) -> ReferenceTruthIncident:
    incident_type = context.incident_type
    capability, service_units, duration_s = _REQUIREMENTS[incident_type]
    affected = (
        context.away_people
        if incident_type
        in {ReferenceIncidentType.VEHICLE_RESCUE, ReferenceIncidentType.MISSING_PERSON}
        else context.occupants
    )
    if incident_type in {
        ReferenceIncidentType.LEVEE_INSPECTION,
        ReferenceIncidentType.INFORMATION_NEED,
        ReferenceIncidentType.HAZARD_RESPONSE,
    }:
        affected = ()
    return ReferenceTruthIncident(
        truth_incident_id=f"RI-{candidate_digest[:16]}",
        incident_type=incident_type,
        episode_key=episode_key,
        onset_s=context.physical.at_s,
        scheduled_resolution_s=context.physical.at_s + duration_s,
        island_id=context.structure.island_id,
        truth_structure_id=context.structure.truth_structure_id,
        infrastructure_id=(
            "SIM-RD407-WEST-01" if incident_type == ReferenceIncidentType.LEVEE_INSPECTION else None
        ),
        affected_truth_person_ids=tuple(sorted(item.truth_person_id for item in affected)),
        location_easting_mm=context.structure.location.easting_mm_epsg26910,
        location_northing_mm=context.structure.location.northing_mm_epsg26910,
        service_requirement=ReferenceServiceRequirement(
            capability=capability,
            service_units=service_units,
            deterministic_service_duration_s=duration_s,
        ),
        severity_micros=max(1, severity_micros),
    )


def generate_reference_truth(
    physical: ReferencePhysicalScenario,
    exposure: ReferenceExposureScenario,
    *,
    seed: int,
) -> ReferenceTruthScenario:
    """Generate truth before observations using development-only intercepts."""

    people_by_home: dict[str, list[ReferenceSyntheticPerson]] = defaultdict(list)
    for person in exposure.people:
        people_by_home[person.home_structure_id].append(person)
    sample_by_time = {sample.at_s: sample for sample in physical.samples}
    accumulator = _TruthAccumulator(seed=seed)
    incident_types = tuple(ReferenceIncidentType)
    levee_anchor_structure_id = next(
        item.truth_structure_id for item in exposure.structures if item.island_id == "ISL-01"
    )
    for at_s in range(-172_800, 345_600, _CANDIDATE_TICK_S):
        sample = sample_by_time[at_s]
        for structure in exposure.structures:
            home_people = tuple(people_by_home[structure.truth_structure_id])
            occupants = tuple(
                person
                for person in home_people
                if _person_at(person, at_s) == structure.truth_structure_id
            )
            away_people = tuple(person for person in home_people if person not in occupants)
            for incident_type in incident_types:
                if (
                    incident_type == ReferenceIncidentType.LEVEE_INSPECTION
                    and structure.truth_structure_id != levee_anchor_structure_id
                ):
                    continue
                context = _CandidateContext(
                    seed=seed,
                    physical=sample,
                    structure=structure,
                    occupants=occupants,
                    away_people=away_people,
                    incident_type=incident_type,
                )
                eligible, probability, severity, signature = _eligible_and_factors(context)
                accumulator.observe(
                    context,
                    eligible=eligible,
                    probability=probability,
                    severity=severity,
                    signature=signature,
                )
    accumulator.finish()
    accumulator.incidents.sort(key=lambda item: (item.onset_s, item.truth_incident_id))
    accumulator.audit.sort(
        key=lambda item: (item.eligible_start_s, item.incident_type.value, item.anchor_id)
    )
    body = {
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "schema_version": "delta-reference-ground-truth-v1",
        "coefficient_version": "delta-reference-truth-development-coefficients-v1",
        "scientific_status": "development-coefficients-not-frozen-for-validation",
        "seed": seed,
        "incidents": [item.model_dump(mode="json") for item in accumulator.incidents],
        "candidate_audit": [item.model_dump(mode="json") for item in accumulator.audit],
    }
    return ReferenceTruthScenario(
        **body,
        truth_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )
