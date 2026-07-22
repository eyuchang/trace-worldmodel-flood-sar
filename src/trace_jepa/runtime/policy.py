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
from trace_jepa.experimental.profile import AdequacyStatus, ExperimentalProfileExtension
from trace_jepa.experimental.revalidation import RevalidationGuard


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
    # Section 5.5 revalidation guard (off by default for teaching baseline).
    enable_revalidation_guard: bool = False
    high_consequence_actions: tuple[str, ...] = (
        "dispatch_rescue_boat",
        "deploy_ground_team",
        "evacuate_to_safety",
    )

    @classmethod
    def from_yaml(cls, path: Path) -> "PolicyConfig":
        return cls.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


class PolicyEngine:
    def __init__(
        self,
        config: PolicyConfig,
        *,
        revalidation: RevalidationGuard | None = None,
    ):
        self.config = config
        self.revalidation = revalidation

    def attach_revalidation(self, guard: RevalidationGuard | None) -> None:
        self.revalidation = guard

    def is_high_consequence(self, action_name: str) -> bool:
        return action_name in self.config.high_consequence_actions

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

        revalidation_failed = self._apply_revalidation_guard(
            evidence,
            action_name=action_name,
            failed=failed,
            missing=missing,
        )

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
            # High-consequence actions must not QUALIFY through a revalidation
            # failure; the RQ5 invariant forbids CLEAR, and pending revalidation
            # is recorded as HOLD or ESCALATE.
            if revalidation_failed and self.is_high_consequence(action_name):
                return EvaluationResult(
                    status=TraceStatus.DEFER,
                    decision=CommitmentDecision.HOLD,
                    failed_gates=tuple(failed),
                    missing_items=tuple(missing),
                    repair=(
                        repair_hint
                        or "Hold high-consequence commitment pending model-version "
                        "revalidation or calibration qualification for the claim family."
                    ),
                    reason=(
                        "Revalidation guard blocked clearance on a superseded or "
                        "unqualified predictor version."
                    ),
                )
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

    def _apply_revalidation_guard(
        self,
        evidence: WorldModelEvidence,
        *,
        action_name: str,
        failed: list[str],
        missing: list[str],
    ) -> bool:
        if not self.config.enable_revalidation_guard:
            return False
        if self.revalidation is None:
            raise RuntimeError(
                "enable_revalidation_guard is true but no RevalidationGuard is attached"
            )

        profile = evidence.experimental_profile
        if profile is None:
            # Extension path required for the guard: synthesize a minimal profile
            # from core provenance fields so baseline evidence remains evaluable.
            profile = ExperimentalProfileExtension(
                predictor_version=evidence.predictor_version,
                calibration_version=evidence.calibration_version,
                claim_family=action_name,
                adequacy_status=AdequacyStatus.QUALIFIED,
                model_hash=None,
            )

        blocked = False
        if not self.revalidation.model_version_current(profile):
            failed.append("model_version_current")
            missing.append("prediction from the current, non-superseded predictor version")
            blocked = True
        if not self.revalidation.calibration_adequate_for_class(profile):
            failed.append("calibration_adequate_for_class")
            missing.append(
                "calibration qualified for the declared claim family / action class"
            )
            blocked = True
        self.revalidation.transition_log.append(
            {
                "event_type": "gate_revalidation_check",
                "action_name": action_name,
                "predictor_version": profile.predictor_version,
                "claim_family": profile.claim_family,
                "adequacy_status": profile.adequacy_status.value,
                "model_version_current": self.revalidation.model_version_current(profile),
                "calibration_adequate_for_class": (
                    self.revalidation.calibration_adequate_for_class(profile)
                ),
                "blocked": blocked,
            }
        )
        return blocked
