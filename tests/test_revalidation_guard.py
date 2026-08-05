"""Contract tests for the Section 5.5 revalidation guard."""

from pathlib import Path

import pytest

from trace_jepa.contracts import Claim, ClaimLayer, CommitmentDecision, WorldModelEvidence
from trace_jepa.experimental import (
    AdequacyStatus,
    RevalidationGuard,
    build_experimental_profile,
)
from trace_jepa.runtime.policy import PolicyConfig, PolicyEngine

FAMILY = "high_consequence_rescue"


def evidence_with_profile(
    *,
    predictor_version: str,
    calibration_version: str,
    adequacy_status: AdequacyStatus,
    model_hash: str | None = None,
    **updates,
) -> WorldModelEvidence:
    profile = build_experimental_profile(
        predictor_version=predictor_version,
        calibration_version=calibration_version,
        claim_family=FAMILY,
        adequacy_status=adequacy_status,
        model_hash=model_hash,
    )
    base = {
        "encoder_version": "encoder-v1",
        "fusion_version": "fusion-v1",
        "predictor_version": predictor_version,
        "semantic_probe_versions": ("probe-v1",),
        "training_snapshot": "data-v1",
        "observation_window_hash": "obs",
        "fleet_state_hash": "state",
        "candidate_plan_id": "plan",
        "action_schema_version": "actions-v1",
        "rollout_horizon": 3,
        "predicted_claims": ("route open",),
        "uncertainty": 0.1,
        "model_support": 0.9,
        "out_of_distribution_score": 0.1,
        "rollout_consistency": 0.9,
        "calibration_version": calibration_version,
        "experimental_profile": profile,
    }
    base.update(updates)
    return WorldModelEvidence(**base)


def guarded_engine() -> tuple[PolicyEngine, RevalidationGuard]:
    config = PolicyConfig.from_yaml(Path("configs/policies/trace_rq5_guard_v1.yaml"))
    guard = RevalidationGuard.bootstrap(
        predictor_version="predictor-v1",
        calibration_version="cal-v1",
        model_hash="hash-v1",
        qualified_families=(FAMILY,),
    )
    return PolicyEngine(config, revalidation=guard), guard


def test_guard_clears_when_version_current_and_calibration_adequate():
    engine, guard = guarded_engine()
    claim = Claim(layer=ClaimLayer.PREDICTIVE, text="South route is open.")
    item = evidence_with_profile(
        predictor_version="predictor-v1",
        calibration_version="cal-v1",
        adequacy_status=AdequacyStatus.QUALIFIED,
        model_hash="hash-v1",
    )
    result = engine.evaluate(
        claim,
        item,
        action_name="dispatch_rescue_boat",
        reversible=False,
        authority_present=True,
    )
    assert result.decision == CommitmentDecision.CLEAR
    assert "model_version_current" not in result.failed_gates
    assert "calibration_adequate_for_class" not in result.failed_gates
    assert guard.transition_log[-1] == {
        "event_type": "gate_revalidation_check",
        "action_name": "dispatch_rescue_boat",
        "predictor_version": "predictor-v1",
        "claim_family": FAMILY,
        "adequacy_status": "qualified",
        "model_version_current": True,
        "calibration_adequate_for_class": True,
        "blocked": False,
    }


def test_guard_holds_high_consequence_on_unqualified_successor():
    engine, guard = guarded_engine()
    event = guard.replace_predictor(
        new_predictor_version="predictor-v2",
        new_calibration_version="cal-v2",
        new_model_hash="hash-v2",
        simulation_time_s=120.0,
        initially_unqualified_families=(FAMILY,),
    )
    assert event.old_model_hash == "hash-v1"
    assert event.new_model_hash == "hash-v2"
    assert event.new_adequacy_status == AdequacyStatus.UNQUALIFIED

    claim = Claim(layer=ClaimLayer.PREDICTIVE, text="South route is open.")
    item = evidence_with_profile(
        predictor_version="predictor-v2",
        calibration_version="cal-v2",
        adequacy_status=AdequacyStatus.UNQUALIFIED,
        model_hash="hash-v2",
    )
    result = engine.evaluate(
        claim,
        item,
        action_name="dispatch_rescue_boat",
        reversible=False,
        authority_present=True,
    )
    assert result.decision == CommitmentDecision.HOLD
    assert "calibration_adequate_for_class" in result.failed_gates


