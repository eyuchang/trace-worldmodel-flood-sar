from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
import yaml

from trace_jepa.predictor import ToyActionPrefixPredictor
from trace_jepa.scenario.delta.artifacts import (
    ArtifactMismatchError,
    sha256_file,
    verify_scenario_artifacts,
)
from trace_jepa.scenario.delta.generator import GENERATION_ORDER, generate_delta_small
from trace_jepa.scenario.delta.loading import (
    DeltaConfigurationError,
    load_acceptance_config,
    load_scenario_config,
)
from trace_jepa.scenario.delta.pipeline import execute_delta_small, verify_exact_replay
from trace_jepa.scenario.delta.population import (
    _channel_probabilities,
    _hourly_channel_probabilities,
    _latent_hour_rates,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPOSITORY_ROOT / "configs/scenarios/wf_dfld_01_small.yaml"
ACCEPTANCE_PATH = REPOSITORY_ROOT / "configs/scenarios/wf_dfld_01_small_acceptance_v2.yaml"
HISTORICAL_ACCEPTANCE_PATH = REPOSITORY_ROOT / "configs/scenarios/wf_dfld_01_small_acceptance.yaml"
GEOGRAPHY_PATH = REPOSITORY_ROOT / "data/scenario/delta/geography/delta_small_geography_v2.yaml"
GEOGRAPHY_MANIFEST_PATH = REPOSITORY_ROOT / "data/scenario/delta/geography/build_manifest_v2.json"
POLICY_PATH = REPOSITORY_ROOT / "configs/policies/trace_delta_small_v1.yaml"


def _write_axis_variant(
    tmp_path: Path,
    axis_name: str,
    axis_value: object,
) -> Path:
    config = load_scenario_config(CONFIG_PATH)
    payload = config.model_dump(mode="json")
    payload["axes"][axis_name] = axis_value
    path = tmp_path / f"{axis_name}.yaml"
    with path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(payload, stream, sort_keys=True)
    return path


def test_small_contract_and_generation_order_are_frozen() -> None:
    scenario = generate_delta_small(CONFIG_PATH, GEOGRAPHY_PATH)
    assert scenario.generation_order == GENERATION_ORDER
    assert scenario.config.extent.island_ids == ["ISL-01", "ISL-02"]
    assert scenario.config.extent.crossing_ids == ["XNG-03", "XNG-04"]
    assert scenario.config.timeline.duration_s == 21_600
    assert scenario.config.extent.roster_size == 60
    assert scenario.config.expected.breaches == 0
    assert all(not levee.breach for levee in scenario.truth.levees)
    assert {item.island_id for item in scenario.truth.structures} == {"ISL-01", "ISL-02"}
    assert {item.person_id for item in scenario.truth.person_positions} == {
        item.person_id for item in scenario.truth.people
    }
    assert any(item.simulation_time_s > 0 for item in scenario.truth.person_positions)
    assert all(item.status == "open" for item in scenario.crossing_states)
    gauge_by_id = {gauge.gauge_id: gauge for gauge in scenario.geography.gauges}
    assert gauge_by_id["RVB"].threshold_status == "verified-cdec-2026-08-05"
    assert gauge_by_id["MRU"].action_stage_millifeet == -1
    assert gauge_by_id["FPT"].minor_flood_stage_millifeet == -1


def test_acceptance_protocol_is_preregistered_before_recalibration() -> None:
    protocol = load_acceptance_config(ACCEPTANCE_PATH)
    historical = load_acceptance_config(HISTORICAL_ACCEPTANCE_PATH)
    assert protocol.book_seed == 20260803
    assert protocol.development_ensemble.first_seed == protocol.book_seed
    assert protocol.development_ensemble.seed_count == 100
    assert protocol.schema_version == "delta-small-acceptance-v6"
    assert protocol.balanced_confirmatory_ensemble is not None
    assert len(protocol.balanced_confirmatory_ensemble.seeds) == 100
    historical_seeds = {
        seed
        for ensemble in (
            historical.confirmatory_ensemble,
            historical.amended_confirmatory_ensemble,
            historical.final_confirmatory_ensemble,
            historical.spatial_confirmatory_ensemble,
        )
        if ensemble is not None
        for seed in ensemble.seeds
    }
    assert set(protocol.balanced_confirmatory_ensemble.seeds).isdisjoint(historical_seeds)
    assert protocol.call_process.expected_total_mean == 40.0
    assert protocol.call_process.configured_peak_intensity_per_hour == 12.0
    assert protocol.demand_capacity.target_peak_ratio == 1.5
    assert protocol.performance.maximum_generate_run_replay_s == 55.0


def test_geography_uses_versioned_authoritative_anchors() -> None:
    scenario = generate_delta_small(CONFIG_PATH, GEOGRAPHY_PATH)
    assert scenario.geography.coordinate_reference == "EPSG:4326+EPSG:26910-fixed-point-v1"
    assert len(scenario.geography.waterways) >= 3
    assert len(scenario.geography.facilities) >= 2
    governed_islands = {
        island_id
        for authority in scenario.geography.governance
        for island_id in authority.island_ids
    }
    assert governed_islands == {"ISL-01", "ISL-02"}
    for source in scenario.geography.sources:
        assert len(source.sha256) == 64
        assert source.byte_length > 0
        assert source.license_name
    for island in scenario.geography.islands:
        assert len(island.geometry.polygons) > 0
        assert -121_8500000 <= island.centroid.longitude_e7 <= -121_4500000
        assert 379_500000 <= island.centroid.latitude_e7 <= 383_000000


def test_geography_manifest_and_tracked_snapshots_match_declared_hashes() -> None:
    scenario = generate_delta_small(CONFIG_PATH, GEOGRAPHY_PATH)
    assert scenario.geography.build_manifest_sha256 == sha256_file(GEOGRAPHY_MANIFEST_PATH)
    geography_root = GEOGRAPHY_PATH.parent
    for source in scenario.geography.sources:
        if not source.snapshot_file_name.startswith("sources/"):
            continue
        snapshot_path = geography_root / source.snapshot_file_name
        assert snapshot_path.is_file()
        assert snapshot_path.stat().st_size == source.byte_length
        assert sha256_file(snapshot_path) == source.sha256


def test_observations_have_offline_truth_lineage_without_truth_leakage() -> None:
    scenario = generate_delta_small(CONFIG_PATH, GEOGRAPHY_PATH)
    incident_ids = {incident.incident_id for incident in scenario.truth.incidents}
    call_ids = {call.call_id for call in scenario.observations.calls}
    assert call_ids == {lineage.call_id for lineage in scenario.observations.lineage}
    assert all(
        lineage.truth_incident_id in incident_ids
        for lineage in scenario.observations.lineage
        if lineage.truth_incident_id is not None
    )
    assert all(
        lineage.relationship == "false_report"
        for lineage in scenario.observations.lineage
        if lineage.truth_incident_id is None
    )
    controller_payload = [call.model_dump(mode="json") for call in scenario.observations.calls]
    assert "truth_incident_id" not in str(controller_payload)
    assert "truth_person_ids" not in str(controller_payload)


def test_axis_sweeps_preserve_declared_invariant_layers(tmp_path: Path) -> None:
    baseline = generate_delta_small(CONFIG_PATH, GEOGRAPHY_PATH)
    higher_severity = generate_delta_small(
        _write_axis_variant(tmp_path, "sigma", 0.6), GEOGRAPHY_PATH
    )
    higher_capacity = generate_delta_small(
        _write_axis_variant(tmp_path, "kappa", 1.0), GEOGRAPHY_PATH
    )
    slower_mobilization = generate_delta_small(
        _write_axis_variant(tmp_path, "mu", 2.0), GEOGRAPHY_PATH
    )
    lower_information = generate_delta_small(
        _write_axis_variant(tmp_path, "iota", 0.6), GEOGRAPHY_PATH
    )
    fragmented_governance = generate_delta_small(
        _write_axis_variant(tmp_path, "phi", 2), GEOGRAPHY_PATH
    )
    lower_prior = generate_delta_small(_write_axis_variant(tmp_path, "pi", 0.5), GEOGRAPHY_PATH)
    vulnerable_exposure = generate_delta_small(
        _write_axis_variant(tmp_path, "exposure_profile", "isleton_high_vulnerability_v1"),
        GEOGRAPHY_PATH,
    )
    degraded_baseline = generate_delta_small(
        _write_axis_variant(tmp_path, "delta", 0.6), GEOGRAPHY_PATH
    )

    assert baseline.weather != higher_severity.weather
    assert baseline.gauges != higher_severity.gauges
    assert baseline.truth != higher_severity.truth
    assert baseline.resources == higher_severity.resources

    assert baseline.weather == higher_capacity.weather
    assert baseline.gauges == higher_capacity.gauges
    assert baseline.truth == higher_capacity.truth
    assert baseline.resources != higher_capacity.resources

    assert baseline.weather == slower_mobilization.weather
    assert baseline.gauges == slower_mobilization.gauges
    assert baseline.truth == slower_mobilization.truth
    assert baseline.resources != slower_mobilization.resources
    assert [unit.resource_class for unit in baseline.resources.units] == [
        unit.resource_class for unit in slower_mobilization.resources.units
    ]

    assert baseline.weather == lower_information.weather
    assert baseline.gauges == lower_information.gauges
    assert baseline.truth == lower_information.truth
    assert baseline.observations != lower_information.observations

    assert baseline.weather == fragmented_governance.weather
    assert baseline.gauges == fragmented_governance.gauges
    assert baseline.truth == fragmented_governance.truth
    assert baseline.resources.units == fragmented_governance.resources.units
    assert (
        baseline.resources.coordination_domain
        != fragmented_governance.resources.coordination_domain
    )

    assert baseline.geography == lower_prior.geography
    assert baseline.weather == lower_prior.weather
    assert baseline.gauges == lower_prior.gauges
    assert baseline.truth == lower_prior.truth
    assert baseline.observations == lower_prior.observations
    assert baseline.resources == lower_prior.resources
    assert baseline.prior_profile != lower_prior.prior_profile

    assert baseline.weather == vulnerable_exposure.weather
    assert baseline.gauges == vulnerable_exposure.gauges
    assert baseline.truth != vulnerable_exposure.truth
    assert baseline.resources == vulnerable_exposure.resources

    assert baseline.weather == degraded_baseline.weather
    assert baseline.gauges == degraded_baseline.gauges
    assert baseline.truth == degraded_baseline.truth
    assert baseline.resources != degraded_baseline.resources


def test_hourly_observation_calibration_matches_frozen_analytical_intensity() -> None:
    scenario = generate_delta_small(CONFIG_PATH, GEOGRAPHY_PATH)
    parameters = _hourly_channel_probabilities(
        scenario.config,
        scenario.weather,
        scenario.crossing_states,
    )
    latent_rates = _latent_hour_rates(
        scenario.config,
        scenario.weather,
        scenario.crossing_states,
    )
    false_per_hour = _channel_probabilities(scenario.config.axes.iota)["false_report_mean"] / 6.0
    shifts = {
        "first_report": 209.5 / 3600.0,
        "duplicate": 509.5 / 3600.0,
        "multi_channel": 389.5 / 3600.0,
        "revision": 899.5 / 3600.0,
    }
    incoming = 0.0
    expected_arrivals: list[float] = []
    for hour, (rate, item) in enumerate(zip(latent_rates, parameters, strict=True)):
        hour_shifts = {key: 0.0 if hour == 5 else value for key, value in shifts.items()}
        current = (
            rate
            * item["reporting"]
            * (
                1.0
                - hour_shifts["first_report"]
                + sum(
                    item[key] * (1.0 - hour_shifts[key])
                    for key in ("duplicate", "multi_channel", "revision")
                )
            )
        )
        expected_arrivals.append(false_per_hour + incoming + current)
        incoming = item["analytical_expected_spill_to_next_hour"]
    assert expected_arrivals == pytest.approx(
        scenario.config.call_process.hourly_intensity,
        abs=1e-10,
    )


def test_small_run_exercises_allocation_refusal_and_repair(tmp_path: Path) -> None:
    execution = execute_delta_small(
        CONFIG_PATH,
        GEOGRAPHY_PATH,
        POLICY_PATH,
        tmp_path / "reference",
        ToyActionPrefixPredictor(),
    )
    assert execution.run_result.allocated > 0
    assert execution.run_result.refused > 0
    assert execution.run_result.repaired > 0
    assert execution.run_result.peak_gross_load_ratio_milli / 1000 == 1.5
    assert execution.run_result.peak_finite_residual_pressure_ratio_milli / 1000 == 3.0
    assert execution.run_result.allocated == 13
    assert execution.run_result.refused == 22
    assert execution.run_result.repaired == 10


def test_artifacts_are_byte_identical_on_clean_replay(tmp_path: Path) -> None:
    predictor = ToyActionPrefixPredictor()
    reference = tmp_path / "reference"
    replay = tmp_path / "replay"
    execution = execute_delta_small(
        CONFIG_PATH,
        GEOGRAPHY_PATH,
        POLICY_PATH,
        reference,
        predictor,
    )
    verify_exact_replay(
        CONFIG_PATH,
        GEOGRAPHY_PATH,
        POLICY_PATH,
        reference,
        replay,
        predictor,
    )
    manifest = verify_scenario_artifacts(reference)
    assert manifest == execution.manifest
    hidden = {
        descriptor.name for descriptor in manifest.artifacts if descriptor.contains_hidden_truth
    }
    assert hidden == {"ground_truth", "call_lineage"}
    expected_inputs = {
        "scenario_configuration",
        "geography_catalog",
        "geography_build_manifest",
        "physical_parameter_table",
        "truth_observation_resource_parameters",
        "predictor_prior",
        "policy",
        "predictor_model",
        "predictor_calibration",
        "environment_contract",
        "dependency_lock",
        "registered_acceptance_protocol",
        "automatic_aid_source_extract",
    }
    if (REPOSITORY_ROOT / "docs/delta/validation/WF_DFLD_01_SMALL_VALIDATION_V2.json").exists():
        expected_inputs.add("registered_validation_report")
    assert {item.name for item in manifest.inputs} == expected_inputs
    assert all(len(item.sha256) == 64 for item in manifest.inputs)


def test_exact_replay_preserves_recorded_source_commit_across_artifact_commits(
    tmp_path: Path,
) -> None:
    predictor = ToyActionPrefixPredictor()
    reference = tmp_path / "reference"
    replay = tmp_path / "replay"
    source_commit = "a" * 40
    execute_delta_small(
        CONFIG_PATH,
        GEOGRAPHY_PATH,
        POLICY_PATH,
        reference,
        predictor,
        recorded_git_commit=source_commit,
    )

    verify_exact_replay(
        CONFIG_PATH,
        GEOGRAPHY_PATH,
        POLICY_PATH,
        reference,
        replay,
        predictor,
    )

    assert verify_scenario_artifacts(replay).git_commit == source_commit
    assert (reference / "manifest.json").read_bytes() == (replay / "manifest.json").read_bytes()


def test_manifest_verification_fails_loudly_after_artifact_tampering(
    tmp_path: Path,
) -> None:
    output = tmp_path / "tampered"
    execute_delta_small(
        CONFIG_PATH,
        GEOGRAPHY_PATH,
        POLICY_PATH,
        output,
        ToyActionPrefixPredictor(),
    )
    with (output / "calls.json").open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ArtifactMismatchError, match="length mismatch"):
        verify_scenario_artifacts(output)


