from __future__ import annotations

from pydantic import Field

from trace_jepa.refresh.base import (
    ClaimView,
    PendingCommitment,
    RefreshDecision,
    RefreshMode,
    RefreshState,
    TriggerFamily,
    acquisition_guard_reason,
    claim_for_pending,
    select_scheduled_channel,
    withdrawal_mode,
    FrozenModel,
)


class ValidityClockConfig(FrozenModel):
    alpha: float = Field(ge=0.0, le=1.0)


class ValidityClockRefreshPolicy:
    name = "validity_clock"

    def __init__(self, alpha: float):
        self.config = ValidityClockConfig(alpha=alpha)

    def decide(
        self,
        state: RefreshState,
        claims: tuple[ClaimView, ...],
        pending: PendingCommitment | None,
    ) -> RefreshDecision:
        if pending is None:
            return RefreshDecision(
                policy=self.name,
                mode=RefreshMode.CONTINUE,
                rationale="no pending commitment",
            )
        claim = claim_for_pending(claims, pending)
        if claim is None or claim.validity_until is None:
            return RefreshDecision(
                policy=self.name,
                commitment_id=pending.commitment_id,
                claim_id=pending.claim_id,
                triggered_families=(TriggerFamily.PREDICTED,),
                mode=withdrawal_mode(pending),
                rationale="no declared validity interval is available",
            )
        observed_at = pending.observed_at if pending.observed_at is not None else state.now
        due_at = observed_at + self.config.alpha * max(
            0.0, claim.validity_until - observed_at
        )
        hard_deadline = min(claim.validity_until, pending.commitment_horizon_end)
        if hard_deadline - state.now < state.tick_s:
            return RefreshDecision(
                policy=self.name,
                commitment_id=pending.commitment_id,
                claim_id=pending.claim_id,
                triggered_families=(TriggerFamily.PREDICTED,),
                mode=withdrawal_mode(pending),
                d_or_margin=hard_deadline - state.now,
                rationale="validity deadline is less than one simulator tick away",
            )
        if state.now < due_at:
            return RefreshDecision(
                policy=self.name,
                commitment_id=pending.commitment_id,
                claim_id=pending.claim_id,
                mode=RefreshMode.CONTINUE,
                next_due_at=due_at,
                d_or_margin=hard_deadline - state.now,
                rationale="fractional validity-clock deadline has not elapsed",
            )
        guard = acquisition_guard_reason(state, pending)
        channel = None if guard else select_scheduled_channel(state, pending)
        if channel is not None:
            return RefreshDecision(
                policy=self.name,
                commitment_id=pending.commitment_id,
                claim_id=pending.claim_id,
                triggered_families=(TriggerFamily.PREDICTED,),
                mode=RefreshMode.ACQUIRE,
                d_or_margin=hard_deadline - state.now,
                voi_table=pending.channels,
                selected_channel=channel.channel,
                rationale="validity-clock deadline elapsed",
            )
        return RefreshDecision(
            policy=self.name,
            commitment_id=pending.commitment_id,
            claim_id=pending.claim_id,
            triggered_families=(TriggerFamily.PREDICTED,),
            mode=withdrawal_mode(pending),
            d_or_margin=hard_deadline - state.now,
            voi_table=pending.channels,
            rationale=guard or "no comparator channel can return before the horizon",
        )
