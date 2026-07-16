from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from trace_jepa.contracts import (
    Claim,
    ClaimLayer,
    CommitmentDecision,
    EvaluationResult,
    TraceStatus,
    WorldModelEvidence,
)


class PolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: str
    min_model_support: float = Field(ge=0.0, le=1.0)
    max_ood_score: float = Field(ge=0.0, le=1.0)
    max_uncertainty: float = Field(ge=0.0, le=1.0)
    max_rollout_horizon: int = Field(ge=1)
    max_observation_age_s: float = Field(ge=0.0)
    require_authority_for: tuple[str, ...] = ()
    allow_qualified_reversible_probe: bool = True

    @classmethod
    def from_yaml(cls, path: Path) -> "PolicyConfig":
        return cls.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


class PolicyEngine:
    def __init__(self, config: PolicyConfig):
        self.config = config

    def evaluate(
        self,
        claim: Claim,
        evidence: WorldModelEvidence,
        *,
        action_name: str,
        reversible: bool,
        authority_present: bool,
        repair_hint: str | None = None,
    ) -> EvaluationResult:
        failed: list[str] = []
        missing: list[str] = []

        if evidence.decisively_contradicted:
            return EvaluationResult(
                status=TraceStatus.REJECT,
                decision=CommitmentDecision.BLOCK,
                failed_gates=("realized_contradiction",),
                repair="Generate a new claim from the realized observation and replan only dependent branches.",
                reason="The realized outcome decisively contradicts the recorded prediction.",
            )

        if evidence.model_support < self.config.min_model_support:
            failed.append("model_support")
            missing.append("evidence inside the declared model support")
        if evidence.out_of_distribution_score > self.config.max_ood_score:
            failed.append("out_of_distribution")
            missing.append("current observation or verification for the out-of-support region")
        if evidence.uncertainty > self.config.max_uncertainty:
            failed.append("uncertainty")
            missing.append("narrower calibrated uncertainty")
        if evidence.rollout_horizon > self.config.max_rollout_horizon:
            failed.append("rollout_horizon")
            missing.append("a shorter receding-horizon prefix")
        if evidence.observation_age_s > self.config.max_observation_age_s:
            failed.append("observation_freshness")
            missing.append("a fresh observation window")
        if claim.layer == ClaimLayer.CAUSAL and "state_sufficiency" not in evidence.assumptions:
            failed.append("causal_identification")
            missing.append("state-sufficiency or an explicitly model-conditional causal qualification")

        authority_required = action_name in self.config.require_authority_for
        if authority_required and not authority_present:
            return EvaluationResult(
                status=TraceStatus.DEFER,
                decision=CommitmentDecision.ESCALATE,
                failed_gates=tuple(failed),
                missing_items=tuple(missing + ["incident-command authorization"]),
                repair="Obtain authorization from the designated incident-command role.",
                reason="Technical evidence is not sufficient to cross the authority boundary.",
            )

        if failed:
            if reversible and self.config.allow_qualified_reversible_probe:
                return EvaluationResult(
                    status=TraceStatus.QUALIFY,
                    decision=CommitmentDecision.QUALIFY,
                    failed_gates=tuple(failed),
                    missing_items=tuple(missing),
                    repair=(
                        repair_hint
                        or "Limit the action to evidence gathering; monitor and do not commit the rescue branch yet."
                    ),
                    reason="A bounded reversible probe may proceed to resolve the named uncertainty.",
                )
            return EvaluationResult(
                status=TraceStatus.DEFER,
                decision=CommitmentDecision.HOLD,
                failed_gates=tuple(failed),
                missing_items=tuple(missing),
                repair=(
                    repair_hint
                    or "Gather the named evidence or select a supported alternative plan."
                ),
                reason="One or more hard technical gates failed.",
            )

        return EvaluationResult(
            status=TraceStatus.ACCEPT,
            decision=CommitmentDecision.CLEAR,
            reason="All declared technical gates passed for this action class.",
        )
