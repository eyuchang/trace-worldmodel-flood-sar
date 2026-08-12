from __future__ import annotations

import shutil
from collections import deque
from pathlib import Path

import pytest
import yaml

from trace_reference.geography import build_reference_geography, load_reference_geography

ROOT = Path(__file__).resolve().parents[3]
GEOGRAPHY_ROOT = ROOT / "data/scenario/delta/reference/geography"


def _metadata() -> list[dict[str, object]]:
    value = yaml.safe_load((GEOGRAPHY_ROOT / "source_metadata_v1.yaml").read_text("utf-8"))
    assert isinstance(value, dict)
    assert isinstance(value["sources"], list)
    return value["sources"]


def test_committed_reference_geography_regenerates_byte_identically(tmp_path: Path) -> None:
    build_reference_geography(
        source_root=GEOGRAPHY_ROOT / "sources",
        source_metadata=_metadata(),
        output_root=tmp_path,
    )
    committed = GEOGRAPHY_ROOT / "derived"
    for name in (
        "reference_geography_catalog_v1.json",
        "reference_geography_build_manifest_v1.json",
    ):
        assert (tmp_path / name).read_bytes() == (committed / name).read_bytes()


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


def test_catalog_tamper_and_symlink_fail_closed(tmp_path: Path) -> None:
    copied = tmp_path / "geography"
    shutil.copytree(GEOGRAPHY_ROOT, copied)
    catalog_path = copied / "derived/reference_geography_catalog_v1.json"
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
