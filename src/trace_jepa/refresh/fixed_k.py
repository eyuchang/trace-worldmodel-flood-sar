from __future__ import annotations

from pydantic import Field

from trace_jepa.refresh.base import (
    ChannelValue,
    ClaimView,
    PendingCommitment,
    RefreshDecision,
    RefreshMode,
    RefreshState,
    TriggerFamily,
    acquisition_guard_reason,
    select_scheduled_channel,
    withdrawal_mode,
    FrozenModel,
)


class FixedIntervalConfig(FrozenModel):
    interval_s: float = Field(gt=0.0)


class FixedIntervalRefreshPolicy:
    name = "fixed_k"

    def __init__(self, interval_s: float):
        self.config = FixedIntervalConfig(interval_s=interval_s)

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
                next_due_at=state.now + self.config.interval_s,
                rationale="no pending commitment",
            )
        anchor = pending.observed_at if pending.observed_at is not None else 0.0
        due_at = anchor + self.config.interval_s
        if state.now < due_at:
            return RefreshDecision(
                policy=self.name,
                commitment_id=pending.commitment_id,
                claim_id=pending.claim_id,
                mode=RefreshMode.CONTINUE,
                next_due_at=due_at,
                rationale="fixed interval has not elapsed",
            )

        guard = acquisition_guard_reason(state, pending)
        channel: ChannelValue | None = (
            None if guard else select_scheduled_channel(state, pending)
        )
        if channel is not None:
            return RefreshDecision(
                policy=self.name,
                commitment_id=pending.commitment_id,
                claim_id=pending.claim_id,
                triggered_families=(TriggerFamily.SCHEDULED,),
                mode=RefreshMode.ACQUIRE,
                voi_table=pending.channels,
                selected_channel=channel.channel,
                next_due_at=state.now + self.config.interval_s,
                rationale="fixed interval elapsed; use the predeclared comparator channel",
            )
        return RefreshDecision(
            policy=self.name,
            commitment_id=pending.commitment_id,
            claim_id=pending.claim_id,
            triggered_families=(TriggerFamily.SCHEDULED,),
            mode=withdrawal_mode(pending),
            voi_table=pending.channels,
            next_due_at=state.now + self.config.interval_s,
            rationale=guard or "no comparator channel can return before the horizon",
        )
