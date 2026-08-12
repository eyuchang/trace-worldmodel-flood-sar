"""Generate causal Reference incident episodes from physical state and exposure."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Literal

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
_PROBABILITY_DENOMINATOR = 10**24

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


@dataclass(frozen=True)
class _StructureTickState:
    """Factors shared by every incident type at one structure/tick."""

    physical: ReferencePhysicalSample
    structure: ReferenceSyntheticStructure
    occupants: tuple[ReferenceSyntheticPerson, ...]
    away_people: tuple[ReferenceSyntheticPerson, ...]
    hazard_micros: int
    maximum_vulnerability_micros: int
    access_impaired: bool
    occupant_signature: str
    away_signature: str


@dataclass(frozen=True)
class _IncidentFactors:
    eligible: bool
    probability_numerator_factor: int
    severity_micros: int
    subject_signature: str


@dataclass(frozen=True)
class ReferenceTruthFitInterval:
    """Intercept interval producing one evaluation incident from one episode."""

    incident_type: ReferenceIncidentType
    lower_intercept_inclusive: int
    upper_intercept_exclusive: int | None


@dataclass(frozen=True)
class ReferenceTruthFitSeedSummary:
    """Compact sufficient statistics for one spent development world."""

    seed: int
    eligible_episode_count: int
    evaluation_intervals: tuple[ReferenceTruthFitInterval, ...]


@dataclass(frozen=True)
class _CandidateAttemptMaterial:
    """Unvalidated hot-path representation converted once per completed episode."""

    candidate_digest: str
    at_s: int
    probability_micros: int
    draw_micros: int
    disposition: Literal["draw-rejected", "accepted-new-episode"]

    def body(self) -> dict[str, object]:
        return {
            "candidate_digest": self.candidate_digest,
            "at_s": self.at_s,
            "probability_micros": self.probability_micros,
            "draw_micros": self.draw_micros,
            "disposition": self.disposition,
        }


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
    representative_attempt: _CandidateAttemptMaterial | None = None
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
        return ReferenceIncidentCandidateAttempt(**self.representative_attempt.body())

    def record(self, attempt: _CandidateAttemptMaterial) -> None:
        attempt_bytes = canonical_json_bytes(attempt.body())
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
        probability: int,
        severity: int,
        signature: str,
    ) -> None:
        anchor_key = (context.incident_type, _anchor_id(context))
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

    def close_ineligible(
        self,
        incident_type: ReferenceIncidentType,
        anchor_id: str,
        at_s: int,
    ) -> None:
        """Close a previously eligible episode without constructing a candidate context."""

        self._close((incident_type, anchor_id), at_s)

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
    ) -> _CandidateAttemptMaterial:
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
        return _CandidateAttemptMaterial(
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


@dataclass
class _FitEpisodeDraft:
    incident_type: ReferenceIncidentType
    burn_in_minimum_intercept: int | None = None
    evaluation_minimum_intercept: int | None = None

    def record(self, at_s: int, minimum_intercept: int) -> None:
        if at_s < 0:
            current = self.burn_in_minimum_intercept
            self.burn_in_minimum_intercept = (
                minimum_intercept if current is None else min(current, minimum_intercept)
            )
        else:
            current = self.evaluation_minimum_intercept
            self.evaluation_minimum_intercept = (
                minimum_intercept if current is None else min(current, minimum_intercept)
            )

    def evaluation_interval(self) -> ReferenceTruthFitInterval | None:
        lower = self.evaluation_minimum_intercept
        upper = self.burn_in_minimum_intercept
        if lower is None or (upper is not None and lower >= upper):
            return None
        return ReferenceTruthFitInterval(
            incident_type=self.incident_type,
            lower_intercept_inclusive=lower,
            upper_intercept_exclusive=upper,
        )


@dataclass
class _FitAccumulator:
    seed: int
    episode_state: dict[tuple[ReferenceIncidentType, str], tuple[str, _FitEpisodeDraft]] = field(
        default_factory=dict
    )
    intervals: list[ReferenceTruthFitInterval] = field(default_factory=list)
    eligible_episode_count: int = 0

    def observe(
        self,
        incident_type: ReferenceIncidentType,
        anchor_id: str,
        signature: str,
        at_s: int,
        factor: int,
        structure_id: str,
    ) -> None:
        key = (incident_type, anchor_id)
        previous = self.episode_state.get(key)
        if previous is None or previous[0] != signature:
            self._close(key)
            draft = _FitEpisodeDraft(incident_type=incident_type)
            self.episode_state[key] = (signature, draft)
            self.eligible_episode_count += 1
        else:
            draft = previous[1]
        draw = uniform_micros(
            self.seed,
            "delta-reference-randomness-v1",
            "truth-candidate-draw",
            at_s,
            incident_type.value,
            structure_id,
        )
        draft.record(at_s, _minimum_accepting_intercept(draw, factor))

    def close_ineligible(
        self,
        incident_type: ReferenceIncidentType,
        anchor_id: str,
    ) -> None:
        self._close((incident_type, anchor_id))

    def _close(self, key: tuple[ReferenceIncidentType, str]) -> None:
        completed = self.episode_state.pop(key, None)
        if completed is None:
            return
        interval = completed[1].evaluation_interval()
        if interval is not None:
            self.intervals.append(interval)

    def finish(self) -> ReferenceTruthFitSeedSummary:
        for key in tuple(self.episode_state):
            self._close(key)
        return ReferenceTruthFitSeedSummary(
            seed=self.seed,
            eligible_episode_count=self.eligible_episode_count,
            evaluation_intervals=tuple(
                sorted(
                    self.intervals,
                    key=lambda item: (
                        item.incident_type.value,
                        item.lower_intercept_inclusive,
                        item.upper_intercept_exclusive or 2**63,
                    ),
                )
            ),
        )


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


def _subjects_signature(
    people: Iterable[ReferenceSyntheticPerson],
    cache: dict[tuple[str, ...], str] | None = None,
) -> str:
    ids = tuple(sorted(item.truth_person_id for item in people))
    if cache is None:
        return hashlib.sha256(canonical_json_bytes(ids)).hexdigest()[:16]
    cached = cache.get(ids)
    if cached is None:
        cached = hashlib.sha256(canonical_json_bytes(ids)).hexdigest()[:16]
        cache[ids] = cached
    return cached


def _person_centered_factors(
    state: _StructureTickState,
    incident_type: ReferenceIncidentType,
) -> tuple[bool, int, int | None]:
    occupants = state.occupants
    away_people = state.away_people
    hazard = state.hazard_micros
    access_impaired = state.access_impaired
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


def _eligible_and_factors(
    state: _StructureTickState,
    incident_type: ReferenceIncidentType,
) -> _IncidentFactors:
    sample = state.physical
    structure = state.structure
    hazard = state.hazard_micros
    maximum_vulnerability = state.maximum_vulnerability_micros
    access_impaired = state.access_impaired
    eligible, subject_factor, person_access_factor = _person_centered_factors(
        state,
        incident_type,
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
    subject_signature = (
        state.away_signature
        if incident_type
        in {ReferenceIncidentType.VEHICLE_RESCUE, ReferenceIncidentType.MISSING_PERSON}
        else state.occupant_signature
    )
    factor = (
        hazard * max(50_000, subject_factor) * max(50_000, maximum_vulnerability) * access_factor
    )
    return _IncidentFactors(
        eligible=eligible,
        probability_numerator_factor=factor,
        severity_micros=hazard,
        subject_signature=subject_signature,
    )


def _probability_micros(intercept_micros: int, factor: int) -> int:
    """Use integer half-up rounding for auditable fixed-point probabilities."""

    rounded = (intercept_micros * factor + _PROBABILITY_DENOMINATOR // 2) // (
        _PROBABILITY_DENOMINATOR
    )
    return min(1_000_000, rounded)


def _minimum_accepting_intercept(draw_micros: int, factor: int) -> int:
    """Invert the fixed-point probability exactly for one keyed draw."""

    required = (draw_micros + 1) * _PROBABILITY_DENOMINATOR - _PROBABILITY_DENOMINATOR // 2
    return max(0, (required + factor - 1) // factor)


def _structure_tick_state(
    physical: ReferencePhysicalSample,
    structure: ReferenceSyntheticStructure,
    home_people: tuple[ReferenceSyntheticPerson, ...],
    *,
    hazard_micros: int,
    access_impaired: bool,
    signature_cache: dict[tuple[str, ...], str],
) -> _StructureTickState:
    occupant_ids = {
        person.truth_person_id
        for person in home_people
        if _person_at(person, physical.at_s) == structure.truth_structure_id
    }
    occupants = tuple(person for person in home_people if person.truth_person_id in occupant_ids)
    away_people = tuple(
        person for person in home_people if person.truth_person_id not in occupant_ids
    )
    return _StructureTickState(
        physical=physical,
        structure=structure,
        occupants=occupants,
        away_people=away_people,
        hazard_micros=hazard_micros,
        maximum_vulnerability_micros=max(
            (person.vulnerability_micros for person in home_people),
            default=structure.vulnerability_micros,
        ),
        access_impaired=access_impaired,
        occupant_signature=_subjects_signature(occupants, signature_cache),
        away_signature=_subjects_signature(away_people, signature_cache),
    )


def _iter_structure_tick_states(
    physical: ReferencePhysicalScenario,
    exposure: ReferenceExposureScenario,
) -> Iterator[tuple[int, ReferenceSyntheticStructure, _StructureTickState, bool]]:
    people_by_home: dict[str, list[ReferenceSyntheticPerson]] = defaultdict(list)
    for person in exposure.people:
        people_by_home[person.home_structure_id].append(person)
    sample_by_time = {sample.at_s: sample for sample in physical.samples}
    signature_cache: dict[tuple[str, ...], str] = {}
    levee_anchor_structure_id = next(
        item.truth_structure_id for item in exposure.structures if item.island_id == "ISL-01"
    )
    for at_s in range(-172_800, 345_600, _CANDIDATE_TICK_S):
        sample = sample_by_time[at_s]
        hazard_by_island = {
            f"ISL-{index:02d}": _hazard_micros(sample, f"ISL-{index:02d}") for index in range(1, 9)
        }
        access_impaired = any(item.status != "open" for item in sample.crossings)
        for structure in exposure.structures:
            yield (
                at_s,
                structure,
                _structure_tick_state(
                    sample,
                    structure,
                    tuple(people_by_home[structure.truth_structure_id]),
                    hazard_micros=hazard_by_island[structure.island_id],
                    access_impaired=access_impaired,
                    signature_cache=signature_cache,
                ),
                structure.truth_structure_id == levee_anchor_structure_id,
            )


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


def build_reference_truth_fit_seed_summary(
    physical: ReferencePhysicalScenario,
    exposure: ReferenceExposureScenario,
    *,
    seed: int,
) -> ReferenceTruthFitSeedSummary:
    """Reduce one spent development world to exact intercept acceptance intervals."""

    accumulator = _FitAccumulator(seed=seed)
    incident_types = tuple(ReferenceIncidentType)
    for _at_s, structure, state, is_levee_anchor in _iter_structure_tick_states(
        physical,
        exposure,
    ):
        for incident_type in incident_types:
            if incident_type == ReferenceIncidentType.LEVEE_INSPECTION and not is_levee_anchor:
                continue
            anchor_id = (
                "SIM-RD407-WEST-01"
                if incident_type == ReferenceIncidentType.LEVEE_INSPECTION
                else structure.truth_structure_id
            )
            factors = _eligible_and_factors(state, incident_type)
            if not factors.eligible:
                accumulator.close_ineligible(incident_type, anchor_id)
                continue
            accumulator.observe(
                incident_type,
                anchor_id,
                factors.subject_signature,
                state.physical.at_s,
                factors.probability_numerator_factor,
                structure.truth_structure_id,
            )
    return accumulator.finish()


def generate_reference_truth(
    physical: ReferencePhysicalScenario,
    exposure: ReferenceExposureScenario,
    *,
    seed: int,
) -> ReferenceTruthScenario:
    """Generate truth before observations using development-only intercepts."""

    accumulator = _TruthAccumulator(seed=seed)
    incident_types = tuple(ReferenceIncidentType)
    for at_s, structure, state, is_levee_anchor in _iter_structure_tick_states(
        physical,
        exposure,
    ):
        for incident_type in incident_types:
            if incident_type == ReferenceIncidentType.LEVEE_INSPECTION and not is_levee_anchor:
                continue
            factors = _eligible_and_factors(state, incident_type)
            if not factors.eligible:
                accumulator.close_ineligible(
                    incident_type,
                    (
                        "SIM-RD407-WEST-01"
                        if incident_type == ReferenceIncidentType.LEVEE_INSPECTION
                        else structure.truth_structure_id
                    ),
                    at_s,
                )
                continue
            accumulator.observe(
                _CandidateContext(
                    seed=seed,
                    physical=state.physical,
                    structure=structure,
                    occupants=state.occupants,
                    away_people=state.away_people,
                    incident_type=incident_type,
                ),
                probability=_probability_micros(
                    _DEVELOPMENT_INTERCEPTS_MICROS[incident_type],
                    factors.probability_numerator_factor,
                ),
                severity=factors.severity_micros,
                signature=factors.subject_signature,
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
