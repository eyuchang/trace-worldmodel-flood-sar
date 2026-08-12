from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from trace_reference import (
    load_reference_exposure_parameters,
    load_reference_physical_parameters,
)
from trace_reference.generation import (
    generate_reference_exposure,
    generate_reference_observations,
    generate_reference_physical_scenario,
    generate_reference_truth,
    verify_reference_envelope,
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
def observation_inputs():
    physical_parameters = load_reference_physical_parameters(ROOT, PHYSICAL_PARAMETERS)
    exposure_parameters = load_reference_exposure_parameters(ROOT, EXPOSURE_PARAMETERS)
    geography = load_reference_geography(geography_root=GEOGRAPHY_ROOT)
    physical = generate_reference_physical_scenario(physical_parameters)
    exposure = generate_reference_exposure(exposure_parameters, geography, seed=20260812)
    truth = generate_reference_truth(physical, exposure, seed=20260812)
    return exposure, truth


@pytest.fixture(scope="module")
def observations(observation_inputs):
    exposure, truth = observation_inputs
    return generate_reference_observations(truth, exposure, seed=20260812)


def test_reference_observations_are_deterministic_and_separately_hashed(
    observation_inputs, observations
) -> None:
    exposure, truth = observation_inputs
    regenerated = generate_reference_observations(truth, exposure, seed=20260812)
    assert observations.model_dump_json() == regenerated.model_dump_json()
    assert (
        len(
            {
                observations.raw.raw_reports_digest,
                observations.delivery.delivery_envelopes_digest,
                observations.hidden.hidden_digest,
            }
        )
        == 3
    )


def test_raw_and_delivery_artifacts_do_not_leak_hidden_truth(observations) -> None:
    public_json = observations.raw.model_dump_json() + observations.delivery.model_dump_json()
    for forbidden in (
        "truth_incident",
        "truth_person",
        "hidden_lineage",
        '"relationship"',
        "episode_key",
    ):
        assert forbidden not in public_json
    assert all(len(report.descriptor_tokens) == 1 for report in observations.raw.reports)
    assert len(
        {token for report in observations.raw.reports for token in report.descriptor_tokens}
    ) < len(observations.raw.reports)


def test_zero_one_many_channel_and_visible_disagreements_are_realized(
    observation_inputs, observations
) -> None:
    _, truth = observation_inputs
    relationships = Counter(item.relationship for item in observations.hidden.entries)
    assert relationships["initial"] > 0
    assert relationships["duplicate"] > 0
    assert relationships["multi-channel"] > 0
    assert relationships["conflict"] > 0
    assert relationships["revision"] > 0
    assert relationships["third-party-welfare"] > 0
    assert relationships["false-benign-levee"] > 0
    reported_truth_ids = {
        item.truth_incident_id
        for item in observations.hidden.entries
        if item.truth_incident_id is not None
    }
    assert len(reported_truth_ids) < len(truth.incidents)
    reports_per_truth = Counter(
        item.truth_incident_id
        for item in observations.hidden.entries
        if item.truth_incident_id is not None
    )
    assert any(total == 1 for total in reports_per_truth.values())
    assert any(total > 1 for total in reports_per_truth.values())


def test_envelopes_bind_exact_raw_content_and_revision_targets(observations) -> None:
    report_by_id = {item.call_id: item for item in observations.raw.reports}
    assert all(
        verify_reference_envelope(report_by_id[envelope.call_id], envelope)
        for envelope in observations.delivery.envelopes
    )
    revisions = [item for item in observations.raw.reports if item.revision_of_call_id]
    assert revisions
    assert all(item.revision_of_call_id in report_by_id for item in revisions)
    assert all(
        item.observed_at_s >= report_by_id[item.revision_of_call_id].observed_at_s
        for item in revisions
    )
    first_envelope = observations.delivery.envelopes[0]
    tampered_report = report_by_id[first_envelope.call_id].model_copy(
        update={"descriptor_tokens": ("tampered-visible-content",)}
    )
    assert not verify_reference_envelope(tampered_report, first_envelope)

    false_ids = {
        item.call_id
        for item in observations.hidden.entries
        if item.relationship == "false-benign-levee"
    }
    assert false_ids
    assert all(
        verify_reference_envelope(report_by_id[envelope.call_id], envelope)
        for envelope in observations.delivery.envelopes
        if envelope.call_id in false_ids
    )


def test_iota_uses_common_random_numbers_and_monotone_mechanism_thresholds(
    observation_inputs,
) -> None:
    exposure, truth = observation_inputs
    low = generate_reference_observations(truth, exposure, seed=20260812, iota=0.3)
    high = generate_reference_observations(truth, exposure, seed=20260812, iota=1.0)
    low_lineage = {item.call_id: item for item in low.hidden.entries}
    high_lineage = {item.call_id: item for item in high.hidden.entries}
    low_initial_truth = {
        item.truth_incident_id for item in low.hidden.entries if item.relationship == "initial"
    }
    high_initial_truth = {
        item.truth_incident_id for item in high.hidden.entries if item.relationship == "initial"
    }
    assert low_initial_truth <= high_initial_truth
    common_initial_truth = low_initial_truth & high_initial_truth
    assert {
        item.call_id
        for item in high.hidden.entries
        if item.truth_incident_id in common_initial_truth
        and item.relationship in {"duplicate", "multi-channel", "conflict"}
    } <= {
        item.call_id
        for item in low.hidden.entries
        if item.truth_incident_id in common_initial_truth
        and item.relationship in {"duplicate", "multi-channel", "conflict"}
    }
    common = set(low_lineage) & set(high_lineage)
    low_reports = {item.call_id: item for item in low.raw.reports}
    high_reports = {item.call_id: item for item in high.raw.reports}
    assert {call_id for call_id in common if high_reports[call_id].callback_failed} <= {
        call_id for call_id in common if low_reports[call_id].callback_failed
    }
    assert {call_id for call_id in common if high_reports[call_id].call_dropped} <= {
        call_id for call_id in common if low_reports[call_id].call_dropped
    }


def test_reference_observations_use_only_synthetic_contact_tokens(observations) -> None:
    tokens = [item.callback_token for item in observations.raw.reports if item.callback_token]
    assert tokens
    assert all(token.startswith("SYN-CB-") for token in tokens)
    assert all("+1" not in token and "@" not in token for token in tokens)
