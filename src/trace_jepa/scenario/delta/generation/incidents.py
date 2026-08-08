"""Causal incident-candidate generation from exposure and physical state."""

from __future__ import annotations

from dataclasses import dataclass

from trace_jepa.scenario.delta.domain import (
    CrossingState,
    DeltaScenarioConfig,
    LeveeTruth,
    PersonPosition,
    PersonTruth,
    StructureState,
    StructureTruth,
    WeatherSample,
)

INCIDENT_REQUIREMENTS_V7 = {
    "C-STR": ("water_rescue", 2_400),
    "C-VEH": ("road_rescue", 1_500),
    "C-LEV": ("levee_inspection", 1_200),
    "C-MED": ("medical_first_response", 1_200),
    "C-WEL": ("welfare_check", 1_200),
    "C-MIS": ("missing_person_search", 1_500),
}


@dataclass(frozen=True)
class IncidentCandidate:
    """One keyed opportunity for a latent incident, before Bernoulli thinning."""

    structure_id: str
    simulation_time_s: int
    incident_type: str
    person_ids: tuple[str, ...]
    factor: float
    hazard_factor: float
    occupancy_factor: float
    vulnerability_factor: float
    access_factor: float
    causal_mechanism: str
    infrastructure_id: str | None = None


@dataclass(frozen=True)
class CandidateInputs:
    """Typed state required to construct all candidate families."""

    config: DeltaScenarioConfig
    structures: list[StructureTruth]
    states: list[StructureState]
    people: list[PersonTruth]
    positions: list[PersonPosition]
    levees: list[LeveeTruth]
    weather: list[WeatherSample]
    crossing_states: list[CrossingState]


@dataclass(frozen=True)
class CandidateIndex:
    state_by_key: dict[tuple[str, int], StructureState]
    weather_by_time: dict[int, WeatherSample]
    positions_by_person: dict[str, list[PersonPosition]]
    levees_by_key: dict[tuple[str, int], list[LeveeTruth]]
    crossing_by_time: dict[int, list[CrossingState]]
    structures_by_island: dict[str, list[StructureTruth]]


@dataclass(frozen=True)
class SubjectSelection:
    people: list[PersonTruth]
    hazard_factor: float
    occupancy_factor: float
    vulnerability_factor: float
    access_factor: float
    causal_mechanism: str


@dataclass(frozen=True)
class SubjectSelectionInput:
    incident_type: str
    state: StructureState
    present: list[PersonTruth]
    away: list[PersonTruth]
    generic_hazard: float
    route_factor: float
    rain_fraction: float


def _position_at(
    person: PersonTruth,
    positions_by_person: dict[str, list[PersonPosition]],
    simulation_time_s: int,
) -> PersonPosition:
    eligible = [
        item
        for item in positions_by_person[person.person_id]
        if item.simulation_time_s <= simulation_time_s
    ]
    if not eligible:
        raise RuntimeError(f"person trajectory has no initial state: {person.person_id}")
    return eligible[-1]


def _index(inputs: CandidateInputs) -> CandidateIndex:
    positions_by_person: dict[str, list[PersonPosition]] = {
        person.person_id: [] for person in inputs.people
    }
    for position in inputs.positions:
        positions_by_person[position.person_id].append(position)
    for values in positions_by_person.values():
        values.sort(key=lambda item: item.simulation_time_s)
    levees_by_key: dict[tuple[str, int], list[LeveeTruth]] = {}
    for levee in inputs.levees:
        levees_by_key.setdefault((levee.island_id, levee.simulation_time_s), []).append(levee)
    crossing_by_time: dict[int, list[CrossingState]] = {}
    for crossing in inputs.crossing_states:
        crossing_by_time.setdefault(crossing.simulation_time_s, []).append(crossing)
    island_ids = {item.island_id for item in inputs.structures}
    return CandidateIndex(
        state_by_key={(item.structure_id, item.simulation_time_s): item for item in inputs.states},
        weather_by_time={item.simulation_time_s: item for item in inputs.weather},
        positions_by_person=positions_by_person,
        levees_by_key=levees_by_key,
        crossing_by_time=crossing_by_time,
        structures_by_island={
            island_id: sorted(
                (item for item in inputs.structures if item.island_id == island_id),
                key=lambda item: item.structure_id,
            )
            for island_id in island_ids
        },
    )


def _levee_candidates(
    inputs: CandidateInputs,
    index: CandidateIndex,
    simulation_time_s: int,
    rain_fraction: float,
    wind_fraction: float,
) -> list[IncidentCandidate]:
    candidates: list[IncidentCandidate] = []
    for island_id, island_structures in index.structures_by_island.items():
        current = sorted(
            index.levees_by_key[(island_id, simulation_time_s)],
            key=lambda item: item.segment_id,
        )
        for levee_index, levee in enumerate(current):
            prior_time = simulation_time_s - inputs.config.timeline.tick_s
            prior_state = "none"
            if prior_time >= 0:
                prior_state = next(
                    item.seepage_state
                    for item in index.levees_by_key[(island_id, prior_time)]
                    if item.segment_id == levee.segment_id
                )
            if levee.seepage_state == "none" or levee.seepage_state == prior_state:
                continue
            anchor = island_structures[levee_index % len(island_structures)]
            hazard_factor = (0.50 + 0.30 * rain_fraction + 0.10 * wind_fraction) * 1.4
            candidates.append(
                IncidentCandidate(
                    structure_id=anchor.structure_id,
                    simulation_time_s=simulation_time_s,
                    incident_type="C-LEV",
                    person_ids=(),
                    factor=hazard_factor,
                    hazard_factor=hazard_factor,
                    occupancy_factor=1.0,
                    vulnerability_factor=1.0,
                    access_factor=1.0,
                    causal_mechanism="new-visible-nonbreach-levee-anomaly-v1",
                    infrastructure_id=levee.segment_id,
                )
            )
    return candidates


