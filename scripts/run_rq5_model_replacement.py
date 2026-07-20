from __future__ import annotations

import argparse
import json
from pathlib import Path

from trace_jepa.contracts import Claim, ClaimLayer, WorldModelEvidence
from trace_jepa.runtime import PolicyConfig, PolicyEngine
from trace_jepa.util import sha256_value
from trace_jepa.worldmodels.versioning import GuardedPolicyEngine, ModelQualification, ModelRegistry


def _evidence(version: str) -> WorldModelEvidence:
    return WorldModelEvidence(
        encoder_version="frozen-encoder-controlled-v1",
        fusion_version="route-fusion-v1",
        predictor_version=version,
        semantic_probe_versions=("route-probe-v1",),
        training_snapshot="rq5-identical-output-control-v1",
        observation_window_hash="paired-observation",
        fleet_state_hash="paired-fleet",
        candidate_plan_id="paired-plan",
        action_schema_version="flood-actions-dynamic-v1",
        rollout_horizon=2,
        predicted_claims=("the route-conditioned action prefix is supported",),
        uncertainty=0.12,
        model_support=0.88,
        out_of_distribution_score=0.10,
        rollout_consistency=0.92,
        calibration_version="controlled-calibration-v1",
        observation_age_s=4.0,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the RQ5 development control for midmission model replacement"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--decisions", type=int, default=20)
    parser.add_argument("--replacement-at", type=int, default=10)
    parser.add_argument("--revalidate-after", type=int, default=3)
    args = parser.parse_args()
    if not 0 < args.replacement_at < args.decisions:
        raise SystemExit("--replacement-at must be inside the decision sequence")

    base = PolicyEngine(
        PolicyConfig(
            policy_version="trace-rq5-controlled-v1",
            min_model_support=0.55,
            max_ood_score=0.45,
            max_uncertainty=0.40,
            max_rollout_horizon=4,
            max_observation_age_s=60.0,
        )
    )
    registry = ModelRegistry()
    registry.install(
        ModelQualification(
            predictor_version="route-model-a",
            predictor_checkpoint_sha256="a" * 64,
            calibration_version="controlled-calibration-v1",
            manifest_sha256="1" * 64,
            qualified_action_types=("dispatch_rescue_boat",),
            qualified=True,
        ),
        make_current=True,
    )
    registry.install(
        ModelQualification(
            predictor_version="route-model-b",
            predictor_checkpoint_sha256="b" * 64,
            calibration_version="controlled-calibration-v1",
            manifest_sha256="2" * 64,
            qualified_action_types=("dispatch_rescue_boat",),
            qualified=False,
        )
    )
    guarded = GuardedPolicyEngine(base, registry)
    claim = Claim(
        layer=ClaimLayer.PREDICTIVE,
        text="The route-conditioned dispatch prefix remains safe within the recorded horizon.",
    )
    rows: list[dict[str, object]] = []
    for index in range(args.decisions):
        if index == args.replacement_at:
            registry.replace("route-model-b")
        if index == args.replacement_at + args.revalidate_after:
            registry.qualify("route-model-b", manifest_sha256="2" * 64)
        version = "route-model-a" if index < args.replacement_at else "route-model-b"
        model_evidence = _evidence(version)
        common = {
            "action_name": "dispatch_rescue_boat",
            "reversible": False,
            "authority_present": True,
        }
        legacy = base.evaluate(claim, model_evidence, **common)
        guarded_result = guarded.evaluate(claim, model_evidence, **common)
        unsafe_context = (
            index >= args.replacement_at and index < args.replacement_at + args.revalidate_after
        )
        rows.append(
            {
                "decision_index": index,
                "predictor_version": version,
                "replacement_unqualified": unsafe_context,
                "legacy_decision": legacy.decision.value,
                "guarded_decision": guarded_result.decision.value,
                "legacy_unsafe_clear": unsafe_context and legacy.decision.value == "clear",
                "guarded_unsafe_clear": unsafe_context and guarded_result.decision.value == "clear",
            }
        )
    report = {
        "report_version": "rq5-model-replacement-controlled-development-v1",
        "design": (
            "paired identical predictions; only model qualification state changes, isolating "
            "the causal effect of the additive version guard"
        ),
        "decisions": args.decisions,
        "replacement_at": args.replacement_at,
        "revalidation_delay_decisions": args.revalidate_after,
        "legacy_unsafe_clears": sum(bool(row["legacy_unsafe_clear"]) for row in rows),
        "guarded_unsafe_clears": sum(bool(row["guarded_unsafe_clear"]) for row in rows),
        "guarded_holds": sum(row["guarded_decision"] == "hold" for row in rows),
        "registry_chain_valid": registry.verify_chain(),
        "registry_events": [event.model_dump(mode="json") for event in registry.events],
        "rows": rows,
        "test_seeds_accessed": False,
        "claim_boundary": "structural development control; not a final end-to-end effectiveness result",
    }
    report["result_sha256"] = sha256_value(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(
        f"legacy_unsafe_clears={report['legacy_unsafe_clears']} "
        f"guarded_unsafe_clears={report['guarded_unsafe_clears']}"
    )
    print(f"Wrote RQ5 development control: {args.output}")


if __name__ == "__main__":
    main()
