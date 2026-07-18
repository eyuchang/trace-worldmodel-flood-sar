from __future__ import annotations

from trace_jepa.refresh.base import (
    ClaimView,
    PendingCommitment,
    RefreshDecision,
    RefreshMode,
    RefreshState,
)


class NoRefreshPolicy:
    name = "none"

    def decide(
        self,
        state: RefreshState,
        claims: tuple[ClaimView, ...],
        pending: PendingCommitment | None,
    ) -> RefreshDecision:
        return RefreshDecision(
            policy=self.name,
            commitment_id=pending.commitment_id if pending else None,
            claim_id=pending.claim_id if pending else None,
            mode=RefreshMode.CONTINUE,
            rationale="no-refresh control never initiates policy-driven evidence",
        )
