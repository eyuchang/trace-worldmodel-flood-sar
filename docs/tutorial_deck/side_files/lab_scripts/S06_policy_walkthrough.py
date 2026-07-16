from __future__ import annotations

from trace_jepa.contracts import Claim, ClaimLayer, WorldModelEvidence
from trace_jepa.runtime import PolicyConfig, PolicyEngine


def make_evidence(*, model_support: float, ood_score: float, uncertainty: float = 0.08) -> WorldModelEvidence:
    return WorldModelEvidence(
        evidence_id=f"policy-demo-support-{model_support:.2f}-ood-{ood_score:.2f}",
        rollout_id="policy-demo-rollout",
        encoder_version="mock-encoder-v1",
        fusion_version="flood-fusion-v1",
        predictor_version="toy-predictor-v1",
        semantic_probe_versions=("route-open-probe-v1",),
        training_snapshot="synthetic-flood-training-v1",
        observation_window_hash="obs-hash-policy-demo",
        fleet_state_hash="state-hash-policy-demo",
        candidate_plan_id="north-direct",
        action_schema_version="flood-actions-v1",
        rollout_horizon=3,
        predicted_claims=("The North Channel is open for rescue-boat dispatch.",),
        uncertainty=uncertainty,
        model_support=model_support,
        out_of_distribution_score=ood_score,
        rollout_consistency=0.91,
        calibration_version="route-calibration-v1",
        assumptions=("The route map is current.",),
        observation_age_s=15.0,
    )


def show_case(
    name: str,
    *,
    engine: PolicyEngine,
    claim: Claim,
    evidence: WorldModelEvidence,
    action_name: str,
    reversible: bool,
    authority_present: bool,
) -> None:
    result = engine.evaluate(
        claim,
        evidence,
        action_name=action_name,
        reversible=reversible,
        authority_present=authority_present,
    )

    print(f"\n{name}")
    print("-" * len(name))
    print(f"Claim confidence:  {claim.confidence:.2f}")
    print(f"Model support:     {evidence.model_support:.2f}")
    print(f"OOD score:         {evidence.out_of_distribution_score:.2f}")
    print(f"TRACE status:      {result.status.value}")
    print(f"Consumer decision: {result.decision.value}")
    print("Failed gates:      " + (", ".join(result.failed_gates) if result.failed_gates else "none"))
    print("Missing items:     " + (", ".join(result.missing_items) if result.missing_items else "none"))
    print(f"Reason:            {result.reason}")


policy = PolicyConfig.from_yaml("configs/policies/trace_v1.yaml")
engine = PolicyEngine(policy)

claim = Claim(
    claim_id="claim-policy-demo-north-route",
    layer=ClaimLayer.PREDICTIVE,
    text="The North Channel is open for rescue-boat dispatch.",
    grounding={"route_id": "north_channel", "asset_type": "rescue_boat"},
    confidence=0.92,
    confidence_semantics="Teaching fixture; not a substitute for model support.",
)

unsupported = make_evidence(model_support=0.28, ood_score=0.82)
supported = make_evidence(model_support=0.90, ood_score=0.10)

show_case(
    "Case 1: Unsupported irreversible dispatch",
    engine=engine,
    claim=claim,
    evidence=unsupported,
    action_name="dispatch_rescue_boat",
    reversible=False,
    authority_present=True,
)
show_case(
    "Case 2: Unsupported but reversible verification",
    engine=engine,
    claim=claim,
    evidence=unsupported,
    action_name="verify_route",
    reversible=True,
    authority_present=False,
)
show_case(
    "Case 3: Supported dispatch without authority",
    engine=engine,
    claim=claim,
    evidence=supported,
    action_name="dispatch_rescue_boat",
    reversible=False,
    authority_present=False,
)
show_case(
    "Case 4: Supported dispatch with authority",
    engine=engine,
    claim=claim,
    evidence=supported,
    action_name="dispatch_rescue_boat",
    reversible=False,
    authority_present=True,
)
