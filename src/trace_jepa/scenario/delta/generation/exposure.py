"""Deterministic synthetic exposure, cohort, trajectory, and state generation."""

from __future__ import annotations

from dataclasses import dataclass

from trace_jepa.scenario.delta.domain import (
    DeltaScenarioConfig,
    LeveeTruth,
    PersonPosition,
    PersonTruth,
    StructureState,
    StructureTruth,
    WeatherSample,
)
from trace_jepa.scenario.delta.generation.randomness import KeyedRandom
from trace_jepa.scenario.delta.geography.models import GeographyCatalog, LinearRing


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


@dataclass(frozen=True)
class PlacementRequest:
    ring: LinearRing
    count: int
    keyed: KeyedRandom
    island_id: str
    minimum_separation_m: int
    required_containment_rings: list[LinearRing] | None
    high_vulnerability: bool


def _sample_points(request: PlacementRequest) -> list[tuple[int, int]]:
    ring = request.ring
    eastings = [point.easting_mm for point in ring.points]
    northings = [point.northing_mm for point in ring.points]
    minimum_easting, maximum_easting = min(eastings), max(eastings)
    minimum_northing, maximum_northing = min(northings), max(northings)
    separation_squared = (request.minimum_separation_m * 1000) ** 2
    points: list[tuple[int, int]] = []
    for attempt in range(100_000):
        candidate = (
            request.keyed.randint(
                minimum_easting,
                maximum_easting,
                "structure-placement",
                request.island_id,
                attempt,
                "easting",
            ),
            request.keyed.randint(
                minimum_northing,
                maximum_northing,
                "structure-placement",
                request.island_id,
                attempt,
                "northing",
            ),
        )
        if not _point_inside_ring(*candidate, ring):
            continue
        if request.required_containment_rings and not any(
            _point_inside_ring(*candidate, required_ring)
            for required_ring in request.required_containment_rings
        ):
            continue
        if request.high_vulnerability:
            north_fraction = (candidate[1] - minimum_northing) / max(
                1, maximum_northing - minimum_northing
            )
            acceptance = 0.45 + 0.45 * (1.0 - north_fraction)
            if (
                request.keyed.uniform(
                    "structure-placement", request.island_id, attempt, "exposure-bias"
                )
                >= acceptance
            ):
                continue
        if any(
            (candidate[0] - point[0]) ** 2 + (candidate[1] - point[1]) ** 2 < separation_squared
            for point in points
        ):
            continue
        points.append(candidate)
        if len(points) == request.count:
            return points
    raise RuntimeError("could not place v7 synthetic structures within the frozen polygons")


def generate_structures(
    geography: GeographyCatalog,
    keyed: KeyedRandom,
    high_vulnerability: bool,
) -> list[StructureTruth]:
    community = next(item for item in geography.communities if item.community_id == "TWN-01")
    andrus = next(item for item in geography.islands if item.island_id == "ISL-01")
    brannan = next(item for item in geography.islands if item.island_id == "ISL-02")
    andrus_points = _sample_points(
        PlacementRequest(
            ring=community.geometry.polygons[0],
            count=12,
            keyed=keyed,
            island_id="ISL-01",
            minimum_separation_m=55,
            required_containment_rings=andrus.geometry.polygons,
            high_vulnerability=high_vulnerability,
        )
    )
    brannan_points = _sample_points(
        PlacementRequest(
            ring=brannan.geometry.polygons[0],
            count=3,
            keyed=keyed,
            island_id="ISL-02",
            minimum_separation_m=200,
            required_containment_rings=None,
            high_vulnerability=high_vulnerability,
        )
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


def generate_people_and_positions(
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


def generate_structure_states(
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


def generate_levees(
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
