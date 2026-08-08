from __future__ import annotations

import hashlib
import json
import socket
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError
from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon

from trace_jepa.experimental import AdequacyStatus
from trace_jepa.predictor import (
    CachedVJEPAFeatureProvider,
    CalibratedVJEPAHead,
    MLPActionPrefixPredictor,
    PredictorInputUnavailable,
    PredictorRequest,
    PredictorVisualFeatureRef,
    ToyActionPrefixPredictor,
    VJEPABackedActionPrefixPredictor,
    write_deterministic_feature_cache,
)
from trace_jepa.scenario.delta.artifacts import canonical_json_bytes
from trace_jepa.scenario.delta.generator import generate_delta_small
from trace_jepa.scenario.delta.loading import load_geography_catalog
from trace_jepa.scenario.delta.publication import publish_reference_bundle
from trace_jepa.scenario.delta.runner import evaluate_capacity_windows, run_delta_small
from trace_jepa.util import sha256_file

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/scenarios/wf_dfld_01_small.yaml"
GEOGRAPHY = ROOT / "data/scenario/delta/geography/delta_small_geography_v3.yaml"
GEOGRAPHY_MANIFEST = ROOT / "data/scenario/delta/geography/build_manifest_v3.json"
POLICY = ROOT / "configs/policies/trace_delta_small_v1.yaml"
FIXTURES = ROOT / "tests/fixtures/predictor"


class _UnqualifiedBackend:
    def infer(self, request: PredictorRequest) -> list[float]:
        assert request.plan.first_action.action_type in {
            "dispatch_rescue_boat",
            "deploy_ground_team",
            "perform_welfare_check",
            "inspect_levee",
        }
        return [1.0, 6.0, -1.0, 0.0, 2.0, -2.0, -1.0]


def _mlp() -> MLPActionPrefixPredictor:
    return MLPActionPrefixPredictor(
        backend=_UnqualifiedBackend(),
        predictor_version="mlp-delta-fixture-v1",
        calibration_version="mlp-delta-fixture-cal-v1",
        training_snapshot="project-owned-synthetic-fixture",
        model_hash="1" * 64,
        calibration_hash="2" * 64,
        adequacy_status=AdequacyStatus.UNQUALIFIED,
    )


def _vjepa() -> VJEPABackedActionPrefixPredictor:
    manifest = json.loads((FIXTURES / "manifest.json").read_text("utf-8"))
    provider = CachedVJEPAFeatureProvider(
        FIXTURES,
        encoder_version=manifest["encoder_version"],
        encoder_checkpoint_hash=manifest["encoder_checkpoint_hash"],
    )
    return VJEPABackedActionPrefixPredictor(
        provider,
        CalibratedVJEPAHead.load(FIXTURES / "vjepa_ci_head.npz"),
        adequacy_status=AdequacyStatus.UNQUALIFIED,
    )


def test_runtime_public_outputs_are_independent_of_hidden_lineage() -> None:
    scenario = generate_delta_small(CONFIG, GEOGRAPHY)
    without_lineage = scenario.model_copy(
        update={"observations": scenario.observations.model_copy(update={"lineage": []})}
    )
    visible = run_delta_small(scenario, ToyActionPrefixPredictor(), POLICY)
    hidden_deleted = run_delta_small(
        without_lineage,
        ToyActionPrefixPredictor(),
        POLICY,
    )
    assert visible.decisions == hidden_deleted.decisions
    assert visible.evidence == hidden_deleted.evidence
    assert visible.predictor_requests == hidden_deleted.predictor_requests
    assert visible.reconciliation_artifact == hidden_deleted.reconciliation_artifact
    assert visible.trace_records == hidden_deleted.trace_records
    assert visible.commitments == hidden_deleted.commitments
    assert visible.outcomes == hidden_deleted.outcomes

    public_payload = canonical_json_bytes(
        {
            "decisions": [item.model_dump(mode="json") for item in visible.decisions],
            "evidence": [item.model_dump(mode="json") for item in visible.evidence],
            "predictor_requests": [
                item.model_dump(mode="json") for item in visible.predictor_requests
            ],
            "reconciliation": visible.reconciliation_artifact.model_dump(mode="json"),
            "records": [item.model_dump(mode="json") for item in visible.trace_records],
            "commitments": [item.model_dump(mode="json") for item in visible.commitments],
            "outcomes": [item.model_dump(mode="json") for item in visible.outcomes],
        }
    )
    for forbidden in (b"INC-", b"PER-", b"STR-", b"truth_incident", b"truth_person"):
        assert forbidden not in public_payload


