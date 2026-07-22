"""Contract tests for experimental-profile predictor-version provenance."""

from datetime import datetime, timezone

from pydantic import ValidationError

from trace_jepa.contracts import WorldModelEvidence
from trace_jepa.experimental import (
    AdequacyStatus,
    ExperimentalProfileExtension,
    build_experimental_profile,
)


def _base_evidence(**updates) -> WorldModelEvidence:
    base = dict(
        encoder_version="encoder-v1",
        fusion_version="fusion-v1",
        predictor_version="predictor-v1",
        semantic_probe_versions=("probe-v1",),
        training_snapshot="data-v1",
        observation_window_hash="obs",
        fleet_state_hash="state",
        candidate_plan_id="plan",
        action_schema_version="actions-v1",
        rollout_horizon=3,
        predicted_claims=("route open",),
        uncertainty=0.1,
        model_support=0.9,
        out_of_distribution_score=0.1,
        rollout_consistency=0.9,
        calibration_version="cal-v1",
    )
    base.update(updates)
    return WorldModelEvidence(**base)


def test_experimental_profile_carries_required_provenance_fields():
    stamp = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    profile = build_experimental_profile(
        predictor_version="predictor-v2",
        calibration_version="cal-v2",
        claim_family="high_consequence_rescue",
        adequacy_status=AdequacyStatus.UNQUALIFIED,
        prediction_timestamp=stamp,
        model_hash="abc123",
    )
    assert profile.predictor_version == "predictor-v2"
    assert profile.calibration_version == "cal-v2"
    assert profile.prediction_timestamp == stamp
    assert profile.claim_family == "high_consequence_rescue"
    assert profile.adequacy_status == AdequacyStatus.UNQUALIFIED
    assert profile.model_hash == "abc123"


def test_world_model_evidence_accepts_experimental_profile_extension():
    profile = ExperimentalProfileExtension(
        predictor_version="predictor-v1",
        calibration_version="cal-v1",
        claim_family="route_access",
        adequacy_status=AdequacyStatus.QUALIFIED,
    )
    evidence = _base_evidence(experimental_profile=profile)
    assert evidence.experimental_profile is not None
    assert evidence.experimental_profile.claim_family == "route_access"
    assert evidence.experimental_profile.adequacy_status == AdequacyStatus.QUALIFIED


def test_world_model_evidence_coerces_profile_mapping():
    evidence = _base_evidence(
        experimental_profile={
            "predictor_version": "predictor-v1",
            "calibration_version": "cal-v1",
            "claim_family": "dispatch_success",
            "adequacy_status": "pending_revalidation",
        }
    )
    assert evidence.experimental_profile.adequacy_status == (
        AdequacyStatus.PENDING_REVALIDATION
    )


def test_baseline_evidence_without_profile_still_validates():
    evidence = _base_evidence()
    assert evidence.experimental_profile is None


def test_experimental_profile_rejects_unknown_fields():
    try:
        ExperimentalProfileExtension(
            predictor_version="p",
            calibration_version="c",
            claim_family="f",
            adequacy_status=AdequacyStatus.QUALIFIED,
            unexpected=True,
        )
        raised = False
    except ValidationError:
        raised = True
    assert raised