def test_small_loader_rejects_out_of_scope_breach_configuration(
    tmp_path: Path,
) -> None:
    config = load_scenario_config(CONFIG_PATH)
    payload = config.model_dump(mode="json")
    payload["expected"]["breaches"] = 1
    path = tmp_path / "breach.yaml"
    with path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(payload, stream, sort_keys=True)
    with pytest.raises(DeltaConfigurationError, match="frozen Small contract"):
        load_scenario_config(path)


def test_small_generate_run_and_replay_stays_below_ci_budget(tmp_path: Path) -> None:
    started = time.perf_counter()
    predictor = ToyActionPrefixPredictor()
    execute_delta_small(
        CONFIG_PATH,
        GEOGRAPHY_PATH,
        POLICY_PATH,
        tmp_path / "reference",
        predictor,
    )
    verify_exact_replay(
        CONFIG_PATH,
        GEOGRAPHY_PATH,
        POLICY_PATH,
        tmp_path / "reference",
        tmp_path / "replay",
        predictor,
    )
    assert time.perf_counter() - started < 55.0


def test_all_registered_seed_studies_are_materialized_with_adverse_result_retained() -> None:
    path = REPOSITORY_ROOT / "docs/delta/validation/WF_DFLD_01_SMALL_VALIDATION.json"
    report = json.loads(path.read_text("utf-8"))
    studies = {item["study_id"]: item for item in report["studies"]}
    assert {item["seed_count"] for item in studies.values()} == {100}
    assert studies["confirmatory-v1-adverse"]["peak_demand_capacity_ratio"]["estimate"] == 2.5
    primary = studies["confirmatory-v4-primary"]
    assert primary["call_count"]["estimate"] == pytest.approx(40.0, abs=2.5)
    assert primary["call_count"]["hourly_mean_95"][3]["lower_95"] <= 12.0
    assert primary["call_count"]["hourly_mean_95"][3]["upper_95"] >= 12.0
    assert primary["operations"]["all_trace_chains_verified"] is True
    assert (
        primary["registered_gate_evaluation"]["median_peak_ratio_within_registered_band"] is False
    )


