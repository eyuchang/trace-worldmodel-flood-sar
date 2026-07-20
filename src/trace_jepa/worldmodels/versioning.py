from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from trace_jepa.contracts import (
    Claim,
    CommitmentDecision,
    EvaluationResult,
    TraceStatus,
    WorldModelEvidence,
)
from trace_jepa.runtime import PolicyEngine
from trace_jepa.util import sha256_value, utc_now


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelQualification(FrozenModel):
    predictor_version: str
    predictor_checkpoint_sha256: str
    calibration_version: str
    manifest_sha256: str
    qualified_action_types: tuple[str, ...]
    qualified: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class ModelVersionEvent(FrozenModel):
    sequence: int = Field(ge=1)
    event_type: str
    predictor_version: str
    payload: dict[str, object] = Field(default_factory=dict)
    previous_hash: str | None = None
    event_hash: str


class ModelRegistry:
    """Append-only model qualification and replacement registry for RQ5."""

    def __init__(self) -> None:
        self._models: dict[str, ModelQualification] = {}
        self._current_version: str | None = None
        self._events: list[ModelVersionEvent] = []

    @property
    def current_version(self) -> str | None:
        return self._current_version

    @property
    def events(self) -> tuple[ModelVersionEvent, ...]:
        return tuple(self._events)

    def _append(self, event_type: str, version: str, payload: dict[str, object]) -> None:
        previous_hash = self._events[-1].event_hash if self._events else None
        body = {
            "sequence": len(self._events) + 1,
            "event_type": event_type,
            "predictor_version": version,
            "payload": payload,
            "previous_hash": previous_hash,
        }
        self._events.append(ModelVersionEvent(**body, event_hash=sha256_value(body)))

    def install(self, qualification: ModelQualification, *, make_current: bool = False) -> None:
        existing = self._models.get(qualification.predictor_version)
        if existing is not None and existing != qualification:
            raise ValueError("a predictor version cannot be rebound to different provenance")
        self._models[qualification.predictor_version] = qualification
        self._append(
            "MODEL_INSTALLED",
            qualification.predictor_version,
            {
                "checkpoint_sha256": qualification.predictor_checkpoint_sha256,
                "qualified": qualification.qualified,
            },
        )
        if make_current:
            self.replace(qualification.predictor_version)

    def replace(self, predictor_version: str) -> None:
        if predictor_version not in self._models:
            raise KeyError(f"predictor version is not installed: {predictor_version}")
        previous = self._current_version
        self._current_version = predictor_version
        self._append("MODEL_REPLACED", predictor_version, {"supersedes": previous or "none"})

    def qualify(self, predictor_version: str, *, manifest_sha256: str) -> None:
        current = self._models[predictor_version]
        if manifest_sha256 != current.manifest_sha256:
            raise ValueError("qualification manifest hash does not match the installed model")
        self._models[predictor_version] = current.model_copy(update={"qualified": True})
        self._append("MODEL_REVALIDATED", predictor_version, {"manifest_sha256": manifest_sha256})

    def clearance_failure(self, evidence: WorldModelEvidence, action_name: str) -> str | None:
        if evidence.predictor_version != self._current_version:
            return "superseded_model_version"
        model = self._models.get(evidence.predictor_version)
        if model is None:
            return "unregistered_model_version"
        if not model.qualified:
            return "unqualified_model_version"
        if model.calibration_version != evidence.calibration_version:
            return "unqualified_calibration_version"
        if action_name not in model.qualified_action_types:
            return "unqualified_action_class"
        return None

    def verify_chain(self) -> bool:
        previous_hash = None
        for event in self._events:
            body = event.model_dump(mode="json", exclude={"event_hash"})
            if body["previous_hash"] != previous_hash or sha256_value(body) != event.event_hash:
                return False
            previous_hash = event.event_hash
        return True


class GuardedPolicyEngine:
    """Monotone wrapper: model-version checks can restrict but never loosen TRACE."""

    def __init__(
        self,
        base: PolicyEngine,
        registry: ModelRegistry,
        *,
        high_consequence_actions: tuple[str, ...] = (
            "dispatch_rescue_boat",
            "dispatch_helicopter",
            "deploy_ground_team",
            "evacuate_to_safety",
        ),
    ):
        self.base = base
        self.registry = registry
        self.high_consequence_actions = high_consequence_actions
        self.config = base.config.model_copy(
            update={"policy_version": f"{base.config.policy_version}+model-version-guard-v1"}
        )

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
        base_result = self.base.evaluate(
            claim,
            evidence,
            action_name=action_name,
            reversible=reversible,
            authority_present=authority_present,
            repair_hint=repair_hint,
        )
        if action_name not in self.high_consequence_actions:
            return base_result
        if base_result.decision not in {CommitmentDecision.CLEAR, CommitmentDecision.QUALIFY}:
            return base_result
        failure = self.registry.clearance_failure(evidence, action_name)
        if failure is None:
            return base_result
        if reversible:
            return EvaluationResult(
                status=TraceStatus.QUALIFY,
                decision=CommitmentDecision.QUALIFY,
                failed_gates=base_result.failed_gates + (failure,),
                missing_items=base_result.missing_items + ("current qualified model evidence",),
                repair="Limit execution to a reversible evidence-gathering prefix and revalidate the model.",
                reason="The base gate permits only a bounded probe because model-version qualification failed.",
            )
        return EvaluationResult(
            status=TraceStatus.DEFER,
            decision=CommitmentDecision.HOLD,
            failed_gates=base_result.failed_gates + (failure,),
            missing_items=base_result.missing_items + ("current qualified model evidence",),
            repair="Revalidate the current model for this action class or generate evidence with a qualified model.",
            reason="A high-consequence commitment cannot use superseded or unqualified model evidence.",
        )
