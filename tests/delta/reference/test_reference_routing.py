from __future__ import annotations

from pathlib import Path

import pytest

from trace_reference import (
    load_reference_gauge_context,
    load_reference_physical_parameters,
    load_reference_resource_parameters,
)
from trace_reference.domain.observations import (
    ReferencePublicLocation,
    ReferencePublicTaxonomy,
    ReferenceRawReport,
)
from trace_reference.domain.resources import ReferenceResourceClass
from trace_reference.domain.routing import ReferenceRouteMode, ReferenceRouteStatus
from trace_reference.generation import (
    generate_reference_physical_scenario,
    generate_reference_resources,
)
from trace_reference.geography import load_reference_geography
from trace_reference.runtime import ReferenceRouteService, ReferenceScenarioIndex

ROOT = Path(__file__).resolve().parents[3]
GEOGRAPHY_ROOT = ROOT / "data/scenario/delta/reference/geography"


@pytest.fixture(scope="module")
def routing_fixture():
    geography = load_reference_geography(geography_root=GEOGRAPHY_ROOT)
    physical = generate_reference_physical_scenario(
        load_reference_physical_parameters(
            ROOT,
            Path("data/scenario/delta/reference/physical/reference_physical_parameters_v1.yaml"),
        )
    )
    gauge_context = load_reference_gauge_context(
        ROOT,
        Path("data/scenario/delta/reference/physical/reference_gauge_context_v1.yaml"),
    )
    resources = generate_reference_resources(
        load_reference_resource_parameters(
            ROOT,
            Path("data/scenario/delta/reference/resources/reference_resource_parameters_v1.yaml"),
        ),
        seed=20260812,
    )
    index = ReferenceScenarioIndex.from_physical(geography, gauge_context, physical)
    return ReferenceRouteService(index), geography, resources


def _report(geography, island_id: str = "ISL-02") -> ReferenceRawReport:
    anchor = next(item.anchor for item in geography.islands if item.island_id == island_id)
    return ReferenceRawReport(
        call_id="RC-0123456789abcdef",
        observed_at_s=1_000,
        channel="911",
        callback_token="SYN-CB-0123456789abcdef",
        callback_failed=False,
        call_dropped=False,
        third_party=False,
        language_access="english",
        location=ReferencePublicLocation(
            easting_mm_epsg26910=anchor.easting_mm_epsg26910,
            northing_mm_epsg26910=anchor.northing_mm_epsg26910,
            precision_m=25,
            method="gps",
            stated_descriptor="synthetic island anchor",
        ),
        taxonomy=ReferencePublicTaxonomy.C_STR,
        reported_occupants=2,
        medical_descriptors=(),
        descriptor_tokens=("porch",),
    )


def test_public_route_catalog_is_deterministic_complete_and_hidden_free(routing_fixture) -> None:
    service, geography, resources = routing_fixture
    report = _report(geography)
    first = service.build_catalog(report, resources.public_catalog, at_s=1_000)
    second = service.build_catalog(report, resources.public_catalog, at_s=1_000)
    assert first.model_dump_json() == second.model_dump_json()
    assert len(first.routes) == len(resources.public_catalog.resources)
    assert first.target_assignment.destination_node_id == "ISL-02"
    assert first.target_assignment.assignment_method == "inside-source-bound-footprint"
    serialized = first.model_dump_json()
    for forbidden in (
        "truth_incident",
        "truth_person",
        "breach",
        "fatigue",
        "initial_outage",
    ):
        assert forbidden not in serialized


def test_road_route_binds_crossing_state_and_nearest_gauge(routing_fixture) -> None:
    service, geography, resources = routing_fixture
    report = _report(geography)
    before = service.build_catalog(report, resources.public_catalog, at_s=189_000)
    after = service.build_catalog(report, resources.public_catalog, at_s=191_000)
    local_engine = next(
        item
        for item in resources.public_catalog.resources
        if item.resource_class == ReferenceResourceClass.TYPE_I_ENGINE
        and item.staged_node_id == "ISL-01"
    )
    before_route = next(
        item for item in before.routes if item.resource_id == local_engine.resource_id
    )
    after_route = next(
        item for item in after.routes if item.resource_id == local_engine.resource_id
    )
    assert before_route.route_mode == ReferenceRouteMode.ROAD
    assert before_route.edge_ids == ("XNG-04",)
    assert before_route.crossing_ids == ("XNG-04",)
    assert before_route.focal_crossing_id == "XNG-04"
    assert before_route.status == ReferenceRouteStatus.OPEN
    assert after_route.status == ReferenceRouteStatus.BLOCKED
    assert before_route.gauge_id in {item.gauge_id for item in service.index.gauge_context.gauges}


def test_air_weather_and_external_water_ingress_fail_conservatively(routing_fixture) -> None:
    service, geography, resources = routing_fixture
    report = _report(geography)
    grounded_time = next(
        item.at_s
        for item in service.index.public_physical
        if item.weather.air_operability == "grounded" and item.at_s >= 0
    )
    catalog = service.build_catalog(report, resources.public_catalog, at_s=grounded_time)
    aircraft = next(
        item
        for item in resources.public_catalog.resources
        if item.resource_class == ReferenceResourceClass.ROTARY_HOIST
    )
    aircraft_route = next(
        item for item in catalog.routes if item.resource_id == aircraft.resource_id
    )
    assert aircraft_route.route_mode == ReferenceRouteMode.AIR
    assert aircraft_route.status == ReferenceRouteStatus.BLOCKED

    external_boat = next(
        item
        for item in resources.public_catalog.resources
        if item.resource_class == ReferenceResourceClass.RESCUE_BOAT
        and item.staged_node_id == "BND-RIO-VISTA"
    )
    water_route = next(
        item for item in catalog.routes if item.resource_id == external_boat.resource_id
    )
    assert water_route.route_mode == ReferenceRouteMode.WATER
    assert water_route.status == ReferenceRouteStatus.UNKNOWN
    assert "verification" in water_route.status_reason


def test_public_index_retains_no_breach_interface(routing_fixture) -> None:
    service, _, _ = routing_fixture
    sample = service.index.physical_at(187_200)
    assert not hasattr(sample, "breach")
    assert sample.at_s == 187_200
