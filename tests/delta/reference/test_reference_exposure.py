from __future__ import annotations

import math
from pathlib import Path

import pytest
from shapely.geometry import Point

from trace_reference import load_reference_exposure_parameters
from trace_reference.generation import generate_reference_exposure
from trace_reference.geography import load_reference_geography
from trace_reference.geography.runtime_geometry import boundary_metric_geometry

ROOT = Path(__file__).resolve().parents[3]
GEOGRAPHY_ROOT = ROOT / "data/scenario/delta/reference/geography"
PARAMETERS = Path("data/scenario/delta/reference/exposure/reference_exposure_parameters_v1.yaml")


@pytest.fixture(scope="module")
def exposure():
    parameters = load_reference_exposure_parameters(ROOT, PARAMETERS)
    geography = load_reference_geography(geography_root=GEOGRAPHY_ROOT)
    return parameters, geography, generate_reference_exposure(parameters, geography, seed=20260812)


def test_reference_exposure_has_exact_synthetic_scale_and_is_deterministic(exposure) -> None:
    parameters, geography, scenario = exposure
    regenerated = generate_reference_exposure(parameters, geography, seed=20260812)
    assert len(scenario.people) == 1_400
    assert len(scenario.structures) == 420
    assert scenario.model_dump_json() == regenerated.model_dump_json()
    assert scenario.exposure_digest == regenerated.exposure_digest


def test_synthetic_structures_are_inside_source_bound_footprints_and_separated(exposure) -> None:
    parameters, geography, scenario = exposure
    geometry_by_island = {
        item.island_id: boundary_metric_geometry(item.boundary) for item in geography.islands
    }
    points_by_island: dict[str, list[tuple[float, float]]] = {}
    for structure in scenario.structures:
        easting = structure.location.easting_mm_epsg26910 / 1_000
        northing = structure.location.northing_mm_epsg26910 / 1_000
        assert geometry_by_island[structure.island_id].contains(Point(easting, northing))
        points_by_island.setdefault(structure.island_id, []).append((easting, northing))
        assert structure.location_semantics.endswith("not-a-real-address")
    for points in points_by_island.values():
        for index, left in enumerate(points):
            assert all(
                math.dist(left, right) >= parameters.minimum_structure_separation_m - 0.002
                for right in points[index + 1 :]
            )


def test_people_remain_synthetic_and_trajectories_are_recoverable(exposure) -> None:
    _, _, scenario = exposure
    structure_by_id = {item.truth_structure_id: item for item in scenario.structures}
    assert len({item.synthetic_callback_token for item in scenario.people}) == 1_400
    assert all(item.synthetic_callback_token.startswith("SYN-CB-") for item in scenario.people)
    assert all(item.trajectory[0].at_s == -172_800 for item in scenario.people)
    for person in scenario.people:
        assert all(
            structure_by_id[point.synthetic_structure_id].island_id == person.island_id
            for point in person.trajectory
        )


def test_epsilon_changes_only_exposure_descendants(exposure) -> None:
    parameters, geography, baseline = exposure
    vulnerable = generate_reference_exposure(parameters, geography, seed=20260812, epsilon=1.2)
    assert tuple(item.truth_structure_id for item in baseline.structures) == tuple(
        item.truth_structure_id for item in vulnerable.structures
    )
    assert tuple(item.truth_person_id for item in baseline.people) == tuple(
        item.truth_person_id for item in vulnerable.people
    )
    assert sum(item.vulnerability_micros for item in vulnerable.people) > sum(
        item.vulnerability_micros for item in baseline.people
    )


def test_exposure_parameter_loader_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "parameters.yaml"
    target.write_bytes((ROOT / PARAMETERS).read_bytes())
    alias = tmp_path / "alias.yaml"
    alias.symlink_to(target)
    with pytest.raises(ValueError, match="must not be a symlink"):
        load_reference_exposure_parameters(tmp_path, Path("alias.yaml"))
