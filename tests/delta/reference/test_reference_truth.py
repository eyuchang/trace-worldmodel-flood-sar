from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from trace_reference import (
    load_reference_exposure_parameters,
    load_reference_physical_parameters,
)
from trace_reference.domain.truth import ReferenceIncidentType
from trace_reference.generation import (
    build_reference_truth_fit_seed_summary,
    generate_reference_exposure,
    generate_reference_physical_scenario,
    generate_reference_truth,
)
from trace_reference.geography import load_reference_geography

ROOT = Path(__file__).resolve().parents[3]
GEOGRAPHY_ROOT = ROOT / "data/scenario/delta/reference/geography"
PHYSICAL_PARAMETERS = Path(
    "data/scenario/delta/reference/physical/reference_physical_parameters_v1.yaml"
)
EXPOSURE_PARAMETERS = Path(
    "data/scenario/delta/reference/exposure/reference_exposure_parameters_v1.yaml"
)


@pytest.fixture(scope="module")
def truth_fixture():
    physical_parameters = load_reference_physical_parameters(ROOT, PHYSICAL_PARAMETERS)
    exposure_parameters = load_reference_exposure_parameters(ROOT, EXPOSURE_PARAMETERS)
    geography = load_reference_geography(geography_root=GEOGRAPHY_ROOT)
    physical = generate_reference_physical_scenario(physical_parameters)
    exposure = generate_reference_exposure(exposure_parameters, geography, seed=20260812)
    return physical, exposure, generate_reference_truth(physical, exposure, seed=20260812)


def test_reference_truth_is_deterministic_causal_and_nonempty(truth_fixture) -> None:
    physical, exposure, truth = truth_fixture
    regenerated = generate_reference_truth(physical, exposure, seed=20260812)
    assert truth.model_dump_json() == regenerated.model_dump_json()
    assert truth.truth_digest == regenerated.truth_digest
    assert truth.incidents
    assert 0 < len(truth.candidate_audit) < 420 * 9 * 10
    accepted = [item for item in truth.candidate_audit if item.accepted_truth_incident_id]
    assert len(accepted) == len(truth.incidents)
    assert all(item.attempt_count >= 1 for item in truth.candidate_audit)


def test_incident_episodes_do_not_repeat_while_eligibility_persists(truth_fixture) -> None:
    _, _, truth = truth_fixture
    by_key = Counter(item.episode_key for item in truth.incidents)
    assert max(by_key.values(), default=0) == 1
    assert any(item.suppressed_eligible_ticks > 0 for item in truth.candidate_audit)
    assert all(
        item.suppression_reason is not None
        for item in truth.candidate_audit
        if item.suppressed_eligible_ticks
    )


def test_person_and_infrastructure_incident_subject_semantics(truth_fixture) -> None:
    _, _, truth = truth_fixture
    for incident in truth.incidents:
        if incident.incident_type == ReferenceIncidentType.LEVEE_INSPECTION:
            assert incident.infrastructure_id == "SIM-RD407-WEST-01"
        if incident.incident_type in {
            ReferenceIncidentType.STRANDED_STRUCTURE,
            ReferenceIncidentType.VEHICLE_RESCUE,
            ReferenceIncidentType.MEDICAL_ACCESS,
            ReferenceIncidentType.WELFARE_CHECK,
            ReferenceIncidentType.MISSING_PERSON,
        }:
            assert incident.affected_truth_person_ids


def test_truth_changes_with_hazard_but_not_observation_quality(truth_fixture) -> None:
    _, exposure, baseline = truth_fixture
    parameters = load_reference_physical_parameters(ROOT, PHYSICAL_PARAMETERS)
    severe_physical = generate_reference_physical_scenario(parameters, sigma=1.2)
    severe = generate_reference_truth(severe_physical, exposure, seed=20260812)
    assert severe.truth_digest != baseline.truth_digest
    assert tuple(item.truth_incident_id for item in severe.incidents) != tuple(
        item.truth_incident_id for item in baseline.incidents
    )


def test_truth_artifact_contains_no_call_volume_target(truth_fixture) -> None:
    _, _, truth = truth_fixture
    serialized = truth.model_dump_json()
    assert "expected_public_reports" not in serialized
    assert "call_volume_target" not in serialized


def test_fit_intervals_exactly_reproduce_evaluation_counts(truth_fixture) -> None:
    physical, exposure, truth = truth_fixture
    summary = build_reference_truth_fit_seed_summary(physical, exposure, seed=20260812)
    intercepts = {
        ReferenceIncidentType.STRANDED_STRUCTURE: 4_200,
        ReferenceIncidentType.VEHICLE_RESCUE: 1_700,
        ReferenceIncidentType.LEVEE_INSPECTION: 2_100,
        ReferenceIncidentType.MEDICAL_ACCESS: 2_500,
        ReferenceIncidentType.WELFARE_CHECK: 2_500,
        ReferenceIncidentType.MISSING_PERSON: 1_400,
        ReferenceIncidentType.ANIMAL_RESCUE: 1_100,
        ReferenceIncidentType.INFORMATION_NEED: 1_500,
        ReferenceIncidentType.HAZARD_RESPONSE: 1_200,
    }
    expected = Counter(
        item.incident_type for item in truth.incidents if 0 <= item.onset_s < 345_600
    )
    actual = Counter(
        interval.incident_type
        for interval in summary.evaluation_intervals
        if interval.lower_intercept_inclusive <= intercepts[interval.incident_type]
        and (
            interval.upper_intercept_exclusive is None
            or intercepts[interval.incident_type] < interval.upper_intercept_exclusive
        )
    )

    assert actual == expected
    assert summary.eligible_episode_count == len(truth.candidate_audit)
