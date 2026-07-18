from __future__ import annotations

from trace_jepa.refresh.base import (
    ADAPTIVE_FAMILY_ORDER,
    ClaimView,
    PendingCommitment,
    RefreshDecision,
    RefreshMode,
    RefreshState,
    TriggerFamily,
    acquisition_guard_reason,
    claim_for_pending,
    select_channel,
    withdrawal_mode,
)


class AdaptiveRefreshPolicy:
    name = "adaptive"

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
        if claim is None:
            return RefreshDecision(
                policy=self.name,
                commitment_id=pending.commitment_id,
                claim_id=pending.claim_id,
                triggered_families=(TriggerFamily.STRUCTURAL,),
                mode=withdrawal_mode(pending),
                q=pending.flip_risk,
                rationale="pending commitment has no attributable claim view",
            )

        fired: set[TriggerFamily] = set()
        validity_shortfall = None
        if claim.validity_until is not None:
            validity_shortfall = claim.validity_until - pending.commitment_horizon_end
        if (
            claim.validity_until is None
            or (validity_shortfall is not None and validity_shortfall < 0.0)
            or claim.uncertainty > state.max_uncertainty
            or claim.rollout_horizon > state.max_rollout_horizon
            or claim.observation_age_s > state.max_observation_age_s
            or pending.regret >= pending.epsilon_c
        ):
            fired.add(TriggerFamily.PREDICTED)
        if (
            claim.observed_innovation is not None
            and claim.innovation_tolerance is not None
            and abs(claim.observed_innovation) > claim.innovation_tolerance
        ):
            fired.add(TriggerFamily.OBSERVED)
        if (
            claim.model_support < state.min_model_support
            or claim.out_of_distribution_score > state.max_ood_score
        ):
            fired.add(TriggerFamily.STRUCTURAL)
        if pending.requires_authority and not pending.authority_present:
            fired.add(TriggerFamily.NORMATIVE)

        ordered = tuple(family for family in ADAPTIVE_FAMILY_ORDER if family in fired)
        if not ordered:
            return RefreshDecision(
                policy=self.name,
                commitment_id=pending.commitment_id,
                claim_id=pending.claim_id,
                mode=RefreshMode.CONTINUE,
                q=pending.flip_risk,
                d_or_margin=pending.epsilon_c - pending.regret,
                rationale="no adaptive trigger family fired",
            )

        deadline = min(
            value
            for value in (claim.validity_until, pending.commitment_horizon_end)
            if value is not None
        )
        if deadline - state.now < state.tick_s:
            return RefreshDecision(
                policy=self.name,
                commitment_id=pending.commitment_id,
                claim_id=pending.claim_id,
                triggered_families=ordered,
                mode=withdrawal_mode(pending),
                q=pending.flip_risk,
                d_or_margin=deadline - state.now,
                voi_table=pending.channels,
                rationale="authorization deadline is less than one simulator tick away",
            )

        guard = acquisition_guard_reason(state, pending)
        channel = None if guard else select_channel(state, pending)
        if channel is not None:
            return RefreshDecision(
                policy=self.name,
                commitment_id=pending.commitment_id,
                claim_id=pending.claim_id,
                triggered_families=ordered,
                mode=RefreshMode.ACQUIRE,
                q=pending.flip_risk,
                d_or_margin=pending.regret - pending.epsilon_c,
                voi_table=pending.channels,
                selected_channel=channel.channel,
                rationale="an adequate channel has strictly positive net value",
            )
        return RefreshDecision(
            policy=self.name,
            commitment_id=pending.commitment_id,
            claim_id=pending.claim_id,
            triggered_families=ordered,
            mode=withdrawal_mode(pending),
            q=pending.flip_risk,
            d_or_margin=pending.regret - pending.epsilon_c,
            voi_table=pending.channels,
            rationale=guard or "no adequate positive-net-value channel is available",
        )