def _present_people(
    inputs: CandidateInputs,
    index: CandidateIndex,
    structure_id: str,
    simulation_time_s: int,
) -> tuple[list[PersonTruth], list[PersonTruth]]:
    present = [
        person
        for person in inputs.people
        if _position_at(person, index.positions_by_person, simulation_time_s).structure_id
        == structure_id
    ]
    away = [
        person
        for person in present
        if _position_at(person, index.positions_by_person, simulation_time_s).state
        == "away_from_home"
    ]
    return present, away


def _select_subjects(request: SubjectSelectionInput) -> SubjectSelection | None:
    incident_type = request.incident_type
    state = request.state
    present = request.present
    away = request.away
    limited = [item for item in present if item.mobility == "limited"]
    medical = [item for item in present if item.medical_dependency != "none"]
    occupancy = len(present) / 4.0
    vulnerability = 1.0 + 0.35 * len(limited) + 0.45 * len(medical)
    access = 1.35 if state.access_state == "impaired" else 0.65
    if incident_type == "C-STR" and state.flood_state == "shallow_ponding" and present:
        return SubjectSelection(
            present,
            request.generic_hazard * (1.2 + request.rain_fraction),
            occupancy,
            vulnerability,
            access,
            "occupied-shallow-ponding-exposure-v1",
        )
    if incident_type == "C-VEH" and state.access_state == "impaired" and away:
        return SubjectSelection(
            away,
            request.generic_hazard * request.route_factor,
            len(away) / 2.0,
            vulnerability,
            access,
            "impaired-access-during-deterministic-movement-v1",
        )
    if incident_type == "C-MED" and medical:
        return SubjectSelection(
            medical,
            request.generic_hazard,
            float(len(medical)),
            1.0 + 0.75 * len(medical),
            access,
            "occupied-medical-dependency-under-hazard-v1",
        )
    vulnerable = [
        item for item in present if item.mobility == "limited" or item.medical_dependency != "none"
    ]
    if incident_type == "C-WEL" and vulnerable:
        return SubjectSelection(
            vulnerable,
            request.generic_hazard,
            float(len(vulnerable)),
            1.0 + 0.5 * len(vulnerable),
            access,
            "limited-mobility-or-medical-welfare-concern-v1",
        )
    if incident_type == "C-MIS" and away:
        return SubjectSelection(
            away,
            request.generic_hazard,
            float(len(away)),
            1.0 + 0.25 * len(away),
            access,
            "deterministic-away-from-home-movement-v1",
        )
    return None


def _structure_candidates(
    inputs: CandidateInputs,
    index: CandidateIndex,
    simulation_time_s: int,
    rain_fraction: float,
    wind_fraction: float,
    route_factor: float,
) -> list[IncidentCandidate]:
    candidates: list[IncidentCandidate] = []
    generic_hazard = 0.50 + 0.30 * rain_fraction + 0.10 * wind_fraction
    for structure in inputs.structures:
        state = index.state_by_key[(structure.structure_id, simulation_time_s)]
        present, away = _present_people(inputs, index, structure.structure_id, simulation_time_s)
        for incident_type in INCIDENT_REQUIREMENTS_V7:
            if incident_type == "C-LEV":
                continue
            selected = _select_subjects(
                SubjectSelectionInput(
                    incident_type=incident_type,
                    state=state,
                    present=present,
                    away=away,
                    generic_hazard=generic_hazard,
                    route_factor=route_factor,
                    rain_fraction=rain_fraction,
                )
            )
            if selected is None:
                continue
            factor = (
                max(0.0, selected.hazard_factor)
                * max(0.0, selected.occupancy_factor)
                * max(0.0, selected.vulnerability_factor)
                * max(0.0, selected.access_factor)
            )
            if factor == 0.0:
                continue
            candidates.append(
                IncidentCandidate(
                    structure_id=structure.structure_id,
                    simulation_time_s=simulation_time_s,
                    incident_type=incident_type,
                    person_ids=tuple(item.person_id for item in selected.people),
                    factor=factor,
                    hazard_factor=selected.hazard_factor,
                    occupancy_factor=selected.occupancy_factor,
                    vulnerability_factor=selected.vulnerability_factor,
                    access_factor=selected.access_factor,
                    causal_mechanism=selected.causal_mechanism,
                )
            )
    return candidates


def incident_candidates(inputs: CandidateInputs) -> list[IncidentCandidate]:
    """Generate all causally eligible keyed incident opportunities."""

    index = _index(inputs)
    candidates: list[IncidentCandidate] = []
    timeline = range(0, inputs.config.timeline.duration_s, inputs.config.timeline.tick_s)
    for simulation_time_s in timeline:
        sample = index.weather_by_time[simulation_time_s]
        rain_fraction = sample.rain_milli_inches_per_hour / 210.0
        wind_fraction = sample.wind_milli_knots / 22_000.0
        crossings = index.crossing_by_time[simulation_time_s]
        route_factor = sum(item.travel_time_s for item in crossings) / max(
            1, len(crossings) * 1_800
        )
        candidates.extend(
            _levee_candidates(inputs, index, simulation_time_s, rain_fraction, wind_fraction)
        )
        candidates.extend(
            _structure_candidates(
                inputs,
                index,
                simulation_time_s,
                rain_fraction,
                wind_fraction,
                route_factor,
            )
        )
    return candidates
