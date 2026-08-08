from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from trace_jepa.predictor import ToyActionPrefixPredictor
from trace_jepa.scenario.delta.artifacts import canonical_json_bytes
from trace_jepa.scenario.delta.generator import generate_delta_small_from_models
from trace_jepa.scenario.delta.geography_models import GeographyCatalog
from trace_jepa.scenario.delta.loading import load_geography_catalog, load_scenario_config
from trace_jepa.scenario.delta.models import (
    DeltaScenarioConfig,
    GeneratedScenario,
    PersonPosition,
)
from trace_jepa.scenario.delta.observations_v7 import (
    BASE_PRECISION_RANGES_M,
    channel_probabilities_v7,
    location_error_scale_v7,
    location_method_mixture_v7,
    reporting_probability_v7,
)
from trace_jepa.scenario.delta.observations_v8 import (
    BASE_REPORTING_BY_HOUR_V2,
    FALSE_REPORT_HOUR_WEIGHTS_V1,
    channel_probabilities_v8,
)
from trace_jepa.scenario.delta.pipeline import execute_delta_small
from trace_jepa.scenario.delta.randomness import KeyedRandom
from trace_jepa.scenario.delta.runner import run_delta_small
from trace_jepa.scenario.delta.truth_v7 import IncidentCandidate
from trace_jepa.scenario.delta.truth_v8 import TYPE_INTERCEPTS_V2, form_episode_candidates_v8
from trace_jepa.util import sha256_file

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "configs/scenarios/wf_dfld_01_small_v3.yaml"
V8_CONFIG = ROOT / "configs/scenarios/wf_dfld_01_small.yaml"
GEOGRAPHY = ROOT / "data/scenario/delta/geography/delta_small_geography_v3.yaml"
POLICY = ROOT / "configs/policies/trace_delta_small_v1.yaml"
SOURCE_PATH = CONFIG.resolve(strict=True)


def _models() -> tuple[DeltaScenarioConfig, GeographyCatalog]:
    return load_scenario_config(CONFIG), load_geography_catalog(GEOGRAPHY)


def _scenario(
    config: DeltaScenarioConfig,
    geography: GeographyCatalog,
    **axis_updates: object,
) -> GeneratedScenario:
    axes = config.axes.model_copy(update=axis_updates)
    return generate_delta_small_from_models(
        config.model_copy(update={"axes": axes}),
        geography,
        SOURCE_PATH,
    )


def _position_at(
    scenario: GeneratedScenario, person_id: str, simulation_time_s: int
) -> PersonPosition:
    eligible = [
        item
        for item in scenario.truth.person_positions
        if item.person_id == person_id and item.simulation_time_s <= simulation_time_s
    ]
    return eligible[-1]


def _episode_candidate(simulation_time_s: int, person_ids: tuple[str, ...]) -> IncidentCandidate:
    return IncidentCandidate(
        structure_id="STR-001",
        simulation_time_s=simulation_time_s,
        incident_type="C-WEL",
        person_ids=person_ids,
        factor=1.0,
        hazard_factor=1.0,
        occupancy_factor=1.0,
        vulnerability_factor=1.0,
        access_factor=1.0,
        causal_mechanism="test-eligibility",
    )


def test_v8_episode_keys_continue_only_while_eligibility_and_subjects_are_continuous() -> None:
    keyed = KeyedRandom(17, "parameter-hash", "ground_truth")
    formed = form_episode_candidates_v8(
        [
            _episode_candidate(0, ("PER-001",)),
            _episode_candidate(300, ("PER-001",)),
            _episode_candidate(600, ("PER-001", "PER-002")),
            _episode_candidate(1_200, ("PER-001", "PER-002")),
        ],
        keyed,
        300,
        {"C-WEL": 1.0},
    )
    assert formed[0].episode_key == formed[1].episode_key
    assert formed[1].episode_key != formed[2].episode_key
    assert formed[2].episode_key != formed[3].episode_key


def test_v8_episode_formation_preserves_keyed_candidate_draws() -> None:
    keyed = KeyedRandom(23, "parameter-hash", "ground_truth")
    candidates = [
        _episode_candidate(0, ("PER-001",)),
        _episode_candidate(300, ("PER-001",)),
        _episode_candidate(600, ("PER-001",)),
    ]
    formed = form_episode_candidates_v8(candidates, keyed, 300, {"C-WEL": 0.4})
    expected = [
        keyed.bernoulli(
            item.probability,
            "incident-candidate",
            item.candidate.structure_id,
            item.candidate.simulation_time_s,
            item.candidate.incident_type,
            "no-infrastructure",
        )
        for item in formed
    ]
    assert [item.accepted_draw for item in formed] == expected
    assert len({item.candidate_digest for item in formed}) == len(formed)
    assert len({item.draw_digest for item in formed}) == len(formed)


