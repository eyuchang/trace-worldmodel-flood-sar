from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from trace_jepa.scenario.delta.geography_models import GeographyCatalog, LinearRing
from trace_jepa.scenario.delta.models import (
    CrossingState,
    DeltaScenarioConfig,
    GroundTruth,
    IncidentTruth,
    LeveeTruth,
    PersonPosition,
    PersonTruth,
    StructureState,
    StructureTruth,
    WeatherSample,
)
from trace_jepa.scenario.delta.randomness import KeyedRandom

INCIDENT_REQUIREMENTS_V7 = {
    "C-STR": ("water_rescue", 2_400),
    "C-VEH": ("road_rescue", 1_500),
    "C-LEV": ("levee_inspection", 1_200),
    "C-MED": ("medical_first_response", 1_200),
    "C-WEL": ("welfare_check", 1_200),
    "C-MIS": ("missing_person_search", 1_500),
}

# These are updated only by the development-seed calibration procedure. The
# committed calibration record binds the exact values and target taxonomy.
TYPE_INTERCEPTS_V1 = {
    "C-STR": 0.003802684544028396,
    "C-VEH": 0.010590227133044604,
    "C-LEV": 0.24001430962351156,
    "C-MED": 0.005440831471262897,
    "C-WEL": 0.003542798578404174,
    "C-MIS": 0.00872872306670035,
}


@dataclass(frozen=True)
class IncidentCandidate:
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


def _point_inside_ring(easting_mm: int, northing_mm: int, ring: LinearRing) -> bool:
    inside = False
    previous = ring.points[-1]
    for current in ring.points:
        crosses = (current.northing_mm > northing_mm) != (previous.northing_mm > northing_mm)
        if crosses:
            intersection = current.easting_mm + (
                (northing_mm - current.northing_mm)
                * (previous.easting_mm - current.easting_mm)
                // (previous.northing_mm - current.northing_mm)
            )
            if easting_mm < intersection:
                inside = not inside
        previous = current
    return inside


def _sample_points(
    ring: LinearRing,
    count: int,
    keyed: KeyedRandom,
    island_id: str,
    *,
    minimum_separation_m: int,
    required_containment_rings: list[LinearRing] | None,
    high_vulnerability: bool,
) -> list[tuple[int, int]]:
    eastings = [point.easting_mm for point in ring.points]
    northings = [point.northing_mm for point in ring.points]
    minimum_easting, maximum_easting = min(eastings), max(eastings)
    minimum_northing, maximum_northing = min(northings), max(northings)
    separation_squared = (minimum_separation_m * 1000) ** 2
    points: list[tuple[int, int]] = []
    for attempt in range(100_000):
        candidate = (
            keyed.randint(
                minimum_easting,
                maximum_easting,
                "structure-placement",
                island_id,
                attempt,
                "easting",
            ),
            keyed.randint(
                minimum_northing,
                maximum_northing,
                "structure-placement",
                island_id,
                attempt,
                "northing",
            ),
        )
        if not _point_inside_ring(*candidate, ring):
            continue
        if required_containment_rings and not any(
            _point_inside_ring(*candidate, required_ring)
            for required_ring in required_containment_rings
        ):
            continue
        if high_vulnerability:
            north_fraction = (candidate[1] - minimum_northing) / max(
                1, maximum_northing - minimum_northing
            )
            acceptance = 0.45 + 0.45 * (1.0 - north_fraction)
            if (
                keyed.uniform("structure-placement", island_id, attempt, "exposure-bias")
                >= acceptance
            ):
                continue
        if any(
            (candidate[0] - point[0]) ** 2 + (candidate[1] - point[1]) ** 2 < separation_squared
            for point in points
        ):
            continue
        points.append(candidate)
        if len(points) == count:
            return points
    raise RuntimeError("could not place v7 synthetic structures within the frozen polygons")