def test_guard_holds_on_superseded_predictor_version():
    engine, guard = guarded_engine()
    guard.replace_predictor(
        new_predictor_version="predictor-v2",
        new_calibration_version="cal-v2",
        new_model_hash="hash-v2",
        simulation_time_s=50.0,
        initially_unqualified_families=(FAMILY,),
    )
    claim = Claim(layer=ClaimLayer.PREDICTIVE, text="Stale prediction.")
    # Evidence still cites the superseded version.
    item = evidence_with_profile(
        predictor_version="predictor-v1",
        calibration_version="cal-v1",
        adequacy_status=AdequacyStatus.SUPERSEDED,
        model_hash="hash-v1",
    )
    result = engine.evaluate(
        claim,
        item,
        action_name="dispatch_rescue_boat",
        reversible=False,
        authority_present=True,
    )
    assert result.decision == CommitmentDecision.HOLD
    assert "model_version_current" in result.failed_gates


def test_unguarded_arm_may_clear_unqualified_successor():
    config = PolicyConfig.from_yaml(Path("configs/policies/trace_v1.yaml"))
    assert config.enable_revalidation_guard is False
    engine = PolicyEngine(config)
    claim = Claim(layer=ClaimLayer.PREDICTIVE, text="South route is open.")
    item = evidence_with_profile(
        predictor_version="predictor-v2",
        calibration_version="cal-v2",
        adequacy_status=AdequacyStatus.UNQUALIFIED,
        model_hash="hash-v2",
    )
    result = engine.evaluate(
        claim,
        item,
        action_name="dispatch_rescue_boat",
        reversible=False,
        authority_present=True,
    )
    assert result.decision == CommitmentDecision.CLEAR


def test_after_qualification_high_consequence_may_clear():
    engine, guard = guarded_engine()
    guard.replace_predictor(
        new_predictor_version="predictor-v2",
        new_calibration_version="cal-v2",
        new_model_hash="hash-v2",
        simulation_time_s=10.0,
        initially_unqualified_families=(FAMILY,),
    )
    guard.qualify_calibration(claim_family=FAMILY, simulation_time_s=40.0)
    assert guard.time_to_restored_ordinary_operation() == 30.0

    claim = Claim(layer=ClaimLayer.PREDICTIVE, text="South route is open.")
    item = evidence_with_profile(
        predictor_version="predictor-v2",
        calibration_version="cal-v2",
        adequacy_status=AdequacyStatus.QUALIFIED,
        model_hash="hash-v2",
    )
    result = engine.evaluate(
        claim,
        item,
        action_name="dispatch_rescue_boat",
        reversible=False,
        authority_present=True,
    )
    assert result.decision == CommitmentDecision.CLEAR


def test_rq5_invariant_no_clear_on_bad_version_under_guard():
    engine, guard = guarded_engine()
    guard.replace_predictor(
        new_predictor_version="predictor-v2",
        new_calibration_version="cal-v2",
        new_model_hash="hash-v2",
        simulation_time_s=5.0,
        initially_unqualified_families=(FAMILY,),
    )
    claim = Claim(layer=ClaimLayer.PREDICTIVE, text="South route is open.")
    bad_cases = [
        evidence_with_profile(
            predictor_version="predictor-v1",
            calibration_version="cal-v1",
            adequacy_status=AdequacyStatus.SUPERSEDED,
            model_hash="hash-v1",
        ),
        evidence_with_profile(
            predictor_version="predictor-v2",
            calibration_version="cal-v2",
            adequacy_status=AdequacyStatus.UNQUALIFIED,
            model_hash="hash-v2",
        ),
    ]
    for item in bad_cases:
        result = engine.evaluate(
            claim,
            item,
            action_name="dispatch_rescue_boat",
            reversible=False,
            authority_present=True,
        )
        assert result.decision != CommitmentDecision.CLEAR
        assert result.decision == CommitmentDecision.HOLD


@pytest.mark.parametrize(
    ("predictor_version", "calibration_version", "model_hash", "status"),
    [
        ("predictor-unregistered", "cal-v1", "hash-v1", AdequacyStatus.QUALIFIED),
        ("predictor-v1", "cal-unregistered", "hash-v1", AdequacyStatus.QUALIFIED),
        ("predictor-v1", "cal-v1", "hash-mismatch", AdequacyStatus.QUALIFIED),
        ("predictor-v1", "cal-v1", "hash-v1", AdequacyStatus.PENDING_REVALIDATION),
    ],
)
def test_guard_holds_unregistered_mismatched_or_pending_evidence(
    predictor_version: str,
    calibration_version: str,
    model_hash: str,
    status: AdequacyStatus,
) -> None:
    engine, _guard = guarded_engine()
    claim = Claim(layer=ClaimLayer.PREDICTIVE, text="Versioned route evidence.")
    item = evidence_with_profile(
        predictor_version=predictor_version,
        calibration_version=calibration_version,
        adequacy_status=status,
        model_hash=model_hash,
    )
    result = engine.evaluate(
        claim,
        item,
        action_name="dispatch_rescue_boat",
        reversible=False,
        authority_present=True,
    )
    assert result.decision == CommitmentDecision.HOLD