def test_v8_default_emits_episode_audit_and_nonunique_visible_descriptors() -> None:
    config = load_scenario_config(V8_CONFIG)
    geography = load_geography_catalog(GEOGRAPHY)
    scenario = generate_delta_small_from_models(config, geography, V8_CONFIG.resolve(strict=True))
    assert config.generator_version == "delta-small-generator-v8"
    assert scenario.truth.schema_version == "delta-ground-truth-v5"
    assert scenario.observations.schema_version == "delta-observations-v5"
    accepted = [
        item.episode_key
        for item in scenario.truth.candidate_audit
        if item.disposition == "accepted_as_truth_incident"
    ]
    assert len(accepted) == len(set(accepted)) == len(scenario.truth.incidents)
    assert any(
        item.disposition == "suppressed_existing_episode_incident"
        for item in scenario.truth.candidate_audit
    )
    descriptor_counts: dict[str, int] = defaultdict(int)
    for call in scenario.observations.calls:
        descriptor_counts[call.reported.description_token] += 1
    assert len(descriptor_counts) < len(scenario.observations.calls)
    assert all(not value.startswith(("INC", "PER", "STR")) for value in descriptor_counts)


def test_v8_calibration_record_matches_frozen_code_constants_and_development_scope() -> None:
    record = json.loads(
        (ROOT / "data/scenario/delta/calibration/v8_process_coefficients_v1.json").read_text(
            "utf-8"
        )
    )
    assert record["development_seeds"] == {
        "first_seed": 20260803,
        "last_seed": 20260902,
        "seed_count": 100,
    }
    assert record["truth"]["type_intercepts"] == TYPE_INTERCEPTS_V2
    assert (
        tuple(record["observations"]["fixed_reporting_probability_by_incident_onset_hour"])
        == BASE_REPORTING_BY_HOUR_V2
    )
    assert tuple(record["observations"]["fixed_false_report_hour_weights"]) == (
        FALSE_REPORT_HOUR_WEIGHTS_V1
    )
    assert record["solver"]["iterations_per_type"] == 80
    assert len(record["solver"]["candidate_trace"]) == 6 * 80
    assert record["truth"]["analytical_expected_total"] == 26.07
    assert record["observations"]["realized_development_call_mean"] == 40.01
    assert channel_probabilities_v8(0.6)["duplicate"] > channel_probabilities_v8(0.9)["duplicate"]


def test_v8_candidate_audit_is_a_separate_hidden_artifact(tmp_path: Path) -> None:
    execution = execute_delta_small(
        V8_CONFIG,
        GEOGRAPHY,
        POLICY,
        tmp_path / "run",
        ToyActionPrefixPredictor(),
    )
    descriptors = {item.name: item for item in execution.manifest.artifacts}
    assert descriptors["incident_candidate_audit"].contains_hidden_truth
    assert descriptors["ground_truth"].contains_hidden_truth
    assert not descriptors["controller_reconciliation"].contains_hidden_truth
    ground_truth = json.loads((tmp_path / "run/ground_truth.json").read_text("utf-8"))
    candidate_audit = json.loads(
        (tmp_path / "run/incident_candidate_audit.json").read_text("utf-8")
    )
    assert "candidate_audit" not in ground_truth
    assert len(candidate_audit) > len(ground_truth["incidents"])
    public_reconciliation = (tmp_path / "run/controller_reconciliation.json").read_text("utf-8")
    assert "truth_incident" not in public_reconciliation
    assert '"hidden_lineage_used":false' in public_reconciliation


def test_v7_contract_uses_new_keyed_namespace_and_versioned_artifacts() -> None:
    config, geography = _models()
    scenario = generate_delta_small_from_models(config, geography, SOURCE_PATH)
    assert config.schema_version == "trace-delta-scenario-v3"
    assert config.generator_version == "delta-small-generator-v7"
    assert config.randomness_namespace_version == "delta-small-generator-v7"
    assert scenario.geography.schema_version == "delta-small-geography-v3"
    assert scenario.truth.schema_version == "delta-ground-truth-v4"
    assert scenario.observations.schema_version == "delta-observations-v4"
    assert scenario.coordination is not None
    assert scenario.coordination.schema_version == "delta-coordination-v1"
    assert "coordination" in scenario.generation_order


def test_v7_calibration_record_binds_the_exact_fitted_implementations() -> None:
    record = json.loads(
        (ROOT / "data/scenario/delta/calibration/v7_process_coefficients_v1.json").read_text(
            "utf-8"
        )
    )
    assert record["inputs"]["truth_implementation_sha256"] == sha256_file(
        ROOT / "src/trace_jepa/scenario/delta/truth_v7.py"
    )
    assert record["inputs"]["observation_implementation_sha256"] == sha256_file(
        ROOT / "src/trace_jepa/scenario/delta/observations_v7.py"
    )
    assert record["truth"]["analytical_expected_total"] == 26.07
    assert record["development_diagnostics_after_freeze"]["realized_observed_call_mean"] == 38.77