def _structures(
    geography: GeographyCatalog,
    keyed: KeyedRandom,
    high_vulnerability: bool,
) -> list[StructureTruth]:
    community = next(item for item in geography.communities if item.community_id == "TWN-01")
    andrus = next(item for item in geography.islands if item.island_id == "ISL-01")
    brannan = next(item for item in geography.islands if item.island_id == "ISL-02")
    andrus_points = _sample_points(
        community.geometry.polygons[0],
        12,
        keyed,
        "ISL-01",
        minimum_separation_m=55,
        required_containment_rings=andrus.geometry.polygons,
        high_vulnerability=high_vulnerability,
    )
    brannan_points = _sample_points(
        brannan.geometry.polygons[0],
        3,
        keyed,
        "ISL-02",
        minimum_separation_m=200,
        required_containment_rings=None,
        high_vulnerability=high_vulnerability,
    )
    return [
        StructureTruth(
            structure_id=f"STR-{index + 1:03d}",
            community_id="TWN-01" if index < 12 else "OUTSIDE-TWN-01",
            island_id="ISL-01" if index < 12 else "ISL-02",
            easting_mm=easting_mm,
            northing_mm=northing_mm,
            placement_profile=(
                "keyed-vulnerability-biased-synthetic-placement-v1"
                if high_vulnerability
                else "keyed-government-footprint-synthetic-placement-v1"
            ),
        )
        for index, (easting_mm, northing_mm) in enumerate([*andrus_points, *brannan_points])
    ]


def _people_and_positions(
    config: DeltaScenarioConfig,
    structures: list[StructureTruth],
    keyed: KeyedRandom,
    high_vulnerability: bool,
) -> tuple[list[PersonTruth], list[PersonPosition]]:
    andrus_count = 48 if high_vulnerability else 52
    languages = ("en", "en", "en", "en", "es", "tl")
    people: list[PersonTruth] = []
    positions: list[PersonPosition] = []
    for index in range(config.extent.roster_size):
        person_id = f"PER-{index + 1:03d}"
        island_structures = structures[:12] if index < andrus_count else structures[12:]
        home = island_structures[
            keyed.choice_index(len(island_structures), "person", person_id, "home")
        ]
        limited_threshold = 0.22 if high_vulnerability else 0.12
        medical_threshold = 0.14 if high_vulnerability else 0.08
        person = PersonTruth(
            person_id=person_id,
            home_structure_id=home.structure_id,
            mobility=(
                "limited"
                if keyed.bernoulli(limited_threshold, "person", person_id, "mobility")
                else "ambulatory"
            ),
            medical_dependency=(
                "oxygen"
                if keyed.bernoulli(medical_threshold, "person", person_id, "medical")
                else "none"
            ),
            preferred_language=languages[
                keyed.choice_index(len(languages), "person", person_id, "language")
            ],
        )
        people.append(person)
        positions.append(
            PersonPosition(
                person_id=person_id,
                simulation_time_s=0,
                structure_id=home.structure_id,
                state="at_home",
            )
        )
        movement_probability = 0.30 if high_vulnerability else 0.20
        if keyed.bernoulli(movement_probability, "person", person_id, "moves"):
            destination_candidates = [
                item for item in structures if item.structure_id != home.structure_id
            ]
            destination = destination_candidates[
                keyed.choice_index(len(destination_candidates), "person", person_id, "destination")
            ]
            departure = config.timeline.tick_s * keyed.randint(
                0,
                48,
                "person",
                person_id,
                "departure-tick",
            )
            returned = min(config.timeline.duration_s, departure + 7_200)
            positions.extend(
                [
                    PersonPosition(
                        person_id=person_id,
                        simulation_time_s=departure,
                        structure_id=destination.structure_id,
                        state="away_from_home",
                    ),
                    PersonPosition(
                        person_id=person_id,
                        simulation_time_s=returned,
                        structure_id=home.structure_id,
                        state="returned_home",
                    ),
                ]
            )
    return people, sorted(positions, key=lambda item: (item.person_id, item.simulation_time_s))


