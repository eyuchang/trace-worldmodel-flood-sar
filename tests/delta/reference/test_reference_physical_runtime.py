from __future__ import annotations

import json
from pathlib import Path

import pytest

from trace_reference import load_reference_gauge_context, load_reference_physical_parameters
from trace_reference.domain.events import ReferenceEventType, ReferenceEventVisibility
from trace_reference.generation import generate_reference_physical_scenario
from trace_reference.runtime import ReferenceEventLog

ROOT = Path(__file__).resolve().parents[3]
PARAMETERS = Path("data/scenario/delta/reference/physical/reference_physical_parameters_v1.yaml")


@pytest.fixture(scope="module")
def physical():
    parameters = load_reference_physical_parameters(ROOT, PARAMETERS)
    return parameters, generate_reference_physical_scenario(parameters)


def test_reference_physical_timeline_is_complete_and_deterministic(physical) -> None:
    parameters, scenario = physical
    regenerated = generate_reference_physical_scenario(parameters)

    assert len(scenario.samples) == 1_729
    assert scenario.samples[0].at_s == -172_800
    assert scenario.samples[-1].at_s == 345_600
    assert scenario.model_dump_json() == regenerated.model_dump_json()
    assert scenario.physical_digest == regenerated.physical_digest


def test_evaluation_rainfall_reconciles_disclosed_global_target(physical) -> None:
    parameters, scenario = physical
    evaluation_samples = [item for item in scenario.samples if 0 <= item.at_s < 345_600]
    integrated_milli_in = sum(
        item.weather.effective_rain_milli_in_per_hour * parameters.output_tick_s / 3_600
        for item in evaluation_samples
    )
    assert integrated_milli_in == pytest.approx(9_800, abs=10)
    assert any(
        item.weather.nominal_rain_milli_in_per_hour != item.weather.effective_rain_milli_in_per_hour
        for item in evaluation_samples
    )


def test_gauge_components_are_exposed_and_thresholds_nonoperative(physical) -> None:
    _, scenario = physical
    for sample in scenario.samples[::149]:
        for gauge in sample.gauges:
            assert gauge.stage_milli_ft == sum(
                (
                    gauge.baseline_milli_ft,
                    gauge.tide_milli_ft,
                    gauge.runoff_milli_ft,
                    gauge.wind_setup_milli_ft,
                    gauge.upstream_release_milli_ft,
                )
            )
            assert gauge.threshold_status == "unavailable-non-operative"
    identities = {item.gauge_id: item.official_name for item in physical[0].gauges}
    assert identities["MRU"] == "Middle River at Undine Road"
    assert identities["MSD"] == "San Joaquin River at Mossdale Bridge"


def test_scripted_breach_widens_reverses_and_changes_access(physical) -> None:
    parameters, scenario = physical
    by_time = {item.at_s: item for item in scenario.samples}
    breach = parameters.breach

    assert by_time[breach.activation_s - 300].breach.active is False
    assert by_time[breach.activation_s].breach.width_milli_ft == 60_000
    assert by_time[breach.activation_s].breach.net_inflow_cfs != 0
    assert (
        by_time[breach.activation_s + breach.widening_duration_s].breach.width_milli_ft == 210_000
    )
    active = [item.breach for item in scenario.samples if item.breach.active]
    assert min(item.net_inflow_cfs for item in active) < 0
    assert max(item.net_inflow_cfs for item in active) > 0
    assert max(item.stored_milli_acre_ft for item in active) <= (
        breach.storage_capacity_acre_ft * 1_000
    )
    before = by_time[190_500].crossings[3]
    after = by_time[190_800].crossings[3]
    assert (before.status, after.status) == ("open", "closed")
    assert all(item.crossings[9].status == "unavailable-unresolved" for item in scenario.samples)


def test_event_visibility_excludes_hidden_breach_from_public_samples(physical) -> None:
    _, scenario = physical
    public = [
        event
        for event in scenario.events
        if event.event_type == ReferenceEventType.PUBLIC_ENVIRONMENT_SAMPLE
    ]
    hidden = [
        event
        for event in scenario.events
        if event.event_type == ReferenceEventType.HIDDEN_PHYSICAL_TRUTH
    ]
    assert len(public) == len(hidden) == 1_729
    assert all(event.visibility == ReferenceEventVisibility.CONTROLLER_VISIBLE for event in public)
    assert all(
        event.visibility == ReferenceEventVisibility.HIDDEN_EVALUATION_ONLY for event in hidden
    )
    assert all("breach" not in json.loads(event.payload_json) for event in public)
    assert all("breach" in json.loads(event.payload_json) for event in hidden)


def test_event_chain_checkpoint_and_restart_match_full_replay(physical) -> None:
    _, scenario = physical
    log = ReferenceEventLog(scenario.events)
    assert log.verify()
    boundary = len(scenario.events) // 2
    checkpoint = log.checkpoint(through_sequence=boundary)
    resumed = log.resume(checkpoint)
    for event in scenario.events[boundary:]:
        resumed.apply(event)
    assert resumed.canonical_value() == log.replay().canonical_value()

    tampered = scenario.events[100].model_copy(update={"payload_json": '{"tampered":true}'})
    events = list(scenario.events)
    events[100] = tampered
    with pytest.raises(ValueError, match="digest is invalid"):
        ReferenceEventLog(events)


def test_sigma_changes_hazard_without_changing_timeline_or_entity_coverage(physical) -> None:
    parameters, baseline = physical
    severe = generate_reference_physical_scenario(parameters, sigma=1.2)
    assert tuple(item.at_s for item in severe.samples) == tuple(
        item.at_s for item in baseline.samples
    )
    assert tuple(item.gauge_id for item in severe.samples[0].gauges) == tuple(
        item.gauge_id for item in baseline.samples[0].gauges
    )
    assert max(item.weather.effective_rain_milli_in_per_hour for item in severe.samples) > max(
        item.weather.effective_rain_milli_in_per_hour for item in baseline.samples
    )


def test_physical_parameter_loader_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "parameters.yaml"
    target.write_bytes((ROOT / PARAMETERS).read_bytes())
    alias = tmp_path / "alias.yaml"
    alias.symlink_to(target)
    with pytest.raises(ValueError, match="must not be a symlink"):
        load_reference_physical_parameters(tmp_path, Path("alias.yaml"))


def test_gauge_context_is_exact_official_identity_transcription() -> None:
    registry = load_reference_gauge_context(
        ROOT,
        Path("data/scenario/delta/reference/physical/reference_gauge_context_v1.yaml"),
    )
    assert tuple(item.gauge_id for item in registry.gauges) == (
        "FPT",
        "RVB",
        "SJJ",
        "ANH",
        "MRU",
        "OLD",
        "MSD",
    )
    assert next(item for item in registry.gauges if item.gauge_id == "MRU").official_name == (
        "Middle River at Undine Road"
    )
    assert next(item for item in registry.gauges if item.gauge_id == "MSD").official_name == (
        "San Joaquin River at Mossdale Bridge"
    )
    assert all(item.threshold_status == "unavailable-non-operative" for item in registry.gauges)