def test_keyed_sigma_comparison_preserves_candidates_and_changes_hazard_truth() -> None:
    config, geography = _models()
    baseline = _scenario(config, geography)
    severe = _scenario(config, geography, sigma=0.6)
    assert baseline.resources == severe.resources
    assert baseline.weather != severe.weather
    assert baseline.gauges != severe.gauges
    baseline_ids = {item.incident_id for item in baseline.truth.incidents}
    severe_ids = {item.incident_id for item in severe.truth.incidents}
    assert baseline_ids & severe_ids
    assert len(severe_ids) > len(baseline_ids)


def test_nonphysical_axes_preserve_declared_causal_layers() -> None:
    config, geography = _models()
    baseline = _scenario(config, geography)
    capacity = _scenario(config, geography, kappa=1.0)
    friction = _scenario(config, geography, mu=2.0)
    information = _scenario(config, geography, iota=0.6)
    coordination = _scenario(config, geography, phi=3)
    prior = _scenario(config, geography, pi=0.5)
    degraded = _scenario(config, geography, delta=0.6)

    for variant in (capacity, friction, information, coordination, prior, degraded):
        assert baseline.weather == variant.weather
        assert baseline.gauges == variant.gauges
        assert baseline.truth == variant.truth
    assert baseline.observations == capacity.observations == friction.observations
    assert baseline.observations == coordination.observations == prior.observations
    assert baseline.observations == degraded.observations
    assert baseline.resources != capacity.resources
    assert baseline.resources != friction.resources
    assert baseline.resources != degraded.resources
    assert baseline.resources == information.resources == coordination.resources == prior.resources
    assert baseline.observations != information.observations
    assert baseline.coordination != coordination.coordination
    assert baseline.prior_profile != prior.prior_profile


def test_exposure_changes_placement_occupancy_and_vulnerability_not_physical_hazard() -> None:
    config, geography = _models()
    baseline = _scenario(config, geography)
    vulnerable = _scenario(
        config,
        geography,
        exposure_profile="isleton_high_vulnerability_v1",
    )
    assert baseline.weather == vulnerable.weather
    assert baseline.gauges == vulnerable.gauges
    assert baseline.crossing_states == vulnerable.crossing_states
    assert baseline.truth.structures != vulnerable.truth.structures
    assert baseline.truth.people != vulnerable.truth.people
    assert baseline.resources == vulnerable.resources


def test_truth_incidents_follow_the_declared_type_specific_mechanics() -> None:
    config, geography = _models()
    observed_types: set[str] = set()
    for seed in range(config.seed, config.seed + 25):
        scenario = generate_delta_small_from_models(
            config.model_copy(update={"seed": seed}),
            geography,
            SOURCE_PATH,
        )
        state_by_key = {
            (item.structure_id, item.simulation_time_s): item
            for item in scenario.truth.structure_states
        }
        levee_by_key = {
            (item.island_id, item.simulation_time_s): item for item in scenario.truth.levees
        }
        structure_by_id = {item.structure_id: item for item in scenario.truth.structures}
        person_by_id = {item.person_id: item for item in scenario.truth.people}
        for incident in scenario.truth.incidents:
            observed_types.add(incident.incident_type)
            state = state_by_key[(incident.structure_id, incident.onset_s)]
            people = [person_by_id[item] for item in incident.person_ids]
            if incident.incident_type == "C-STR":
                assert state.flood_state == "shallow_ponding"
                assert people
            elif incident.incident_type == "C-VEH":
                assert state.access_state == "impaired"
                assert all(
                    _position_at(scenario, item.person_id, incident.onset_s).state
                    == "away_from_home"
                    for item in people
                )
            elif incident.incident_type == "C-LEV":
                assert not people
                assert incident.infrastructure_id is not None
                island_id = structure_by_id[incident.structure_id].island_id
                assert levee_by_key[(island_id, incident.onset_s)].seepage_state != "none"
            elif incident.incident_type == "C-MED":
                assert people
                assert all(item.medical_dependency != "none" for item in people)
            elif incident.incident_type == "C-WEL":
                assert people
                assert all(
                    item.mobility == "limited" or item.medical_dependency != "none"
                    for item in people
                )
            elif incident.incident_type == "C-MIS":
                assert people
                assert all(
                    _position_at(scenario, item.person_id, incident.onset_s).state
                    == "away_from_home"
                    for item in people
                )
            assert set(incident.causal_factors_milli) == {
                "hazard",
                "occupancy",
                "vulnerability",
                "access",
                "candidate_probability",
            }
    assert observed_types == {"C-STR", "C-VEH", "C-LEV", "C-MED", "C-WEL", "C-MIS"}