def _structure_states(
    config: DeltaScenarioConfig,
    structures: list[StructureTruth],
    weather: list[WeatherSample],
    keyed: KeyedRandom,
) -> list[StructureState]:
    weather_by_time = {item.simulation_time_s: item for item in weather}
    states: list[StructureState] = []
    for structure in structures:
        drainage_threshold = keyed.randint(
            35,
            115,
            "structure-physical-susceptibility",
            structure.structure_id,
        )
        for simulation_time_s in range(0, config.timeline.duration_s + 1, config.timeline.tick_s):
            recent_rain = max(
                weather_by_time[recent_time].rain_milli_inches_per_hour
                for recent_time in range(
                    max(0, simulation_time_s - 7_200),
                    simulation_time_s + 1,
                    config.timeline.tick_s,
                )
            )
            ponding = recent_rain >= drainage_threshold
            states.append(
                StructureState(
                    structure_id=structure.structure_id,
                    simulation_time_s=simulation_time_s,
                    flood_state="shallow_ponding" if ponding else "dry",
                    access_state="impaired" if ponding else "open",
                )
            )
    return states


def _levees(
    config: DeltaScenarioConfig,
    weather: list[WeatherSample],
) -> list[LeveeTruth]:
    weather_by_time = {item.simulation_time_s: item for item in weather}

    def seepage_state(rain_milli_inches_per_hour: int) -> str:
        if rain_milli_inches_per_hour >= 200:
            return "visible_increasing_seepage"
        if rain_milli_inches_per_hour >= 140:
            return "visible_minor_seepage"
        if rain_milli_inches_per_hour >= 100:
            return "visible_recession_monitoring"
        return "none"

    return [
        LeveeTruth(
            segment_id=f"{district}-SMALL-01",
            island_id=island_id,
            district_id=district,
            simulation_time_s=simulation_time_s,
            condition="fair",
            seepage_state=seepage_state(
                weather_by_time[simulation_time_s].rain_milli_inches_per_hour
            ),
            breach=False,
        )
        for district, island_id in (
            ("RD-407", "ISL-01"),
            ("RD-317", "ISL-01"),
            ("RD-556", "ISL-01"),
            ("RD-2067", "ISL-02"),
        )
        for simulation_time_s in range(0, config.timeline.duration_s + 1, config.timeline.tick_s)
    ]


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


def incident_candidates_v7(
    config: DeltaScenarioConfig,
    structures: list[StructureTruth],
    states: list[StructureState],
    people: list[PersonTruth],
    positions: list[PersonPosition],
    levees: list[LeveeTruth],
    weather: list[WeatherSample],
    crossing_states: list[CrossingState],
) -> list[IncidentCandidate]:
    state_by_key = {(item.structure_id, item.simulation_time_s): item for item in states}
    weather_by_time = {item.simulation_time_s: item for item in weather}
    positions_by_person: dict[str, list[PersonPosition]] = {
        person.person_id: [] for person in people
    }
    for position in positions:
        positions_by_person[position.person_id].append(position)
    for values in positions_by_person.values():
        values.sort(key=lambda item: item.simulation_time_s)
    levees_by_key: dict[tuple[str, int], list[LeveeTruth]] = {}
    for levee in levees:
        levees_by_key.setdefault((levee.island_id, levee.simulation_time_s), []).append(levee)
    crossing_by_time: dict[int, list[CrossingState]] = {}
    for crossing in crossing_states:
        crossing_by_time.setdefault(crossing.simulation_time_s, []).append(crossing)
    structures_by_island = {
        island_id: sorted(
            (item for item in structures if item.island_id == island_id),
            key=lambda item: item.structure_id,
        )
        for island_id in {item.island_id for item in structures}
    }
    candidates: list[IncidentCandidate] = []
    for simulation_time_s in range(0, config.timeline.duration_s, config.timeline.tick_s):
        sample = weather_by_time[simulation_time_s]
        rain_fraction = sample.rain_milli_inches_per_hour / 210.0
        wind_fraction = sample.wind_milli_knots / 22_000.0
        route_factor = sum(
            item.travel_time_s for item in crossing_by_time[simulation_time_s]
        ) / max(1, len(crossing_by_time[simulation_time_s]) * 1_800)
        for island_id, island_structures in structures_by_island.items():
            current_levees = sorted(
                levees_by_key[(island_id, simulation_time_s)],
                key=lambda item: item.segment_id,
            )
            for levee_index, levee in enumerate(current_levees):
                prior_time = simulation_time_s - config.timeline.tick_s
                prior_state = (
                    next(
                        item.seepage_state
                        for item in levees_by_key[(island_id, prior_time)]
                        if item.segment_id == levee.segment_id
                    )
                    if prior_time >= 0
                    else "none"
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
        for structure in structures:
            state = state_by_key[(structure.structure_id, simulation_time_s)]
            present = [
                person
                for person in people
                if _position_at(person, positions_by_person, simulation_time_s).structure_id
                == structure.structure_id
            ]
            away_present = [
                person
                for person in present
                if _position_at(person, positions_by_person, simulation_time_s).state
                == "away_from_home"
            ]
            limited = [item for item in present if item.mobility == "limited"]
            medical = [item for item in present if item.medical_dependency != "none"]
            generic_hazard = 0.50 + 0.30 * rain_fraction + 0.10 * wind_fraction
            occupancy = len(present) / 4.0
            vulnerability = 1.0 + 0.35 * len(limited) + 0.45 * len(medical)
            access = 1.35 if state.access_state == "impaired" else 0.65
            for incident_type in INCIDENT_REQUIREMENTS_V7:
                if incident_type == "C-LEV":
                    continue
                selected_people: list[PersonTruth]
                causal_mechanism: str
                type_hazard = generic_hazard
                type_occupancy = occupancy
                type_vulnerability = vulnerability
                type_access = access
                if incident_type == "C-STR":
                    if state.flood_state != "shallow_ponding" or not present:
                        continue
                    selected_people = present
                    type_hazard *= 1.2 + rain_fraction
                    causal_mechanism = "occupied-shallow-ponding-exposure-v1"
                elif incident_type == "C-VEH":
                    if state.access_state != "impaired" or not away_present:
                        continue
                    selected_people = away_present
                    type_hazard *= route_factor
                    type_occupancy = len(away_present) / 2.0
                    causal_mechanism = "impaired-access-during-deterministic-movement-v1"
                elif incident_type == "C-MED":
                    if not medical:
                        continue
                    selected_people = medical
                    type_occupancy = len(medical)
                    type_vulnerability = 1.0 + 0.75 * len(medical)
                    causal_mechanism = "occupied-medical-dependency-under-hazard-v1"
                elif incident_type == "C-WEL":
                    vulnerable = [
                        item
                        for item in present
                        if item.mobility == "limited" or item.medical_dependency != "none"
                    ]
                    if not vulnerable:
                        continue
                    selected_people = vulnerable
                    type_occupancy = len(vulnerable)
                    type_vulnerability = 1.0 + 0.5 * len(vulnerable)
                    causal_mechanism = "limited-mobility-or-medical-welfare-concern-v1"
                else:
                    if not away_present:
                        continue
                    selected_people = away_present
                    type_occupancy = len(away_present)
                    type_vulnerability = 1.0 + 0.25 * len(away_present)
                    causal_mechanism = "deterministic-away-from-home-movement-v1"
                factor = (
                    max(0.0, type_hazard)
                    * max(0.0, type_occupancy)
                    * max(0.0, type_vulnerability)
                    * max(0.0, type_access)
                )
                if factor == 0.0:
                    continue
                candidates.append(
                    IncidentCandidate(
                        structure_id=structure.structure_id,
                        simulation_time_s=simulation_time_s,
                        incident_type=incident_type,
                        person_ids=tuple(item.person_id for item in selected_people),
                        factor=factor,
                        hazard_factor=type_hazard,
                        occupancy_factor=type_occupancy,
                        vulnerability_factor=type_vulnerability,
                        access_factor=type_access,
                        causal_mechanism=causal_mechanism,
                    )
                )
    return candidates


def build_truth_inputs_v7(
    config: DeltaScenarioConfig,
    geography: GeographyCatalog,
    weather: list[WeatherSample],
    crossing_states: list[CrossingState],
    keyed: KeyedRandom,
) -> tuple[
    list[StructureTruth],
    list[StructureState],
    list[PersonTruth],
    list[PersonPosition],
    list[LeveeTruth],
    list[IncidentCandidate],
]:
    high_vulnerability = config.axes.exposure_profile != "isleton_small_v1"
    structures = _structures(geography, keyed, high_vulnerability)
    people, positions = _people_and_positions(config, structures, keyed, high_vulnerability)
    states = _structure_states(config, structures, weather, keyed)
    levees = _levees(config, weather)
    candidates = incident_candidates_v7(
        config,
        structures,
        states,
        people,
        positions,
        levees,
        weather,
        crossing_states,
    )
    return structures, states, people, positions, levees, candidates


def expected_incidents_by_type_v7(candidates: list[IncidentCandidate]) -> dict[str, float]:
    result = {incident_type: 0.0 for incident_type in INCIDENT_REQUIREMENTS_V7}
    for candidate in candidates:
        intercept = TYPE_INTERCEPTS_V1[candidate.incident_type]
        result[candidate.incident_type] += 1.0 - math.exp(-intercept * candidate.factor)
    return result


def generate_truth_v7(
    config: DeltaScenarioConfig,
    geography: GeographyCatalog,
    weather: list[WeatherSample],
    crossing_states: list[CrossingState],
    keyed: KeyedRandom,
) -> GroundTruth:
    structures, states, people, positions, levees, candidates = build_truth_inputs_v7(
        config,
        geography,
        weather,
        crossing_states,
        keyed,
    )
    incidents: list[IncidentTruth] = []
    for candidate in candidates:
        intercept = TYPE_INTERCEPTS_V1[candidate.incident_type]
        probability = 1.0 - math.exp(-intercept * candidate.factor)
        candidate_key = (
            candidate.structure_id,
            candidate.simulation_time_s,
            candidate.incident_type,
            candidate.infrastructure_id or "no-infrastructure",
        )
        if not keyed.bernoulli(probability, "incident-candidate", *candidate_key):
            continue
        incident_digest = hashlib.sha256(
            "|".join(str(item) for item in candidate_key).encode("utf-8")
        ).hexdigest()[:12]
        complexity_milli = keyed.randint(0, 1_000, "incident-complexity", *candidate_key)
        capability, service_duration_s = INCIDENT_REQUIREMENTS_V7[candidate.incident_type]
        service_units = (
            2
            if candidate.incident_type in {"C-STR", "C-MED"} and len(candidate.person_ids) >= 3
            else 1
        )
        incidents.append(
            IncidentTruth(
                incident_id=f"INC7-{incident_digest}",
                structure_id=candidate.structure_id,
                person_ids=list(candidate.person_ids),
                incident_type=candidate.incident_type,
                required_capability=capability,
                onset_s=candidate.simulation_time_s,
                service_duration_s=service_duration_s,
                service_units=service_units,
                complexity_milli=complexity_milli,
                causal_mechanism=candidate.causal_mechanism,
                infrastructure_id=candidate.infrastructure_id,
                causal_factors_milli={
                    "hazard": round(1_000 * candidate.hazard_factor),
                    "occupancy": round(1_000 * candidate.occupancy_factor),
                    "vulnerability": round(1_000 * candidate.vulnerability_factor),
                    "access": round(1_000 * candidate.access_factor),
                    "candidate_probability": round(1_000 * probability),
                },
            )
        )
    return GroundTruth(
        schema_version="delta-ground-truth-v4",
        cohort_label="synthetic-isleton-teaching-cohort-v3-not-demographic",
        structures=structures,
        structure_states=states,
        people=people,
        person_positions=positions,
        levees=levees,
        incidents=sorted(incidents, key=lambda item: (item.onset_s, item.incident_id)),
    )
