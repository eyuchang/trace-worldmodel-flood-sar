from __future__ import annotations

import json
import shutil
from collections import deque
from itertools import pairwise
from pathlib import Path

import pytest

from trace_jepa.support import sha256_file
from trace_reference.geography import build_reference_geography, load_reference_geography

ROOT = Path(__file__).resolve().parents[3]
GEOGRAPHY_ROOT = ROOT / "data/scenario/delta/reference/geography"
SOURCE_NAMES = (
    "dwr_lma_target_v1.geojson",
    "sacramento_county_andrus_brannan_v1.geojson",
    "census_incorporated_places_v1.geojson",
    "census_designated_places_v1.geojson",
    "usgs_gnis_communities_v1.geojson",
    "caltrans_state_crossings_v1.geojson",
    "caltrans_local_crossings_v1.geojson",
    "usgs_gnis_woodward_crossing_v1.geojson",
)


def test_committed_reference_geography_regenerates_byte_identically(tmp_path: Path) -> None:
    build_reference_geography(
        geography_root=GEOGRAPHY_ROOT,
        output_root=tmp_path,
    )
    committed = GEOGRAPHY_ROOT / "derived"
    for name in (
        "reference_geography_catalog_v2.json",
        "reference_geography_build_manifest_v2.json",
    ):
        assert (tmp_path / name).read_bytes() == (committed / name).read_bytes()


def test_development_v1_geography_remains_immutable_protocol_history() -> None:
    expected = {
        "reference_geography_catalog_v1.json": (
            "be3e57790e0b5550a95c8ce6517e86bb8db2668ada50f6894f117bf3bfae7977"
        ),
        "reference_geography_build_manifest_v1.json": (
            "dcf06ad149efdd0c606b53cbcc4c1fdc0dfa028c9ddb3018b6bcec578ec12540"
        ),
    }
    for name, digest in expected.items():
        assert sha256_file(GEOGRAPHY_ROOT / "derived" / name) == digest


def test_catalog_binds_all_reference_entities_and_corrected_crossing_types() -> None:
    catalog = load_reference_geography(geography_root=GEOGRAPHY_ROOT)

    assert [item.island_id for item in catalog.islands] == [
        f"ISL-{index:02d}" for index in range(1, 9)
    ]
    assert [item.community_id for item in catalog.communities] == [
        f"TWN-{index:02d}" for index in range(1, 5)
    ]
    crossing = {item.crossing_id: item for item in catalog.crossings}
    assert crossing["XNG-03"].crossing_type == "movable-lift"
    assert crossing["XNG-08"].crossing_type == "hydraulic-ferry"
    assert crossing["XNG-10"].crossing_type == "crossing-type-unresolved"
    assert crossing["XNG-10"].evidence_status == "official-identity-current-type-unresolved"
    assert all(item.boundary.area_m2_epsg26910 > 1_000_000 for item in catalog.islands)


def test_andrus_binding_preserves_district_segmentation_and_balmd_crosscheck() -> None:
    catalog = load_reference_geography(geography_root=GEOGRAPHY_ROOT)
    andrus = catalog.islands[0]
    identifiers = {
        identifier
        for binding in andrus.source_bindings
        for identifier in binding.feature_identifiers
    }
    assert {"OBJECTID:19", "OBJECTID:22", "OBJECTID:23"}.issubset(identifiers)
    assert "OBJECTID:259" in identifiers
    assert andrus.boundary_semantics == "union-of-county-reclamation-district-footprints"

    brannan = catalog.islands[1]
    assert brannan.boundary_semantics == "single-county-reclamation-district-footprint"
    assert len(brannan.source_bindings) == 1
    assert brannan.source_bindings[0].feature_identifiers == ("OBJECTID:24",)


def test_community_identifiers_and_derived_anchor_semantics_are_explicit() -> None:
    catalog = load_reference_geography(geography_root=GEOGRAPHY_ROOT)
    communities = {item.community_id: item for item in catalog.communities}
    assert communities["TWN-01"].source_bindings[0].feature_identifiers == ("PLACE:36882",)
    assert communities["TWN-02"].source_bindings[0].feature_identifiers == ("PLACE:83374",)
    assert communities["TWN-03"].geometry_semantics == (
        "gnis-derived-centroid-of-official-multipoint-no-boundary"
    )
    assert communities["TWN-03"].source_bindings[0].use == "derived-anchor"


def test_multimodal_simulation_graph_connects_all_exposure_islands() -> None:
    catalog = load_reference_geography(geography_root=GEOGRAPHY_ROOT)
    graph: dict[str, set[str]] = {node.node_id: set() for node in catalog.route_nodes}
    for edge in catalog.route_edges:
        graph[edge.from_node_id].add(edge.to_node_id)
        graph[edge.to_node_id].add(edge.from_node_id)
    reached = {"ISL-01"}
    pending = deque(reached)
    while pending:
        for neighbor in graph[pending.popleft()]:
            if neighbor not in reached:
                reached.add(neighbor)
                pending.append(neighbor)
    assert {f"ISL-{index:02d}" for index in range(1, 9)}.issubset(reached)
    assert all(edge.operative_claim == "simulation-topology-only" for edge in catalog.route_edges)


def test_source_snapshots_exclude_upstream_contact_fields() -> None:
    source_bytes = b"".join(path.read_bytes() for path in (GEOGRAPHY_ROOT / "sources").iterdir())
    assert b"Daytime_Phone" not in source_bytes
    assert b"Nighttime_Phone" not in source_bytes
    assert b"callback" not in source_bytes


