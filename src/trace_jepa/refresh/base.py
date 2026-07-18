from __future__ import annotations

from enum import Enum
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TriggerFamily(str, Enum):
    PREDICTED = "predicted"
    OBSERVED = "observed"
    STRUCTURAL = "structural"
    NORMATIVE = "normative"
    SCHEDULED = "scheduled"


ADAPTIVE_FAMILY_ORDER = (
    TriggerFamily.PREDICTED,
    TriggerFamily.OBSERVED,
    TriggerFamily.STRUCTURAL,
    TriggerFamily.NORMATIVE,
)


class RefreshMode(str, Enum):
    CONTINUE = "continue"
    ACQUIRE = "acquire"
    SAFE_ALTERNATIVE = "safe_alternative"
    HOLD = "hold"
    ESCALATE = "escalate"


class ClaimView(FrozenModel):
    claim_id: str
    model_support: float = Field(ge=0.0, le=1.0)
    out_of_distribution_score: float = Field(ge=0.0, le=1.0)
    uncertainty: float = Field(ge=0.0, le=1.0)
    rollout_horizon: int = Field(ge=0)
    observation_age_s: float = Field(ge=0.0)
    validity_until: float | None = Field(default=None, ge=0.0)
    observed_innovation: float | None = None
    innovation_tolerance: float | None = Field(default=None, ge=0.0)


class ChannelValue(FrozenModel):
    channel: Literal["gauge_poll", "drone_survey"]
    clear_probability: float = Field(ge=0.0, le=1.0)
    value_of_information: float = Field(ge=0.0)
    cost: float = Field(ge=0.0)
    latency_s: float = Field(ge=0.0)

    @computed_field
    @property
    def net_value(self) -> float:
        return self.value_of_information - self.cost


class PendingCommitment(FrozenModel):
    commitment_id: str
    claim_id: str
    action_class: str
    route_id: str | None = None
    reversible: bool = False
    requires_authority: bool = True
    authority_present: bool = True
    commitment_horizon_end: float = Field(ge=0.0)
    failure_probability: float = Field(ge=0.0, le=1.0)
    selected_action: Literal["fast", "safe", "probe"] = "fast"
    epsilon_c: float = Field(gt=0.0)
    failure_loss: float = Field(gt=0.0)
    safe_loss: float = Field(gt=0.0)
    safe_alternative_available: bool = False
    pending_evidence: bool = False
    last_evidence_acquired_at: float | None = Field(default=None, ge=0.0)
    observed_at: float | None = Field(default=None, ge=0.0)
    channels: tuple[ChannelValue, ...] = ()

    @model_validator(mode="after")
    def validate_consequence_model(self) -> "PendingCommitment":
        if self.safe_loss >= self.failure_loss:
            raise ValueError("safe_loss must be strictly less than failure_loss")
        upper = 0.5 * min(
            self.safe_loss, self.failure_loss - self.safe_loss
        )
        if self.epsilon_c >= upper:
            raise ValueError(
                "epsilon_c violates the consequence-scaled regret assumption"
            )
        return self

    @computed_field
    @property
    def decision_boundary(self) -> float:
        return self.safe_loss / self.failure_loss

    @computed_field
    @property
    def flip_risk(self) -> float:
        if self.selected_action == "safe":
            return 1.0 - self.failure_probability
        return self.failure_probability

    @computed_field
    @property
    def regret(self) -> float:
        if self.selected_action == "safe":
            return (1.0 - self.failure_probability) * self.safe_loss
        return self.failure_probability * (self.failure_loss - self.safe_loss)


class RefreshState(FrozenModel):
    now: float = Field(ge=0.0)
    tick_s: float = Field(default=1.0, gt=0.0)
    min_refresh_interval_s: float = Field(default=5.0, gt=0.0)
    min_model_support: float = Field(default=0.60, ge=0.0, le=1.0)
    max_ood_score: float = Field(default=0.35, ge=0.0, le=1.0)
    max_uncertainty: float = Field(default=0.30, ge=0.0, le=1.0)
    max_rollout_horizon: int = Field(default=8, ge=1)
    max_observation_age_s: float = Field(default=120.0, gt=0.0)
    gamma_irreversible: float = Field(default=0.80, ge=0.0, le=1.0)
    gamma_probe: float = Field(default=0.50, ge=0.0, le=1.0)
    channel_order: tuple[str, ...] = ("gauge_poll", "drone_survey")


class RefreshDecision(FrozenModel):
    refresh_decision_id: str | None = None
    policy: str
    commitment_id: str | None = None
    claim_id: str | None = None
    triggered_families: tuple[TriggerFamily, ...] = ()
    mode: RefreshMode = RefreshMode.CONTINUE
    q: float | None = Field(default=None, ge=0.0, le=1.0)
    d_or_margin: float | None = None
    voi_table: tuple[ChannelValue, ...] = ()
    selected_channel: str | None = None
    safe_alternative_plan_id: str | None = None
    next_due_at: float | None = Field(default=None, ge=0.0)
    rationale: str


@runtime_checkable
class RefreshPolicy(Protocol):
    name: str

    def decide(
        self,
        state: RefreshState,
        claims: tuple[ClaimView, ...],
        pending: PendingCommitment | None,
    ) -> RefreshDecision: ...


def claim_for_pending(
    claims: tuple[ClaimView, ...], pending: PendingCommitment
) -> ClaimView | None:
    return next((claim for claim in claims if claim.claim_id == pending.claim_id), None)


def select_channel(
    state: RefreshState,
    pending: PendingCommitment,
) -> ChannelValue | None:
    """Apply adequate-set-first VoI with a deterministic configured tie-break."""

    gamma = state.gamma_probe if pending.reversible else state.gamma_irreversible
    adequate = [
        channel
        for channel in pending.channels
        if channel.clear_probability >= gamma
        and channel.latency_s <= max(0.0, pending.commitment_horizon_end - state.now)
    ]
    positive = [channel for channel in adequate if channel.net_value > 0.0]
    if not positive:
        return None
    order = {channel: index for index, channel in enumerate(state.channel_order)}
    return min(
        positive,
        key=lambda channel: (
            -channel.net_value,
            order.get(channel.channel, len(order)),
            channel.channel,
        ),
    )


def select_scheduled_channel(
    state: RefreshState,
    pending: PendingCommitment,
) -> ChannelValue | None:
    """Use one declared channel rule for timing-only comparator policies."""

    available = [
        channel
        for channel in pending.channels
        if channel.latency_s <= max(0.0, pending.commitment_horizon_end - state.now)
    ]
    order = {channel: index for index, channel in enumerate(state.channel_order)}
    if not available:
        return None
    return min(
        available,
        key=lambda channel: (
            order.get(channel.channel, len(order)),
            channel.channel,
        ),
    )


def withdrawal_mode(pending: PendingCommitment) -> RefreshMode:
    if pending.safe_alternative_available:
        return RefreshMode.SAFE_ALTERNATIVE
    if pending.requires_authority and not pending.authority_present:
        return RefreshMode.ESCALATE
    return RefreshMode.HOLD


def acquisition_guard_reason(
    state: RefreshState, pending: PendingCommitment
) -> str | None:
    if pending.pending_evidence:
        return "evidence is already pending for this commitment"
    if pending.last_evidence_acquired_at is not None:
        elapsed = state.now - pending.last_evidence_acquired_at
        if elapsed < state.min_refresh_interval_s:
            return "minimum per-commitment refresh interval has not elapsed"
    return None