def test_truth_is_independent_of_the_configured_observation_hourly_target() -> None:
    config, geography = _models()
    baseline = generate_delta_small_from_models(config, geography, SOURCE_PATH)
    revised_call_process = config.call_process.model_copy(
        update={
            "hourly_intensity": [5.0, 8.0, 12.0, 7.0, 5.0, 3.0],
        }
    )
    variant = generate_delta_small_from_models(
        config.model_copy(update={"call_process": revised_call_process}),
        geography,
        SOURCE_PATH,
    )
    assert baseline.truth == variant.truth
    assert baseline.observations.calls == variant.observations.calls


def test_observation_quality_mechanisms_are_monotone_and_baseline_mixture_is_frozen() -> None:
    high = channel_probabilities_v7(0.9)
    low = channel_probabilities_v7(0.6)
    assert reporting_probability_v7(0.6, 3) < reporting_probability_v7(0.9, 3)
    for key in ("duplicate", "multi_channel", "revision", "conflict", "callback_failure", "drop"):
        assert low[key] > high[key]
    high_mix = location_method_mixture_v7(0.9)
    low_mix = location_method_mixture_v7(0.6)
    assert high_mix == {
        "gps-or-address-intersection": 0.55,
        "landmark": 0.27,
        "cell-sector": 0.18,
    }
    assert low_mix["cell-sector"] > high_mix["cell-sector"]
    assert location_error_scale_v7(0.9) == 1.0
    assert location_error_scale_v7(0.3) == 3.0


def test_v7_calls_use_declared_location_ranges_and_visible_conflicts_only() -> None:
    config, geography = _models()
    scenario: GeneratedScenario | None = None
    for seed in range(config.seed, config.seed + 25):
        candidate = generate_delta_small_from_models(
            config.model_copy(update={"seed": seed}),
            geography,
            SOURCE_PATH,
        )
        if any(
            item.relationship == "conflicting_report" for item in candidate.observations.lineage
        ):
            scenario = candidate
            break
    assert scenario is not None
    for call in scenario.observations.calls:
        lower, upper = BASE_PRECISION_RANGES_M[call.location.method]
        assert lower <= call.location.precision_m <= upper
    lineage_by_incident: dict[str, list[str]] = defaultdict(list)
    for item in scenario.observations.lineage:
        if item.truth_incident_id is not None:
            lineage_by_incident[item.truth_incident_id].append(item.call_id)
    calls = {item.call_id: item for item in scenario.observations.calls}
    conflicts = [
        item for item in scenario.observations.lineage if item.relationship == "conflicting_report"
    ]
    assert conflicts
    for conflict in conflicts:
        peers = [calls[item] for item in lineage_by_incident[conflict.truth_incident_id or ""]]
        visible = calls[conflict.call_id]
        assert any(
            (
                visible.reported.call_type,
                visible.reported.occupants,
                visible.reported.medical,
                visible.location.easting_mm,
                visible.location.northing_mm,
            )
            != (
                peer.reported.call_type,
                peer.reported.occupants,
                peer.reported.medical,
                peer.location.easting_mm,
                peer.location.northing_mm,
            )
            for peer in peers
            if peer.call_id != visible.call_id
        )
    public = canonical_json_bytes(
        [item.model_dump(mode="json") for item in scenario.observations.calls]
    )
    assert b"truth_incident" not in public
    assert b"truth_person" not in public
    assert b"conflicting_report" not in public


def test_phi_changes_only_delivery_and_controller_behavior_without_task3_events() -> None:
    config, geography = _models()
    baseline = _scenario(config, geography)
    fragmented = _scenario(config, geography, phi=3)
    assert baseline.truth == fragmented.truth
    assert baseline.observations == fragmented.observations
    assert baseline.resources == fragmented.resources
    assert baseline.coordination is not None
    assert fragmented.coordination is not None
    assert all(item.sharing_latency_s == 0 for item in baseline.coordination.deliveries)
    assert any(item.sharing_latency_s > 0 for item in fragmented.coordination.deliveries)
    result = run_delta_small(fragmented, ToyActionPrefixPredictor(), POLICY)
    received_by_call = {item.call_id: item.received_s for item in fragmented.observations.calls}
    assert all(
        event.simulation_time_s >= received_by_call[event.call_id] for event in result.decisions
    )
    assert any(item.observation_age_s > 0 for item in result.evidence)
    serialized = canonical_json_bytes(
        {
            "coordination": fragmented.coordination.model_dump(mode="json"),
            "decisions": [item.model_dump(mode="json") for item in result.decisions],
        }
    ).lower()
    for forbidden in (b"mutual-aid", b"authority-transfer", b"negotiation", b"federation"):
        assert forbidden not in serialized