def test_release_and_license_policy_is_fail_closed() -> None:
    catalog = load_reference_geography(geography_root=GEOGRAPHY_ROOT)
    sources = {item.source_id: item for item in catalog.sources}
    assert sources["REF-GEO-SRC-06"].redistribution_status == ("creative-commons-attribution")
    assert sources["REF-GEO-SRC-07"].redistribution_status == ("creative-commons-attribution")
    county = sources["REF-GEO-SRC-02"]
    assert county.redistribution_status == "redistribution-review-required"
    assert county.release_inclusion == "excluded-pending-dataset-specific-license-review"
    assert catalog.scientific_status.startswith("development-only")


def test_polygon_orientation_is_canonical_and_source_requirements_are_reconciled() -> None:
    catalog = load_reference_geography(geography_root=GEOGRAPHY_ROOT)
    assert {
        requirement for source in catalog.sources for requirement in source.phase0_requirement_ids
    } == {
        "REF-SRC-01",
        "REF-SRC-02",
        "REF-SRC-03",
        "REF-SRC-04",
    }
    for island in catalog.islands:
        for polygon in island.boundary.polygons_e6:
            signed_areas = [
                sum(
                    left_x * right_y - right_x * left_y
                    for (left_x, left_y), (right_x, right_y) in pairwise(ring)
                )
                for ring in polygon
            ]
            assert signed_areas[0] > 0
            assert all(value < 0 for value in signed_areas[1:])


def test_all_committed_source_objects_are_recursively_free_of_contact_fields() -> None:
    prohibited = {"phone", "email", "callback", "contact", "owner", "mailing"}

    def inspect(value: object) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                assert not any(token in str(key).casefold() for token in prohibited)
                inspect(nested)
        elif isinstance(value, list):
            for nested in value:
                inspect(nested)
        elif isinstance(value, str):
            assert "@" not in value

    for source in sorted((GEOGRAPHY_ROOT / "sources").glob("*.geojson")):
        inspect(json.loads(source.read_text("utf-8")))


def test_catalog_tamper_and_symlink_fail_closed(tmp_path: Path) -> None:
    copied = tmp_path / "geography"
    shutil.copytree(GEOGRAPHY_ROOT, copied)
    catalog_path = copied / "derived/reference_geography_catalog_v2.json"
    catalog_path.write_bytes(catalog_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="catalog digest mismatch"):
        load_reference_geography(geography_root=copied)

    copied = tmp_path / "linked-geography"
    shutil.copytree(GEOGRAPHY_ROOT, copied)
    source = copied / "sources/dwr_lma_target_v1.geojson"
    replacement = copied / "outside.geojson"
    replacement.write_bytes(source.read_bytes())
    source.unlink()
    source.symlink_to(replacement)
    with pytest.raises(ValueError, match="must not be a symlink"):
        load_reference_geography(geography_root=copied)


@pytest.mark.parametrize(
    ("relative_name", "message"),
    [
        ("source_metadata_v2.yaml", "metadata registry digest mismatch"),
        ("source_retrieval_receipts_v2.yaml", "retrieval receipts digest mismatch"),
    ],
)
def test_provenance_registry_mutation_fails_closed(
    tmp_path: Path, relative_name: str, message: str
) -> None:
    copied = tmp_path / "geography"
    shutil.copytree(GEOGRAPHY_ROOT, copied)
    target = copied / relative_name
    target.write_bytes(target.read_bytes() + b"# mutation\n")
    with pytest.raises(ValueError, match=message):
        load_reference_geography(geography_root=copied)


@pytest.mark.parametrize("source_name", SOURCE_NAMES)
def test_every_source_mutation_fails_closed(tmp_path: Path, source_name: str) -> None:
    copied = tmp_path / source_name
    shutil.copytree(GEOGRAPHY_ROOT, copied)
    target = copied / "sources" / source_name
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError, match="source digest mismatch"):
        load_reference_geography(geography_root=copied)


def test_builder_rejects_intermediate_symlink_source_directory(tmp_path: Path) -> None:
    copied = tmp_path / "geography"
    shutil.copytree(GEOGRAPHY_ROOT, copied)
    actual_sources = copied / "actual-sources"
    (copied / "sources").rename(actual_sources)
    (copied / "sources").symlink_to(actual_sources, target_is_directory=True)
    output = tmp_path / "output"
    output.mkdir()
    with pytest.raises(ValueError, match="parent must not be a symlink"):
        build_reference_geography(geography_root=copied, output_root=output)


def test_environment_binding_and_metadata_schema_fail_closed(tmp_path: Path) -> None:
    copied = tmp_path / "geography"
    shutil.copytree(GEOGRAPHY_ROOT, copied)
    manifest_path = copied / "derived/reference_geography_build_manifest_v2.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["environment_versions"]["python"] = "0.0.0"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="geospatial environment mismatch"):
        load_reference_geography(geography_root=copied)

    copied = tmp_path / "invalid-schema"
    shutil.copytree(GEOGRAPHY_ROOT, copied)
    metadata_path = copied / "source_metadata_v2.yaml"
    metadata_path.write_text(
        metadata_path.read_text("utf-8").replace(
            "    agency: California Department of Water Resources\n",
            "    agency: California Department of Water Resources\n    unexpected: rejected\n",
            1,
        ),
        encoding="utf-8",
    )
    output = tmp_path / "output"
    output.mkdir()
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        build_reference_geography(geography_root=copied, output_root=output)
