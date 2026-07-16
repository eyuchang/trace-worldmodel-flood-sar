from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from trace_jepa.util import new_id, utc_now


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ClaimLayer(str, Enum):
    OBSERVATION = "observation"
    DIAGNOSTIC = "diagnostic"
    PREDICTIVE = "predictive"
    CAUSAL = "causal"
    PRACTICAL = "practical"
    AUTHORITY = "authority"


class TraceStatus(str, Enum):
    ACCEPT = "accept"
    QUALIFY = "qualify"
    REVISE = "revise"
    DEFER = "defer"
    REJECT = "reject"
    NO_ARGUMENT = "no_argument"


class CommitmentDecision(str, Enum):
    CLEAR = "clear"
    QUALIFY = "qualify"
    HOLD = "hold"
    BLOCK = "block"
    ESCALATE = "escalate"


class EmergencyCall(FrozenModel):
    """A normalized emergency report accepted by the Mission Controller.

    The raw caller text is preserved for audit, while operational modules use
    the normalized location identifier, people count, and deadline.
    """

    call_id: str = Field(default_factory=lambda: new_id("call"))
    raw_text: str = Field(min_length=1)
    reported_location: str
    normalized_location_id: str
    people_count: int = Field(ge=1)
    deadline_s: int = Field(default=1200, ge=60)
    source: str = "emergency_phone"
    caller_name: str | None = None
    caller_contact: str | None = None
    received_at: datetime = Field(default_factory=utc_now)


class ActionInstance(FrozenModel):
    """A grounded command proposed by the Mission Controller.

    The action is not an opaque string. It names the actor, destination, route,
    and mission parameters so that the planner, predictor, TRACE record,
    dispatcher, environment, and later audit all refer to the same object.
    """

    action_id: str = Field(default_factory=lambda: new_id("action"))
    action_type: str
    actor_id: str
    origin: str | None = None
    destination: str | None = None
    route_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)

    @property
    def short_label(self) -> str:
        actor = self.actor_id.replace("_", " ")
        route = self.route_id.replace("_", " ") if self.route_id else None
        destination = (
            self.destination.replace("_", " ") if self.destination else None
        )
        if self.action_type == "verify_route" and route:
            return f"{actor} verifies {route}"
        if self.action_type == "dispatch_rescue_boat":
            destination_text = f" to {destination}" if destination else ""
            route_text = f" via {route}" if route else ""
            return f"{actor} dispatches{destination_text}{route_text}"
        if self.action_type == "evacuate_to_safety":
            destination_text = f" to {destination}" if destination else " to safety"
            route_text = f" via {route}" if route else ""
            return f"{actor} evacuates onboard people{destination_text}{route_text}"
        action = self.action_type.replace("_", " ")
        return f"{actor}: {action}"


class Claim(FrozenModel):
    claim_id: str = Field(default_factory=lambda: new_id("claim"))
    layer: ClaimLayer
    text: str
    grounding: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence_semantics: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class PlanCandidate(FrozenModel):
    plan_id: str
    name: str
    actions: tuple[ActionInstance, ...]
    utility: float
    reversible_first_action: bool
    requires_authority: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def first_action(self) -> ActionInstance:
        return self.actions[0]


class PlanPrediction(FrozenModel):
    plan_id: str
    success_probability: float = Field(ge=0.0, le=1.0)
    arrival_time_s: float = Field(ge=0.0)
    hazard_score: float = Field(ge=0.0, le=1.0)
    resource_margin: float
    model_support: float = Field(ge=0.0, le=1.0)
    out_of_distribution_score: float = Field(ge=0.0, le=1.0)
    uncertainty: float = Field(ge=0.0, le=1.0)
    rollout_horizon: int = Field(ge=1)
    assumptions: tuple[str, ...] = ()


class WorldModelEvidence(FrozenModel):
    evidence_id: str = Field(default_factory=lambda: new_id("wm-evidence"))
    rollout_id: str = Field(default_factory=lambda: new_id("rollout"))
    encoder_version: str
    fusion_version: str
    predictor_version: str
    semantic_probe_versions: tuple[str, ...]
    training_snapshot: str
    observation_window_hash: str
    fleet_state_hash: str
    candidate_plan_id: str
    action_schema_version: str
    rollout_horizon: int = Field(ge=1)
    predicted_claims: tuple[str, ...]
    uncertainty: float = Field(ge=0.0, le=1.0)
    model_support: float = Field(ge=0.0, le=1.0)
    out_of_distribution_score: float = Field(ge=0.0, le=1.0)
    rollout_consistency: float = Field(ge=0.0, le=1.0)
    reachability_evidence: dict[str, Any] = Field(default_factory=dict)
    calibration_version: str
    assumptions: tuple[str, ...] = ()
    observation_age_s: float = Field(default=0.0, ge=0.0)
    decisively_contradicted: bool = False
    realized_outcome: dict[str, Any] | None = None
    prediction_residual: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ConsumerAction(FrozenModel):
    consumer_action_id: str = Field(default_factory=lambda: new_id("consumer"))
    consumer: str
    decision: CommitmentDecision
    consumer_policy_version: str
    record_id: str
    record_version: int
    reason: str
    created_at: datetime = Field(default_factory=utc_now)


class TraceRecord(FrozenModel):
    record_id: str = Field(default_factory=lambda: new_id("trace"))
    record_version: int = Field(default=1, ge=1)
    schema_version: str = "trace-student-v1"
    policy_version: str
    claim: Claim
    evidence_refs: tuple[str, ...]
    final_status: TraceStatus
    failed_gates: tuple[str, ...] = ()
    missing_items: tuple[str, ...] = ()
    repair: str | None = None
    consumer_actions: tuple[ConsumerAction, ...] = ()
    supersedes_record_id: str | None = None
    supersedes_record_version: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("evidence_refs")
    @classmethod
    def evidence_must_not_be_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("a TRACE record must reference at least one evidence object")
        return value


class EvaluationResult(FrozenModel):
    status: TraceStatus
    decision: CommitmentDecision
    failed_gates: tuple[str, ...] = ()
    missing_items: tuple[str, ...] = ()
    repair: str | None = None
    reason: str


class Commitment(FrozenModel):
    commitment_id: str = Field(default_factory=lambda: new_id("commitment"))
    action: ActionInstance
    authorizing_record_id: str
    authorizing_record_version: int
    consumer_policy_version: str
    created_at: datetime = Field(default_factory=utc_now)


class RealizedOutcome(FrozenModel):
    outcome_id: str = Field(default_factory=lambda: new_id("outcome"))
    action: ActionInstance
    success: bool
    observations: dict[str, Any] = Field(default_factory=dict)
    reason: str
    created_at: datetime = Field(default_factory=utc_now)
