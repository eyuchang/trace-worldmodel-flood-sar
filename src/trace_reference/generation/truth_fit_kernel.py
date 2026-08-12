"""Allocation-bounded exact kernel for Reference truth sufficient statistics."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field

from trace_jepa.support import canonical_json_bytes
from trace_reference.domain.exposure import (
    ReferenceExposureScenario,
    ReferenceSyntheticPerson,
    ReferenceSyntheticStructure,
)
from trace_reference.domain.physical import ReferencePhysicalSample, ReferencePhysicalScenario
from trace_reference.domain.truth import ReferenceIncidentType

from .randomness import encode_keyed_parts, uniform_micros_encoded
from .truth_fit_types import ReferenceTruthFitInterval, ReferenceTruthFitSeedSummary
from .truth_probability import minimum_accepting_intercept

_CANDIDATE_TICK_S = 1_800
_NAMESPACE = "delta-reference-randomness-v1"
_DRAW_STAGE = encode_keyed_parts("truth-candidate-draw")


@dataclass
class _HomeState:
    structure: ReferenceSyntheticStructure
    maximum_vulnerability_micros: int
    occupant_ids: set[str] = field(default_factory=set)
    away_ids: set[str] = field(default_factory=set)
    dependent_occupants: set[str] = field(default_factory=set)
    vulnerable_occupants: set[str] = field(default_factory=set)
    occupant_signature: str = ""
    away_signature: str = ""

    def refresh_signatures(self) -> None:
        self.occupant_signature = _signature(self.occupant_ids)
        self.away_signature = _signature(self.away_ids)


@dataclass(frozen=True)
class _PersonState:
    person_id: str
    home_index: int
    dependent: bool
    vulnerable: bool


@dataclass
class _EpisodeState:
    incident_type: ReferenceIncidentType
    signature: str
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

    def interval(self) -> ReferenceTruthFitInterval | None:
        lower = self.evaluation_minimum_intercept
        upper = self.burn_in_minimum_intercept
        if lower is None or (upper is not None and lower >= upper):
            return None
        return ReferenceTruthFitInterval(
            incident_type=self.incident_type,
            lower_intercept_inclusive=lower,
            upper_intercept_exclusive=upper,
        )


@dataclass(frozen=True)
class _FitSlot:
    state_index: int
    incident_type: ReferenceIncidentType
    draw_suffix: bytes


@dataclass(frozen=True)
class _FitTime:
    at_s: int
    encoded: bytes


@dataclass
class _CompactFitAccumulator:
    seed: int
    structure_count: int
    states: list[_EpisodeState | None] = field(init=False)
    intervals: list[ReferenceTruthFitInterval] = field(default_factory=list)
    eligible_episode_count: int = 0

    def __post_init__(self) -> None:
        self.states = [None] * (len(ReferenceIncidentType) * self.structure_count)

    def observe(
        self,
        slot: _FitSlot,
        signature: str,
        time: _FitTime,
        factor: int,
    ) -> None:
        state = self.states[slot.state_index]
        if state is None or state.signature != signature:
            self._close(slot.state_index)
            state = _EpisodeState(incident_type=slot.incident_type, signature=signature)
            self.states[slot.state_index] = state
            self.eligible_episode_count += 1
        draw = uniform_micros_encoded(
            self.seed,
            _NAMESPACE,
            _DRAW_STAGE,
            time.encoded,
            slot.draw_suffix,
        )
        state.record(time.at_s, minimum_accepting_intercept(draw, factor))

    def close(self, slot: _FitSlot) -> None:
        self._close(slot.state_index)

    def _close(self, slot: int) -> None:
        state = self.states[slot]
        if state is None:
            return
        interval = state.interval()
        if interval is not None:
            self.intervals.append(interval)
        self.states[slot] = None

    def finish(self) -> ReferenceTruthFitSeedSummary:
        for slot, state in enumerate(self.states):
            if state is not None:
                self._close(slot)
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


def _signature(person_ids: set[str]) -> str:
    return hashlib.sha256(canonical_json_bytes(tuple(sorted(person_ids)))).hexdigest()[:16]


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


def _home_states(
    exposure: ReferenceExposureScenario,
) -> tuple[
    list[_HomeState],
    dict[int, list[tuple[_PersonState, bool]]],
]:
    home_index = {
        structure.truth_structure_id: index for index, structure in enumerate(exposure.structures)
    }
    people_by_home: dict[int, list[ReferenceSyntheticPerson]] = defaultdict(list)
    for person in exposure.people:
        people_by_home[home_index[person.home_structure_id]].append(person)
    homes = [
        _HomeState(
            structure=structure,
            maximum_vulnerability_micros=max(
                (person.vulnerability_micros for person in people_by_home[index]),
                default=structure.vulnerability_micros,
            ),
        )
        for index, structure in enumerate(exposure.structures)
    ]
    transitions: dict[int, list[tuple[_PersonState, bool]]] = defaultdict(list)
    for index, people in people_by_home.items():
        home_id = homes[index].structure.truth_structure_id
        for person in people:
            state = _PersonState(
                person_id=person.truth_person_id,
                home_index=index,
                dependent=person.medical_dependency != "none",
                vulnerable=(person.mobility != "standard" or person.medical_dependency != "none"),
            )
            for point in person.trajectory:
                transitions[point.at_s].append((state, point.synthetic_structure_id == home_id))
    for changes in transitions.values():
        changes.sort(key=lambda item: item[0].person_id)
    return homes, transitions


def _apply_transitions(
    homes: list[_HomeState],
    transitions: dict[int, list[tuple[_PersonState, bool]]],
    at_s: int,
) -> None:
    changed: set[int] = set()
    for person, at_home in transitions.get(at_s, ()):
        home = homes[person.home_index]
        home.occupant_ids.discard(person.person_id)
        home.away_ids.discard(person.person_id)
        home.dependent_occupants.discard(person.person_id)
        home.vulnerable_occupants.discard(person.person_id)
        if at_home:
            home.occupant_ids.add(person.person_id)
            if person.dependent:
                home.dependent_occupants.add(person.person_id)
            if person.vulnerable:
                home.vulnerable_occupants.add(person.person_id)
        else:
            home.away_ids.add(person.person_id)
        changed.add(person.home_index)
    for index in changed:
        homes[index].refresh_signatures()


def _factor(
    hazard: int,
    subject_factor: int,
    vulnerability: int,
    access_factor: int,
) -> int:
    return (
        hazard
        * max(50_000, min(1_000_000, subject_factor))
        * max(50_000, vulnerability)
        * access_factor
    )


def _observe_or_close(
    accumulator: _CompactFitAccumulator,
    *,
    slot: _FitSlot,
    eligible: bool,
    signature: str,
    time: _FitTime,
    factor: int,
) -> None:
    if eligible:
        accumulator.observe(slot, signature, time, factor)
    else:
        accumulator.close(slot)


def build_reference_truth_fit_seed_summary_optimized(
    physical: ReferencePhysicalScenario,
    exposure: ReferenceExposureScenario,
    *,
    seed: int,
) -> ReferenceTruthFitSeedSummary:
    """Build the exact sufficient statistics with compact mutable state."""

    homes, transitions = _home_states(exposure)
    for home in homes:
        home.refresh_signatures()
    sample_by_time = {sample.at_s: sample for sample in physical.samples}
    structure_count = len(homes)
    accumulator = _CompactFitAccumulator(seed=seed, structure_count=structure_count)
    types = tuple(ReferenceIncidentType)
    slots = {
        (incident_type, structure_index): _FitSlot(
            state_index=type_index * structure_count + structure_index,
            incident_type=incident_type,
            draw_suffix=encode_keyed_parts(
                incident_type.value,
                home.structure.truth_structure_id,
            ),
        )
        for type_index, incident_type in enumerate(types)
        for structure_index, home in enumerate(homes)
    }
    levee_index = next(
        index for index, home in enumerate(homes) if home.structure.island_id == "ISL-01"
    )
    for at_s in range(-172_800, 345_600, _CANDIDATE_TICK_S):
        _apply_transitions(homes, transitions, at_s)
        sample = sample_by_time[at_s]
        time = _FitTime(at_s=at_s, encoded=encode_keyed_parts(at_s))
        access_impaired = any(item.status != "open" for item in sample.crossings)
        hazards = {
            f"ISL-{index:02d}": _hazard_micros(sample, f"ISL-{index:02d}") for index in range(1, 9)
        }
        for structure_index, home in enumerate(homes):
            structure = home.structure
            hazard = hazards[structure.island_id]
            occupants = len(home.occupant_ids)
            away = len(home.away_ids)
            maximum_vulnerability = home.maximum_vulnerability_micros

            stranded = ReferenceIncidentType.STRANDED_STRUCTURE
            _observe_or_close(
                accumulator,
                slot=slots[(stranded, structure_index)],
                eligible=occupants > 0 and hazard >= 450_000,
                signature=home.occupant_signature,
                time=time,
                factor=_factor(
                    hazard,
                    occupants * 170_000,
                    maximum_vulnerability,
                    850_000 if access_impaired else 500_000,
                ),
            )
            vehicle = ReferenceIncidentType.VEHICLE_RESCUE
            _observe_or_close(
                accumulator,
                slot=slots[(vehicle, structure_index)],
                eligible=away > 0 and (access_impaired or hazard >= 350_000),
                signature=home.away_signature,
                time=time,
                factor=_factor(
                    hazard,
                    away * 180_000,
                    maximum_vulnerability,
                    950_000 if access_impaired else 450_000,
                ),
            )
            medical = ReferenceIncidentType.MEDICAL_ACCESS
            dependent = len(home.dependent_occupants)
            _observe_or_close(
                accumulator,
                slot=slots[(medical, structure_index)],
                eligible=dependent > 0 and hazard >= 260_000,
                signature=home.occupant_signature,
                time=time,
                factor=_factor(
                    hazard,
                    dependent * 320_000,
                    maximum_vulnerability,
                    950_000 if access_impaired else 600_000,
                ),
            )
            welfare = ReferenceIncidentType.WELFARE_CHECK
            vulnerable = len(home.vulnerable_occupants)
            _observe_or_close(
                accumulator,
                slot=slots[(welfare, structure_index)],
                eligible=vulnerable > 0 and hazard >= 200_000,
                signature=home.occupant_signature,
                time=time,
                factor=_factor(hazard, vulnerable * 260_000, maximum_vulnerability, 700_000),
            )
            missing = ReferenceIncidentType.MISSING_PERSON
            _observe_or_close(
                accumulator,
                slot=slots[(missing, structure_index)],
                eligible=away > 0 and hazard >= 300_000,
                signature=home.away_signature,
                time=time,
                factor=_factor(
                    hazard,
                    away * 250_000,
                    maximum_vulnerability,
                    850_000 if access_impaired else 600_000,
                ),
            )
            animal = ReferenceIncidentType.ANIMAL_RESCUE
            _observe_or_close(
                accumulator,
                slot=slots[(animal, structure_index)],
                eligible=structure.animal_units > 0 and hazard >= 400_000,
                signature=home.occupant_signature,
                time=time,
                factor=_factor(
                    hazard,
                    structure.animal_units * 180_000,
                    maximum_vulnerability,
                    750_000,
                ),
            )
            information = ReferenceIncidentType.INFORMATION_NEED
            _observe_or_close(
                accumulator,
                slot=slots[(information, structure_index)],
                eligible=at_s >= 0 and (hazard >= 250_000 or access_impaired),
                signature=home.occupant_signature,
                time=time,
                factor=_factor(hazard, 550_000, structure.vulnerability_micros, 700_000),
            )
            hazard_response = ReferenceIncidentType.HAZARD_RESPONSE
            _observe_or_close(
                accumulator,
                slot=slots[(hazard_response, structure_index)],
                eligible=at_s >= 0 and (hazard >= 500_000 or access_impaired),
                signature=home.occupant_signature,
                time=time,
                factor=_factor(
                    hazard,
                    600_000,
                    structure.vulnerability_micros,
                    900_000 if access_impaired else 650_000,
                ),
            )
            if structure_index == levee_index:
                levee = ReferenceIncidentType.LEVEE_INSPECTION
                _observe_or_close(
                    accumulator,
                    slot=slots[(levee, structure_index)],
                    eligible=at_s >= 144_000,
                    signature=home.occupant_signature,
                    time=time,
                    factor=_factor(hazard, 700_000, maximum_vulnerability, 850_000),
                )
    return accumulator.finish()
