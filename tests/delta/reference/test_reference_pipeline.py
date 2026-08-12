from __future__ import annotations

from pathlib import Path

from trace_reference.generation import generate_reference_scenario

ROOT = Path(__file__).resolve().parents[3]


def test_reference_pipeline_executes_approved_causal_order_offline() -> None:
    scenario = generate_reference_scenario(ROOT, seed=20260812)
    assert scenario.config.generation_order == (
        "geography",
        "meteorology",
        "hydrology_breach_access",
        "exposure_truth_incidents",
        "public_observations",
        "resources_and_telemetry",
        "coordination_delivery",
        "predictor_prior",
        "fault_overlay",
        "trace_execution_recovery",
        "offline_evaluation",
    )
    assert len(scenario.geography.islands) == 8
    assert len(scenario.exposure.people) == 1_400
    assert scenario.truth.scientific_status == (
        "frozen-spent-development-fit-not-validation-evidence"
    )
    assert scenario.truth.coefficient_digest == (
        "63fa9591c17a1208cfa45c46a76997785aa9a9a15e00a074a1e62fe22540b25a"
    )
    assert scenario.observations.raw.scientific_status == (
        "frozen-spent-development-fit-not-validation-evidence"
    )
    assert scenario.observations.raw.coefficient_version.endswith("v2")
    assert sum(item.observed_at_s >= 0 for item in scenario.observations.raw.reports) > 2_000
    assert scenario.prior.prior_accuracy_milli == 700


def test_reference_pipeline_is_byte_deterministic_for_development_seed() -> None:
    first = generate_reference_scenario(ROOT, seed=20260812)
    second = generate_reference_scenario(ROOT, seed=20260812)
    assert first.physical.physical_digest == second.physical.physical_digest
    assert first.exposure.exposure_digest == second.exposure.exposure_digest
    assert first.truth.truth_digest == second.truth.truth_digest
    assert first.observations.raw.raw_reports_digest == second.observations.raw.raw_reports_digest
    assert first.resources.hidden.hidden_resource_digest == (
        second.resources.hidden.hidden_resource_digest
    )
    assert first.coordination.public.public_coordination_digest == (
        second.coordination.public.public_coordination_digest
    )