def test_v5_configuration_and_book_bundle_remain_immutable_audit_evidence() -> None:
    archived_config = REPOSITORY_ROOT / "configs/scenarios/wf_dfld_01_small_v1.yaml"
    book_v1 = REPOSITORY_ROOT / "data/scenario/delta/reference/wf_dfld_01_small_book_v1"
    assert sha256_file(archived_config) == (
        "a97cb37c0547183828019ca5bc56662af9d3cc73db5eebc906f8e3f11975939b"
    )
    assert sha256_file(book_v1 / "manifest.json") == (
        "ad69d57fde24db6c7c49080c71398bdbec59f7f164e42470c62e94c1e6581e19"
    )


def test_confirmatory_v5_report_is_complete_and_reports_all_frozen_gates() -> None:
    report_path = REPOSITORY_ROOT / "docs/delta/validation/WF_DFLD_01_SMALL_VALIDATION_V2.json"
    report = json.loads(report_path.read_text("utf-8"))
    protocol = load_acceptance_config(ACCEPTANCE_PATH)
    assert report["protocol_sha256"] == sha256_file(ACCEPTANCE_PATH)
    studies = {item["study_id"]: item for item in report["studies"]}
    assert set(studies) == {"development-v6", "confirmatory-v5-primary"}
    primary = studies["confirmatory-v5-primary"]
    assert primary["seed_count"] == 100
    assert protocol.balanced_confirmatory_ensemble is not None
    assert primary["seeds"] == protocol.balanced_confirmatory_ensemble.seeds
    assert primary["call_count"]["estimate"] == pytest.approx(40.0, abs=2.5)
    peak_interval = primary["call_count"]["hourly_mean_95"][3]
    assert peak_interval["lower_95"] <= 12.0 <= peak_interval["upper_95"]
    assert 1.4 <= primary["peak_gross_load_ratio"]["estimate"] <= 1.6
    assert primary["operations"]["all_trace_chains_verified"] is True
    assert (
        primary["resource_only_amendment_invariance"]["all_seeds_and_fields_byte_identical"] is True
    )
    assert (
        primary["registered_gate_evaluation"]["all_registered_numeric_and_chain_gates_met"] is True
    )
    assert all(report["book_walkthrough"]["registered_gate_evaluation"].values())


def test_automatic_aid_source_extract_is_explicit_about_provenance_limits() -> None:
    path = REPOSITORY_ROOT / "data/scenario/delta/resources/rio_vista_fire_source_extract_v1.json"
    source = json.loads(path.read_text("utf-8"))
    assert source["facts"]["street_address"] == "350 Main Street, Rio Vista, CA 94571"
    assert source["facts"]["location"]["precision"] == ("secondary-address-geocode-not-surveyed")
    assert source["scenario_assumptions_not_source_facts"]["automatic_aid_arrival_s"] == 5_400
    assert all(len(item["url_sha256"]) == 64 for item in source["sources"])
    assert all(item["upstream_content_sha256"] is None for item in source["sources"])
    assert "HTTP 403" in source["retrieval_note"]
