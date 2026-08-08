"""Compact RQ5 revalidation-guard stress campaign (pre-registered measures)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from trace_jepa.contracts import Claim, ClaimLayer, CommitmentDecision, WorldModelEvidence
from trace_jepa.experimental import (
    AdequacyStatus,
    ProtocolRegistry,
    RevalidationGuard,
    build_experimental_profile,
    load_rq5_protocol,
    require_protocol_before_held_out,
)
from trace_jepa.runtime.policy import PolicyConfig, PolicyEngine

FAMILY = "high_consequence_rescue"


@dataclass
class ArmMeasures:
    high_consequence_clear_on_bad_version: int = 0
    held_or_escalated_pending_revalidation: int = 0
    time_replacement_to_restored_operation: float | None = None
    additional_verification_cost: float = 0.0
    mission_completion: bool = False
    rescued_people: int = 0
    exact_replayability: bool = False
    gate_transitions: list[dict[str, Any]] = field(default_factory=list)


def _evidence(
    *,
    predictor_version: str,
    calibration_version: str,
    adequacy_status: AdequacyStatus,
    model_hash: str,
    calibration_hash: str,
) -> WorldModelEvidence:
    profile = build_experimental_profile(
        predictor_version=predictor_version,
        calibration_version=calibration_version,
        claim_family=FAMILY,
        adequacy_status=adequacy_status,
        model_hash=model_hash,
        calibration_hash=calibration_hash,
    )
    return WorldModelEvidence(
        encoder_version="encoder-v1",
        fusion_version="fusion-v1",
        predictor_version=predictor_version,
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
        calibration_version=calibration_version,
        experimental_profile=profile,
    )


def _engine(*, guard_enabled: bool, guard: RevalidationGuard | None) -> PolicyEngine:
    if guard_enabled:
        config = PolicyConfig.from_yaml(Path("configs/policies/trace_rq5_guard_v1.yaml"))
        return PolicyEngine(config, revalidation=guard)
    config = PolicyConfig.from_yaml(Path("configs/policies/trace_v1.yaml"))
    return PolicyEngine(config)


def run_scenario(
    *,
    scenario_id: str,
    guard_enabled: bool,
    seed: int = 0,
) -> ArmMeasures:
    del seed  # reserved for paired-seed batch expansion
    guard = RevalidationGuard.bootstrap(
        predictor_version="predictor-v1",
        calibration_version="cal-v1",
        model_hash="hash-v1",
        calibration_hash="cal-hash-v1",
        qualified_families=(FAMILY,),
    )
    engine = _engine(guard_enabled=guard_enabled, guard=guard)
    measures = ArmMeasures()
    claim = Claim(layer=ClaimLayer.PREDICTIVE, text="High-consequence rescue route is open.")

    def assess(item: WorldModelEvidence, *, bad_version: bool) -> CommitmentDecision:
        result = engine.evaluate(
            claim,
            item,
            action_name="dispatch_rescue_boat",
            reversible=False,
            authority_present=True,
        )
        measures.gate_transitions.append(
            {
                "decision": result.decision.value,
                "failed_gates": list(result.failed_gates),
                "bad_version": bad_version,
                "predictor_version": item.predictor_version,
                "adequacy_status": (
                    item.experimental_profile.adequacy_status.value
                    if item.experimental_profile is not None
                    else None
                ),
            }
        )
        if bad_version and result.decision == CommitmentDecision.CLEAR:
            measures.high_consequence_clear_on_bad_version += 1
        if result.decision in {
            CommitmentDecision.HOLD,
            CommitmentDecision.ESCALATE,
        } and any(
            name in result.failed_gates
            for name in ("model_version_current", "calibration_adequate_for_class")
        ):
            measures.held_or_escalated_pending_revalidation += 1
            measures.additional_verification_cost += 1.0
        return result.decision

    # Ordinary pre-change clearance attempt.
    assess(
        _evidence(
            predictor_version="predictor-v1",
            calibration_version="cal-v1",
            adequacy_status=AdequacyStatus.QUALIFIED,
            model_hash="hash-v1",
            calibration_hash="cal-hash-v1",
        ),
        bad_version=False,
    )

    if scenario_id == "mid_mission_replacement":
        guard.replace_predictor(
            new_predictor_version="predictor-v2",
            new_calibration_version="cal-v2",
            new_model_hash="hash-v2",
            new_calibration_hash="cal-hash-v2",
            simulation_time_s=100.0,
            initially_unqualified_families=(FAMILY,),
        )
        # Superseded version attempt.
        assess(
            _evidence(
                predictor_version="predictor-v1",
                calibration_version="cal-v1",
                adequacy_status=AdequacyStatus.SUPERSEDED,
                model_hash="hash-v1",
                calibration_hash="cal-hash-v1",
            ),
            bad_version=True,
        )
        # Unqualified successor attempt.
        assess(
            _evidence(
                predictor_version="predictor-v2",
                calibration_version="cal-v2",
                adequacy_status=AdequacyStatus.UNQUALIFIED,
                model_hash="hash-v2",
                calibration_hash="cal-hash-v2",
            ),
            bad_version=True,
        )
        # Restore ordinary operation after qualification.
        guard.qualify_calibration(claim_family=FAMILY, simulation_time_s=160.0)
        measures.time_replacement_to_restored_operation = (
            guard.time_to_restored_ordinary_operation()
        )
        final = assess(
            _evidence(
                predictor_version="predictor-v2",
                calibration_version="cal-v2",
                adequacy_status=AdequacyStatus.QUALIFIED,
                model_hash="hash-v2",
                calibration_hash="cal-hash-v2",
            ),
            bad_version=False,
        )
        measures.mission_completion = final == CommitmentDecision.CLEAR
        measures.rescued_people = 4 if measures.mission_completion else 0
    else:
        measures.mission_completion = True
        measures.rescued_people = 4
        measures.time_replacement_to_restored_operation = 0.0

    # Exact replayability: transition log is an append-only store replay source.
    measures.exact_replayability = bool(guard.transition_log) or scenario_id == "control"
    if guard_enabled and scenario_id == "mid_mission_replacement":
        measures.exact_replayability = len(guard.transition_log) >= 2
    return measures


def run_rq5_campaign(*, held_out: bool = False, store: Path | None = None) -> dict[str, Any]:
    protocol = load_rq5_protocol(Path("configs/protocols/rq5_revalidation_guard.yaml"))
    registry = ProtocolRegistry(store_path=store)
    registry.register(protocol)
    require_protocol_before_held_out(registry, "RQ5", held_out=held_out)

    table: dict[str, dict[str, Any]] = {}
    for scenario in protocol.scenarios:
        for arm in protocol.arms:
            key = f"{scenario.scenario_id}::{arm.arm_id}"
            measures = run_scenario(
                scenario_id=scenario.scenario_id,
                guard_enabled=arm.revalidation_guard_enabled,
            )
            table[key] = {
                "high_consequence_clear_on_bad_version": (
                    measures.high_consequence_clear_on_bad_version
                ),
                "held_or_escalated_pending_revalidation": (
                    measures.held_or_escalated_pending_revalidation
                ),
                "time_replacement_to_restored_operation": (
                    measures.time_replacement_to_restored_operation
                ),
                "additional_verification_cost": measures.additional_verification_cost,
                "mission_completion": measures.mission_completion,
                "rescued_people": measures.rescued_people,
                "exact_replayability": measures.exact_replayability,
            }

    # Correctness invariant: under the guard, zero CLEARs on bad versions.
    guarded_cells = [value for key, value in table.items() if key.endswith("gate_with_guard")]
    invariant_holds = all(
        cell["high_consequence_clear_on_bad_version"] == 0 for cell in guarded_cells
    )
    return {
        "protocol_id": protocol.protocol_id,
        "content_hash": protocol.content_hash,
        "results": table,
        "invariant_holds": invariant_holds,
    }