def test_predictor_requests_bind_nearest_gauge_stage_ages_and_resource_telemetry() -> None:
    scenario = generate_delta_small(CONFIG, GEOGRAPHY)
    result = run_delta_small(scenario, ToyActionPrefixPredictor(), POLICY)
    assert (
        len(result.predictor_requests) == len(result.evidence) == len(scenario.observations.calls)
    )
    crossing_by_id = {item.crossing_id: item for item in scenario.geography.crossings}
    gauge_by_id = {item.gauge_id: item for item in scenario.geography.gauges}
    gauge_sample_by_key = {
        (item.gauge_id, item.simulation_time_s): item for item in scenario.gauges
    }
    for request, evidence in zip(result.predictor_requests, result.evidence, strict=True):
        route = request.observation.routes[0]
        crossing = crossing_by_id[route.route_id]
        expected_gauge = min(
            scenario.geography.gauges,
            key=lambda gauge: (
                (gauge.location.easting_mm - crossing.location.easting_mm) ** 2
                + (gauge.location.northing_mm - crossing.location.northing_mm) ** 2,
                gauge.gauge_id,
            ),
        )
        assert route.gauge_id == expected_gauge.gauge_id
        assert route.gauge_threshold_status == gauge_by_id[route.gauge_id].threshold_status
        sample = gauge_sample_by_key[(route.gauge_id, route.gauge_sample_time_s)]
        assert route.stage_millifeet == sample.stage_millifeet
        assert route.observation_age_s == (
            request.observation.context.simulation_time_s - route.crossing_sample_time_s
        )
        request_hash = hashlib.sha256(
            canonical_json_bytes(request.model_dump(mode="json"))
        ).hexdigest()
        assert evidence.observation_window_hash == request_hash
        assert evidence.observation_age_s == max(
            route.observation_age_s,
            request.observation.context.call_observation_age_s,
            request.observation.context.simulation_time_s - route.gauge_sample_time_s,
        )
        assert request.observation.context.compatible_resources
        assert all(
            request.plan.first_action.parameters["required_capability"] in item.capabilities
            for item in request.observation.context.compatible_resources
        )
        assert all("local capacity" not in claim for claim in evidence.predicted_claims)
    automatic_aid = [
        item
        for request in result.predictor_requests
        for item in request.observation.context.compatible_resources
        if item.availability_mode == "preauthorized-automatic-aid-fixed-staging"
    ]
    assert automatic_aid
    assert all(item.origin_base_id == "FAC-RIO-VISTA-55" for item in automatic_aid)
    assert all(item.staged_base_id == "FAC-FIRE-01" for item in automatic_aid)


def test_every_commitment_has_exact_clear_trace_authorization() -> None:
    result = run_delta_small(
        generate_delta_small(CONFIG, GEOGRAPHY),
        ToyActionPrefixPredictor(),
        POLICY,
    )
    record_by_version = {
        (record.record_id, record.record_version): record for record in result.trace_records
    }
    commitment_ids = {item.commitment_id for item in result.commitments}
    assert commitment_ids == {item.authorizing_commitment_id for item in result.outcomes}
    for commitment in result.commitments:
        record = record_by_version[
            (commitment.authorizing_record_id, commitment.authorizing_record_version)
        ]
        assert record.consumer_actions
        assert record.consumer_actions[-1].decision.value == "clear"
        event = next(
            item for item in result.decisions if item.commitment_id == commitment.commitment_id
        )
        assert (event.trace_record_id, event.trace_record_version) == (
            commitment.authorizing_record_id,
            commitment.authorizing_record_version,
        )
        outcome = next(
            item
            for item in result.outcomes
            if item.authorizing_commitment_id == commitment.commitment_id
        )
        assert (
            outcome.authorizing_trace_record_id,
            outcome.authorizing_trace_record_version,
        ) == (
            commitment.authorizing_record_id,
            commitment.authorizing_record_version,
        )


def test_service_outcomes_distinguish_observed_completion_from_scenario_censoring() -> None:
    scenario = generate_delta_small(CONFIG, GEOGRAPHY)
    result = run_delta_small(scenario, ToyActionPrefixPredictor(), POLICY)
    assert result.outcomes
    assert any(item.status == "active_at_scenario_censoring" for item in result.outcomes)
    decisions = {item.commitment_id: item for item in result.decisions if item.commitment_id}
    for outcome in result.outcomes:
        decision = decisions[outcome.authorizing_commitment_id]
        assert decision.scheduled_completion_s == outcome.scheduled_completion_s
        assert decision.censoring_s == scenario.config.timeline.duration_s
        assert outcome.censoring_s == scenario.config.timeline.duration_s
        if outcome.scheduled_completion_s <= scenario.config.timeline.duration_s:
            assert outcome.status == "completed_within_window"
            assert outcome.observed_completion_s == outcome.scheduled_completion_s
        else:
            assert outcome.status == "active_at_scenario_censoring"
            assert outcome.observed_completion_s is None
            assert decision.service_complete_s > scenario.config.timeline.duration_s


def test_engine_is_never_counted_or_dispatched_for_water_rescue() -> None:
    scenario = generate_delta_small(CONFIG, GEOGRAPHY)
    engine = next(unit for unit in scenario.resources.units if "ENGINE" in unit.resource_id)
    assert "water_rescue" not in engine.capabilities
    result = run_delta_small(scenario, ToyActionPrefixPredictor(), POLICY)
    call_by_id = {item.call_id: item for item in scenario.observations.calls}
    assert all(
        not (
            event.event_type == "allocation"
            and call_by_id[event.call_id].reported.call_type == "C-STR"
            and "ENGINE" in event.resource_id
        )
        for event in result.decisions
    )


def test_automatic_aid_schedule_is_fixed_preauthorized_and_not_mutual_aid() -> None:
    scenario = generate_delta_small(CONFIG, GEOGRAPHY)
    automatic_aid = [
        unit
        for unit in scenario.resources.units
        if unit.availability_mode == "preauthorized-automatic-aid-fixed-staging"
    ]
    assert scenario.resources.schema_version == "delta-resources-v3"
    assert scenario.resources.resource_profile_id == ("kappa-0.5-local-plus-automatic-aid-v1")
    assert len(automatic_aid) == 2
    assert {unit.resource_class for unit in automatic_aid} == {
        "type_i_engine",
        "zodiac_rescue_boat",
    }
    assert {unit.available_from_s for unit in automatic_aid} == {5_400}
    assert all(unit.origin_base_id == "FAC-RIO-VISTA-55" for unit in automatic_aid)
    assert all(unit.base_id == "FAC-FIRE-01" for unit in automatic_aid)

    result = run_delta_small(scenario, ToyActionPrefixPredictor(), POLICY)
    assert {event.event_type for event in result.decisions} <= {
        "allocation",
        "refusal",
        "repair",
    }
    serialized = canonical_json_bytes(result.model_dump(mode="json")).lower()
    for forbidden in (b"mutual-aid-request", b"authority-transfer", b"negotiation", b"federation"):
        assert forbidden not in serialized


def test_each_physical_resource_has_at_most_one_concurrent_commitment() -> None:
    result = run_delta_small(
        generate_delta_small(CONFIG, GEOGRAPHY),
        ToyActionPrefixPredictor(),
        POLICY,
    )
    intervals_by_resource: dict[str, list[tuple[int, int]]] = {}
    for event in result.decisions:
        if event.event_type != "allocation" or event.service_complete_s is None:
            continue
        intervals_by_resource.setdefault(event.resource_id, []).append(
            (event.simulation_time_s, event.service_complete_s)
        )
    for intervals in intervals_by_resource.values():
        ordered = sorted(intervals)
        assert all(left[1] <= right[0] for left, right in pairwise(ordered))


def test_gross_load_is_policy_independent_and_residual_accounting_is_explicit() -> None:
    scenario = generate_delta_small(CONFIG, GEOGRAPHY)
    toy_result = run_delta_small(scenario, ToyActionPrefixPredictor(), POLICY)
    held_result = run_delta_small(scenario, _mlp(), POLICY)
    assert [item.gross_load_ratio_milli for item in toy_result.demand_windows] == [
        item.gross_load_ratio_milli for item in held_result.demand_windows
    ]
    assert toy_result.allocated > 0
    assert held_result.allocated == 0
    assert any(item.commitment_covered_demand_units > 0 for item in toy_result.demand_windows)
    for item in toy_result.demand_windows:
        assert (
            item.commitment_covered_demand_units + item.residual_unassigned_demand_units
            == item.active_demand_service_units
        )
        if item.active_demand_service_units == 0:
            assert item.gross_load_ratio_milli == 0
            assert item.residual_pressure_ratio_milli == 0
        if item.residual_unserviceable:
            assert item.residual_unassigned_demand_units > 0
            assert item.free_compatible_capacity_units == 0
            assert item.residual_pressure_ratio_milli is None


def test_false_report_commitment_consumes_capacity_without_covering_truth() -> None:
    scenario = generate_delta_small(CONFIG, GEOGRAPHY)
    result = run_delta_small(scenario, ToyActionPrefixPredictor(), POLICY)
    false_call_id = next(
        item.call_id
        for item in scenario.observations.lineage
        if item.relationship == "false_report"
    )
    allocation = next(event for event in result.decisions if event.event_type == "allocation")
    synthetic_false_commitment = allocation.model_copy(update={"call_id": false_call_id})
    baseline = evaluate_capacity_windows(scenario, [])
    with_false_commitment = evaluate_capacity_windows(scenario, [synthetic_false_commitment])
    assert all(item.commitment_covered_demand_units == 0 for item in with_false_commitment)
    assert any(
        amended.free_compatible_capacity_units < uncommitted.free_compatible_capacity_units
        for amended, uncommitted in zip(with_false_commitment, baseline, strict=True)
    )


def test_fixed_axis_predictor_substitution_changes_only_model_provenance() -> None:
    scenario = generate_delta_small(CONFIG, GEOGRAPHY)
    toy_result = run_delta_small(scenario, ToyActionPrefixPredictor(), POLICY)
    mlp_result = run_delta_small(scenario, _mlp(), POLICY)
    vjepa = _vjepa()
    manifest = json.loads((FIXTURES / "manifest.json").read_text("utf-8"))
    visual_reference = PredictorVisualFeatureRef(
        observation_id="vjepa_ci_feature",
        observation_sha256="c" * 64,
        feature_cache_sha256=manifest["artifacts"]["vjepa_ci_feature.npz"],
        feature_schema_version=manifest["feature_schema_version"],
        encoder_version=manifest["encoder_version"],
        encoder_checkpoint_hash=manifest["encoder_checkpoint_hash"],
        captured_at_s=0,
    )
    visual_features = {
        call.call_id: visual_reference.model_copy(update={"captured_at_s": call.received_s})
        for call in scenario.observations.calls
    }
    vjepa_result = run_delta_small(
        scenario,
        vjepa,
        POLICY,
        visual_features=visual_features,
    )

    call_ids = [item.call_id for item in scenario.observations.calls]
    assert [item.evidence_id for item in toy_result.evidence] == [
        f"evidence-{call_id}" for call_id in call_ids
    ]
    assert [item.evidence_id for item in mlp_result.evidence] == [
        item.evidence_id for item in toy_result.evidence
    ]
    assert [item.evidence_id for item in vjepa_result.evidence] == [
        item.evidence_id for item in toy_result.evidence
    ]
    assert {item.predictor_version for item in toy_result.evidence} == {"toy-action-prefix-v2"}
    assert {item.predictor_version for item in mlp_result.evidence} == {"mlp-delta-fixture-v1"}
    assert {item.predictor_version for item in vjepa_result.evidence} == {vjepa.predictor_version}
    assert all(
        item.trace_decision == "hold"
        for item in mlp_result.decisions
        if item.event_type != "repair"
    )
    assert all(
        item.trace_decision == "hold"
        for item in vjepa_result.decisions
        if item.event_type != "repair"
    )
    assert mlp_result.allocated == 0
    assert vjepa_result.allocated == 0
    assert toy_result.allocated > 0
    assert (
        [item.gross_load_ratio_milli for item in toy_result.demand_windows]
        == [item.gross_load_ratio_milli for item in mlp_result.demand_windows]
        == [item.gross_load_ratio_milli for item in vjepa_result.demand_windows]
    )
    expected_prior = scenario.prior_profile.profile_id
    assert all(
        f"prior_profile={expected_prior}" in item.experimental_profile.notes
        for item in (*toy_result.evidence, *mlp_result.evidence, *vjepa_result.evidence)
    )


def test_vjepa_feature_provider_fails_closed_on_unsafe_or_unverifiable_inputs(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError):
        PredictorVisualFeatureRef(
            observation_id="../escape",
            observation_sha256="a" * 64,
            feature_cache_sha256="b" * 64,
            feature_schema_version="vjepa-frozen-feature-v1",
            encoder_version="test-encoder",
            encoder_checkpoint_hash="b" * 64,
            captured_at_s=0,
        )

    predictor = _vjepa()
    scenario = generate_delta_small(CONFIG, GEOGRAPHY)
    call = scenario.observations.calls[0]
    unsafe_reference = PredictorVisualFeatureRef(
        observation_id="missing-safe-id",
        observation_sha256="a" * 64,
        feature_cache_sha256="c" * 64,
        feature_schema_version="vjepa-frozen-feature-v1",
        encoder_version=predictor.encoder_version,
        encoder_checkpoint_hash=predictor.encoder_checkpoint_hash,
        captured_at_s=call.received_s,
    )
    with pytest.raises(PredictorInputUnavailable, match="absent"):
        run_delta_small(
            scenario.model_copy(
                update={
                    "observations": scenario.observations.model_copy(
                        update={"calls": [call], "lineage": []}
                    )
                }
            ),
            predictor,
            POLICY,
            visual_features={call.call_id: unsafe_reference},
        )

    target = tmp_path / "target.npz"
    write_deterministic_feature_cache(
        target,
        feature=np.asarray([0.1], dtype=np.float32),
        observation_sha256="a" * 64,
        encoder_version="test-encoder",
        encoder_checkpoint_hash="b" * 64,
    )
    (tmp_path / "linked.npz").symlink_to(target)
    provider = CachedVJEPAFeatureProvider(
        tmp_path,
        encoder_version="test-encoder",
        encoder_checkpoint_hash="b" * 64,
    )
    request = PredictorRequest.model_validate(
        {
            "plan": {
                "plan_id": "safe-plan",
                "name": "safe",
                "actions": [
                    {
                        "action_type": "dispatch_rescue_boat",
                        "actor_id": "boat",
                        "route_id": "XNG-04",
                    }
                ],
                "utility": 1.0,
                "reversible_first_action": False,
            },
            "observation": {
                "routes": [
                    {
                        "route_id": "XNG-04",
                        "report": "open",
                        "nominal_travel_s": 1.0,
                    }
                ],
                "context": {
                    "visual_feature": {
                        "observation_id": "linked",
                        "observation_sha256": "a" * 64,
                        "feature_cache_sha256": sha256_file(target),
                        "feature_schema_version": "vjepa-frozen-feature-v1",
                        "encoder_version": "test-encoder",
                        "encoder_checkpoint_hash": "b" * 64,
                        "captured_at_s": 0,
                    }
                },
            },
        }
    )
    with pytest.raises(PredictorInputUnavailable, match="symlink"):
        provider.features(request)

    def request_for(observation_id: str, digest: str) -> PredictorRequest:
        cache_path = tmp_path / f"{observation_id}.npz"
        context = request.observation.context.model_copy(
            update={
                "visual_feature": PredictorVisualFeatureRef(
                    observation_id=observation_id,
                    observation_sha256=digest,
                    feature_cache_sha256=sha256_file(cache_path),
                    feature_schema_version="vjepa-frozen-feature-v1",
                    encoder_version="test-encoder",
                    encoder_checkpoint_hash="b" * 64,
                    captured_at_s=0,
                )
            }
        )
        return request.model_copy(
            update={"observation": request.observation.model_copy(update={"context": context})}
        )

    write_deterministic_feature_cache(
        tmp_path / "digest.npz",
        feature=np.asarray([0.1], dtype=np.float32),
        observation_sha256="d" * 64,
        encoder_version="test-encoder",
        encoder_checkpoint_hash="b" * 64,
    )
    with pytest.raises(PredictorInputUnavailable, match="digest mismatch"):
        provider.features(request_for("digest", "e" * 64))

    cache_mismatch = request_for("digest", "d" * 64)
    bad_cache_reference = cache_mismatch.observation.context.visual_feature.model_copy(
        update={"feature_cache_sha256": "0" * 64}
    )
    cache_mismatch = cache_mismatch.model_copy(
        update={
            "observation": cache_mismatch.observation.model_copy(
                update={
                    "context": cache_mismatch.observation.context.model_copy(
                        update={"visual_feature": bad_cache_reference}
                    )
                }
            )
        }
    )
    with pytest.raises(PredictorInputUnavailable, match="feature-cache digest mismatch"):
        provider.features(cache_mismatch)

    stale = request_for("digest", "d" * 64)
    stale = stale.model_copy(
        update={
            "observation": stale.observation.model_copy(
                update={
                    "context": stale.observation.context.model_copy(
                        update={"simulation_time_s": 301}
                    )
                }
            )
        }
    )
    with pytest.raises(PredictorInputUnavailable, match="stale"):
        provider.features(stale)

    write_deterministic_feature_cache(
        tmp_path / "nonfinite.npz",
        feature=np.asarray([float("nan")], dtype=np.float32),
        observation_sha256="f" * 64,
        encoder_version="test-encoder",
        encoder_checkpoint_hash="b" * 64,
    )
    with pytest.raises(ValueError, match="finite"):
        provider.features(request_for("nonfinite", "f" * 64))


def test_geography_geometry_provenance_and_operational_precision_are_valid() -> None:
    catalog = load_geography_catalog(GEOGRAPHY)
    build_manifest = json.loads(GEOGRAPHY_MANIFEST.read_text("utf-8"))
    assert build_manifest["raster_crs"] == "EPSG:26910"
    assert build_manifest["raster_vertical_datum"] == "NAVD88 metres"
    dem_records = [item for item in build_manifest["sources"] if "delta-10m" in item["source_id"]]
    assert {item["archive_member"] for item in dem_records} == {
        None,
        "dem_delta_10m_20250312.tif",
    }
    assert all(item["redistribution_status"] for item in build_manifest["sources"])
    assert all(item.license_name and item.license_locator for item in catalog.sources)

    island_polygons = {}
    for island in catalog.islands:
        polygons = [
            Polygon([(point.easting_mm, point.northing_mm) for point in ring.points])
            for ring in island.geometry.polygons
        ]
        assert all(polygon.is_valid and polygon.area > 0 for polygon in polygons)
        island_polygons[island.island_id] = polygons

    scenario = generate_delta_small(CONFIG, GEOGRAPHY)
    for structure in scenario.truth.structures:
        point = Point(structure.easting_mm, structure.northing_mm)
        assert any(polygon.covers(point) for polygon in island_polygons[structure.island_id])

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:26910", always_xy=True)
    for island in catalog.islands:
        east, north = transformer.transform(
            island.centroid.longitude_e7 / 10_000_000,
            island.centroid.latitude_e7 / 10_000_000,
        )
        assert abs(round(east * 1000) - island.centroid.easting_mm) <= 10
        assert abs(round(north * 1000) - island.centroid.northing_mm) <= 10

    lines = [
        LineString([(point.easting_mm, point.northing_mm) for point in segment.points])
        for waterway in catalog.waterways
        for segment in waterway.segments
    ]
    for crossing in catalog.crossings:
        crossing_point = Point(crossing.location.easting_mm, crossing.location.northing_mm)
        assert min(crossing_point.distance(line) for line in lines) <= 150_000

    facility_by_id = {item.facility_id: item for item in catalog.facilities}
    assert facility_by_id["FAC-FIRE-01"].operational_for_routing is True
    assert facility_by_id["FAC-FIRE-01"].location_precision == "secondary-address-geocode"
    assert facility_by_id["FAC-RAMP-01"].operational_for_routing is False
    assert "not-ramp-survey" in facility_by_id["FAC-RAMP-01"].location_precision
    assert not (GEOGRAPHY.parent / "delta_small_geography_v1.yaml").exists()


def test_runtime_and_publication_are_offline_and_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deny_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden during Delta runtime")

    monkeypatch.setattr(socket, "socket", deny_network)
    scenario = generate_delta_small(CONFIG, GEOGRAPHY)
    first = run_delta_small(scenario, ToyActionPrefixPredictor(), POLICY)
    second = run_delta_small(scenario, ToyActionPrefixPredictor(), POLICY)
    assert first == second

    from trace_jepa.scenario.delta.pipeline import execute_delta_small

    reference = tmp_path / "reference"
    execute_delta_small(
        CONFIG,
        GEOGRAPHY,
        POLICY,
        reference,
        ToyActionPrefixPredictor(),
    )
    first_figures = tmp_path / "figures-a"
    second_figures = tmp_path / "figures-b"
    first_manifest = publish_reference_bundle(reference, first_figures)
    second_manifest = publish_reference_bundle(reference, second_figures)
    assert first_manifest == second_manifest
    assert first_manifest["schema_version"] == "delta-small-publication-bundle-v4"
    published_names = {item["file_name"] for item in first_manifest["artifacts"]}
    assert {
        "delta_small_reconciliation.svg",
        "delta_small_strict_load.svg",
        "delta_small_strict_residual_pressure.svg",
        "delta_small_metric_sensitivity.svg",
    } <= published_names
    for descriptor in first_manifest["artifacts"]:
        file_name = descriptor["file_name"]
        assert (first_figures / file_name).read_bytes() == (second_figures / file_name).read_bytes()
