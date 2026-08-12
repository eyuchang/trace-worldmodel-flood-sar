"""Generate the 1,400-person synthetic Reference teaching cohort."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass

from shapely.geometry import Point

from trace_jepa.support import canonical_json_bytes
from trace_reference.domain.exposure import (
    ReferenceExposureParameters,
    ReferenceExposureScenario,
    ReferenceSyntheticPerson,
    ReferenceSyntheticStructure,
    ReferenceTrajectoryChangePoint,
)
from trace_reference.geography.catalog_models import ReferenceGeographyCatalog, ReferenceIsland
from trace_reference.geography.runtime_geometry import boundary_metric_geometry, metric_point

from .randomness import digest_order, keyed_digest, uniform_micros

_START_S = -172_800
_END_S = 345_600
_DAY_S = 86_400


@dataclass(frozen=True)
class _PersonBuildContext:
    parameters: ReferenceExposureParameters
    seed: int
    namespace: str
    island_structures: tuple[ReferenceSyntheticStructure, ...]
    epsilon_micros: int


def _identifier(prefix: str, seed: int, namespace: str, *parts: object) -> str:
    return f"{prefix}-{keyed_digest(seed, namespace, *parts).hex()[:16]}"


def _rate(rate_micros: int, epsilon_micros: int) -> int:
    return min(1_000_000, round(rate_micros * epsilon_micros / 1_000_000))


def _nearby_clear(
    *,
    easting_m: float,
    northing_m: float,
    grid: dict[tuple[int, int], list[tuple[float, float]]],
    separation_m: int,
) -> bool:
    cell = (int(easting_m // separation_m), int(northing_m // separation_m))
    squared_limit = separation_m * separation_m
    for cell_x in range(cell[0] - 1, cell[0] + 2):
        for cell_y in range(cell[1] - 1, cell[1] + 2):
            for other_x, other_y in grid[(cell_x, cell_y)]:
                if (easting_m - other_x) ** 2 + (northing_m - other_y) ** 2 < squared_limit:
                    return False
    grid[cell].append((easting_m, northing_m))
    return True


def _sample_structures(
    *,
    seed: int,
    namespace: str,
    island: ReferenceIsland,
    count: int,
    separation_m: int,
    epsilon_micros: int,
) -> tuple[ReferenceSyntheticStructure, ...]:
    geometry = boundary_metric_geometry(island.boundary)
    min_x, min_y, max_x, max_y = geometry.bounds
    grid: dict[tuple[int, int], list[tuple[float, float]]] = defaultdict(list)
    structures: list[ReferenceSyntheticStructure] = []
    for index in range(count):
        for attempt in range(10_000):
            x_draw = uniform_micros(seed, namespace, island.island_id, index, attempt, "x")
            y_draw = uniform_micros(seed, namespace, island.island_id, index, attempt, "y")
            easting = min_x + (max_x - min_x) * x_draw / 1_000_000
            northing = min_y + (max_y - min_y) * y_draw / 1_000_000
            if not geometry.contains(Point(easting, northing)):
                continue
            if not _nearby_clear(
                easting_m=easting,
                northing_m=northing,
                grid=grid,
                separation_m=separation_m,
            ):
                continue
            structure_id = _identifier("RS", seed, namespace, island.island_id, index)
            base_draw = uniform_micros(seed, namespace, structure_id, "vulnerability")
            vulnerability = min(
                1_000_000,
                round((300_000 + base_draw * 450_000 / 1_000_000) * epsilon_micros / 1_000_000),
            )
            structures.append(
                ReferenceSyntheticStructure(
                    truth_structure_id=structure_id,
                    island_id=island.island_id,
                    location=metric_point(easting, northing),
                    synthetic_capacity=4
                    + uniform_micros(seed, namespace, structure_id, "capacity") % 3,
                    vulnerability_micros=vulnerability,
                    utility_resilience_micros=300_000
                    + uniform_micros(seed, namespace, structure_id, "utility") % 600_001,
                    animal_units=(
                        uniform_micros(seed, namespace, structure_id, "animals") % 9
                        if uniform_micros(seed, namespace, structure_id, "has-animals") < 180_000
                        else 0
                    ),
                    location_semantics=(
                        "seeded-point-inside-simulation-footprint-not-a-real-address"
                    ),
                )
            )
            break
        else:
            raise RuntimeError(
                f"unable to place {count} separated synthetic structures on {island.island_id}"
            )
    return tuple(structures)


def _movement_pattern(
    parameters: ReferenceExposureParameters,
    *,
    seed: int,
    namespace: str,
    person_id: str,
    epsilon_micros: int,
) -> str:
    draw = uniform_micros(seed, namespace, person_id, "occupancy-pattern")
    day_rate = _rate(parameters.daytime_away_rate_micros, epsilon_micros)
    night_rate = _rate(parameters.nighttime_away_rate_micros, epsilon_micros)
    if draw < day_rate:
        return "daytime-away"
    if draw < day_rate + night_rate:
        return "nighttime-away"
    return "home-static"


def _trajectory(
    *,
    seed: int,
    namespace: str,
    person_id: str,
    pattern: str,
    home: ReferenceSyntheticStructure,
    island_structures: tuple[ReferenceSyntheticStructure, ...],
) -> tuple[ReferenceTrajectoryChangePoint, ...]:
    away_ids = digest_order(
        seed,
        namespace,
        (item.truth_structure_id for item in island_structures if item != home),
        person_id,
        "away-destination",
    )
    away = next(item for item in island_structures if item.truth_structure_id == away_ids[0])
    initial_state = "away-synthetic-activity" if pattern == "nighttime-away" else "home"
    initial_structure = away if pattern == "nighttime-away" else home
    points = [
        ReferenceTrajectoryChangePoint(
            at_s=_START_S,
            state=initial_state,
            synthetic_structure_id=initial_structure.truth_structure_id,
            location=initial_structure.location,
        )
    ]
    if pattern == "home-static":
        return tuple(points)
    for day_start in range(_START_S, _END_S + _DAY_S, _DAY_S):
        transitions = (
            (
                (day_start + 14_400, "away-synthetic-activity", away),
                (day_start + 50_400, "home", home),
            )
            if pattern == "daytime-away"
            else (
                (day_start + 3_600, "home", home),
                (day_start + 61_200, "away-synthetic-activity", away),
            )
        )
        for at_s, state, structure in transitions:
            if _START_S < at_s <= _END_S:
                points.append(
                    ReferenceTrajectoryChangePoint(
                        at_s=at_s,
                        state=state,
                        synthetic_structure_id=structure.truth_structure_id,
                        location=structure.location,
                    )
                )
    return tuple(sorted(points, key=lambda item: item.at_s))


def _person(
    context: _PersonBuildContext,
    *,
    index: int,
    home: ReferenceSyntheticStructure,
) -> ReferenceSyntheticPerson:
    parameters = context.parameters
    seed = context.seed
    namespace = context.namespace
    epsilon_micros = context.epsilon_micros
    person_id = _identifier("RP", seed, namespace, home.island_id, index)
    mobility_draw = uniform_micros(seed, namespace, person_id, "mobility")
    wheelchair_rate = _rate(parameters.wheelchair_rate_micros, epsilon_micros)
    limited_rate = _rate(parameters.limited_mobility_rate_micros, epsilon_micros)
    mobility = (
        "wheelchair"
        if mobility_draw < wheelchair_rate
        else "limited"
        if mobility_draw < wheelchair_rate + limited_rate
        else "standard"
    )
    medical_draw = uniform_micros(seed, namespace, person_id, "medical")
    medical_rates = (
        ("oxygen", _rate(parameters.oxygen_dependency_rate_micros, epsilon_micros)),
        ("dialysis", _rate(parameters.dialysis_dependency_rate_micros, epsilon_micros)),
        ("insulin", _rate(parameters.insulin_dependency_rate_micros, epsilon_micros)),
    )
    medical = "none"
    cumulative = 0
    for label, rate in medical_rates:
        cumulative += rate
        if medical_draw < cumulative:
            medical = label
            break
    language_draw = uniform_micros(seed, namespace, person_id, "language")
    non_english_rate = _rate(parameters.non_english_access_rate_micros, epsilon_micros)
    if language_draw >= non_english_rate:
        language = "english"
    else:
        language = ("spanish", "tagalog", "chinese")[language_draw % 3]
    transport = (
        "unavailable"
        if uniform_micros(seed, namespace, person_id, "transport")
        < _rate(parameters.no_transport_rate_micros, epsilon_micros)
        else "available"
    )
    pattern = _movement_pattern(
        parameters,
        seed=seed,
        namespace=namespace,
        person_id=person_id,
        epsilon_micros=epsilon_micros,
    )
    vulnerability = 150_000 + uniform_micros(seed, namespace, person_id, "vulnerability") // 3
    vulnerability += (
        180_000 if mobility == "limited" else 300_000 if mobility == "wheelchair" else 0
    )
    vulnerability += 220_000 if medical != "none" else 0
    vulnerability += 120_000 if transport == "unavailable" else 0
    return ReferenceSyntheticPerson(
        truth_person_id=person_id,
        home_structure_id=home.truth_structure_id,
        island_id=home.island_id,
        mobility=mobility,
        medical_dependency=medical,
        language_access=language,
        transport_access=transport,
        occupancy_pattern=pattern,
        vulnerability_micros=min(1_000_000, round(vulnerability * epsilon_micros / 1_000_000)),
        synthetic_callback_token=_identifier("SYN-CB", seed, namespace, person_id, "callback"),
        trajectory=_trajectory(
            seed=seed,
            namespace=namespace,
            person_id=person_id,
            pattern=pattern,
            home=home,
            island_structures=context.island_structures,
        ),
    )


def generate_reference_exposure(
    parameters: ReferenceExposureParameters,
    geography: ReferenceGeographyCatalog,
    *,
    seed: int,
    epsilon: float = 1.0,
) -> ReferenceExposureScenario:
    """Generate a deterministic cohort without parcels, addresses, or real identities."""

    if not 0.3 <= epsilon <= 2.0:
        raise ValueError("Reference epsilon must remain within the registered axis range")
    epsilon_micros = round(epsilon * 1_000_000)
    island_by_id = {item.island_id: item for item in geography.islands}
    namespace = parameters.randomness_namespace
    structures: list[ReferenceSyntheticStructure] = []
    people: list[ReferenceSyntheticPerson] = []
    person_index = 0
    for allocation in parameters.island_allocations:
        island_structures = _sample_structures(
            seed=seed,
            namespace=namespace,
            island=island_by_id[allocation.island_id],
            count=allocation.synthetic_structures,
            separation_m=parameters.minimum_structure_separation_m,
            epsilon_micros=epsilon_micros,
        )
        structures.extend(island_structures)
        slots = [
            item.truth_structure_id
            for item in island_structures
            for _ in range(item.synthetic_capacity)
        ]
        if len(slots) < allocation.synthetic_people:
            raise RuntimeError(f"insufficient synthetic capacity on {allocation.island_id}")
        ordered_slots = digest_order(seed, namespace, slots, allocation.island_id, "home-slots")
        structure_by_id = {item.truth_structure_id: item for item in island_structures}
        person_context = _PersonBuildContext(
            parameters=parameters,
            seed=seed,
            namespace=namespace,
            island_structures=island_structures,
            epsilon_micros=epsilon_micros,
        )
        for slot in ordered_slots[: allocation.synthetic_people]:
            people.append(
                _person(
                    person_context,
                    index=person_index,
                    home=structure_by_id[slot],
                )
            )
            person_index += 1
    body = {
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "schema_version": "delta-reference-exposure-v1",
        "parameter_version": parameters.parameter_version,
        "profile_id": parameters.profile_id,
        "seed": seed,
        "epsilon_micros": epsilon_micros,
        "structures": [item.model_dump(mode="json") for item in structures],
        "people": [item.model_dump(mode="json") for item in people],
    }
    return ReferenceExposureScenario(
        **body,
        exposure_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )
