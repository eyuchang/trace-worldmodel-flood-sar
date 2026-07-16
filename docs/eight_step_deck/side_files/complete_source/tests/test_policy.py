from pathlib import Path

from trace_jepa.contracts import Claim, ClaimLayer, CommitmentDecision, WorldModelEvidence
from trace_jepa.runtime.policy import PolicyConfig, PolicyEngine


def evidence(**updates) -> WorldModelEvidence:
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


def test_policy_is_deterministic_and_holds_out_of_support_action():
    config = PolicyConfig.from_yaml(Path("configs/policies/trace_v1.yaml"))
    engine = PolicyEngine(config)
    claim = Claim(layer=ClaimLayer.PREDICTIVE, text="The northern route is open.")
    item = evidence(model_support=0.2, out_of_distribution_score=0.8)
    first = engine.evaluate(
        claim,
        item,
        action_name="dispatch_rescue_boat",
        reversible=False,
        authority_present=True,
    )
    second = engine.evaluate(
        claim,
        item,
        action_name="dispatch_rescue_boat",
        reversible=False,
        authority_present=True,
    )
    assert first == second
    assert first.decision == CommitmentDecision.HOLD
    assert "model_support" in first.failed_gates
    assert "out_of_distribution" in first.failed_gates
