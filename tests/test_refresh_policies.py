from __future__ import annotations

import pytest
from pydantic import ValidationError

from trace_jepa.refresh import (
    AdaptiveRefreshPolicy,
    ChannelValue,
    ClaimView,
    FixedIntervalRefreshPolicy,
    NoRefreshPolicy,
    PendingCommitment,
    RefreshMode,
    RefreshState,
    TriggerFamily,
    ValidityClockRefreshPolicy,
)


def _channels() -> tuple[ChannelValue, ...]:
    return (
        ChannelValue(
            channel="gauge_poll",
            clear_probability=0.90,
            value_of_information=3.0,
            cost=0.2,
            latency_s=5.0,
        ),
        ChannelValue(
            channel="drone_survey",
            clear_probability=0.95,
            value_of_information=8.0,
            cost=5.1,
            latency_s=30.0,
        ),
    )


def _claim(**updates) -> ClaimView:
    values = {
        "claim_id": "claim-1",
        "model_support": 0.80,
        "out_of_distribution_score": 0.20,
        "uncertainty": 0.20,
        "rollout_horizon": 5,
        "observation_age_s": 30.0,
        "validity_until": 200.0,
        "observed_innovation": 0.0,
        "innovation_tolerance": 0.1,
    }
    values.update(updates)
    return ClaimView(**values)


def _pending(**updates) -> PendingCommitment:
    values = {
        "commitment_id": "commitment-1",
        "claim_id": "claim-1",
        "action_class": "dispatch_rescue_boat",
        "route_id": "north_channel",
        "reversible": False,
        "requires_authority": True,
        "authority_present": True,
        "commitment_horizon_end": 100.0,
        "failure_probability": 0.02,
        "selected_action": "fast",
        "epsilon_c": 1.0,
        "failure_loss": 100.0,
        "safe_loss": 15.0,
        "safe_alternative_available": False,
        "pending_evidence": False,
        "last_evidence_acquired_at": None,
        "observed_at": 0.0,
        "channels": _channels(),
    }
    values.update(updates)
    return PendingCommitment(**values)


def _state(**updates) -> RefreshState:
    values = {"now": 10.0, "tick_s": 1.0, "min_refresh_interval_s": 5.0}
    values.update(updates)
    return RefreshState(**values)


def test_no_refresh_never_initiates_evidence() -> None:
    decision = NoRefreshPolicy().decide(_state(), (_claim(uncertainty=0.9),), _pending())
    assert decision.mode == RefreshMode.CONTINUE
    assert decision.triggered_families == ()
    assert decision.selected_channel is None


@pytest.mark.parametrize(
    "claim_updates,pending_updates,family",
    [
        ({"uncertainty": 0.31}, {}, TriggerFamily.PREDICTED),
        (
            {"observed_innovation": 0.11, "innovation_tolerance": 0.10},
            {},
            TriggerFamily.OBSERVED,
        ),
        ({"model_support": 0.59}, {}, TriggerFamily.STRUCTURAL),
        ({}, {"authority_present": False}, TriggerFamily.NORMATIVE),
    ],
)
def test_adaptive_trigger_families(
    claim_updates, pending_updates, family
) -> None:
    decision = AdaptiveRefreshPolicy().decide(
        _state(), (_claim(**claim_updates),), _pending(**pending_updates)
    )
    assert family in decision.triggered_families


def test_adaptive_records_all_simultaneous_families_in_table_order() -> None:
    decision = AdaptiveRefreshPolicy().decide(
        _state(),
        (
            _claim(
                uncertainty=0.31,
                observed_innovation=0.11,
                model_support=0.59,
            ),
        ),
        _pending(authority_present=False),
    )
    assert decision.triggered_families == (
        TriggerFamily.PREDICTED,
        TriggerFamily.OBSERVED,
        TriggerFamily.STRUCTURAL,
        TriggerFamily.NORMATIVE,
    )


def test_trigger_threshold_equalities_pass_except_regret() -> None:
    quiet = AdaptiveRefreshPolicy().decide(
        _state(),
        (
            _claim(
                model_support=0.60,
                out_of_distribution_score=0.35,
                uncertainty=0.30,
                rollout_horizon=8,
                observation_age_s=120.0,
                observed_innovation=0.10,
                innovation_tolerance=0.10,
            ),
        ),
        _pending(failure_probability=0.01),
    )
    assert quiet.triggered_families == ()

    # R_fast = p * (L - Delta) = 1.0 exactly; equality fires.
    regret_boundary = AdaptiveRefreshPolicy().decide(
        _state(),
        (_claim(),),
        _pending(failure_probability=1.0 / 85.0),
    )
    assert TriggerFamily.PREDICTED in regret_boundary.triggered_families


def test_consequence_scaled_regret_and_flip_risk_are_not_conflated() -> None:
    fast = _pending(failure_probability=0.2, selected_action="fast")
    safe = _pending(failure_probability=0.2, selected_action="safe")
    assert fast.decision_boundary == pytest.approx(0.15)
    assert fast.flip_risk == pytest.approx(0.2)
    assert fast.regret == pytest.approx(17.0)
    assert safe.flip_risk == pytest.approx(0.8)
    assert safe.regret == pytest.approx(12.0)


def test_adequate_set_is_filtered_before_net_value() -> None:
    pending = _pending(
        channels=(
            ChannelValue(
                channel="gauge_poll",
                clear_probability=0.79,
                value_of_information=100.0,
                cost=0.2,
                latency_s=5.0,
            ),
            ChannelValue(
                channel="drone_survey",
                clear_probability=0.85,
                value_of_information=6.0,
                cost=5.0,
                latency_s=20.0,
            ),
        )
    )
    decision = AdaptiveRefreshPolicy().decide(
        _state(), (_claim(uncertainty=0.31),), pending
    )
    assert decision.mode == RefreshMode.ACQUIRE
    assert decision.selected_channel == "drone_survey"


def test_channel_ties_follow_declared_channel_order() -> None:
    equal = (
        ChannelValue(
            channel="gauge_poll",
            clear_probability=0.9,
            value_of_information=5.2,
            cost=0.2,
            latency_s=5.0,
        ),
        ChannelValue(
            channel="drone_survey",
            clear_probability=0.9,
            value_of_information=10.0,
            cost=5.0,
            latency_s=20.0,
        ),
    )
    decision = AdaptiveRefreshPolicy().decide(
        _state(channel_order=("drone_survey", "gauge_poll")),
        (_claim(uncertainty=0.31),),
        _pending(channels=equal),
    )
    assert decision.selected_channel == "drone_survey"


def test_nonpositive_or_inadequate_channels_withdraw_authorization() -> None:
    channels = (
        ChannelValue(
            channel="gauge_poll",
            clear_probability=0.9,
            value_of_information=0.2,
            cost=0.2,
            latency_s=5.0,
        ),
    )
    held = AdaptiveRefreshPolicy().decide(
        _state(), (_claim(uncertainty=0.31),), _pending(channels=channels)
    )
    assert held.mode == RefreshMode.HOLD

    safe = AdaptiveRefreshPolicy().decide(
        _state(),
        (_claim(uncertainty=0.31),),
        _pending(channels=channels, safe_alternative_available=True),
    )
    assert safe.mode == RefreshMode.SAFE_ALTERNATIVE


def test_subtick_deadline_withdraws_without_acquisition() -> None:
    decision = AdaptiveRefreshPolicy().decide(
        _state(now=99.5, tick_s=1.0),
        (_claim(validity_until=100.0, uncertainty=0.31),),
        _pending(commitment_horizon_end=101.0),
    )
    assert decision.mode == RefreshMode.HOLD
    assert decision.selected_channel is None
    assert decision.d_or_margin == pytest.approx(0.5)


@pytest.mark.parametrize(
    "pending_updates",
    [
        {"pending_evidence": True},
        {"last_evidence_acquired_at": 8.0},
    ],
)
def test_zeno_guard_blocks_duplicate_or_too_frequent_acquisition(
    pending_updates,
) -> None:
    decision = AdaptiveRefreshPolicy().decide(
        _state(now=10.0, min_refresh_interval_s=5.0),
        (_claim(uncertainty=0.31),),
        _pending(**pending_updates),
    )
    assert decision.mode == RefreshMode.HOLD
    assert decision.selected_channel is None


def test_fixed_interval_fires_only_when_due() -> None:
    policy = FixedIntervalRefreshPolicy(interval_s=45.0)
    early = policy.decide(_state(now=44.9), (_claim(),), _pending(observed_at=0.0))
    due = policy.decide(_state(now=45.0), (_claim(),), _pending(observed_at=0.0))
    assert early.mode == RefreshMode.CONTINUE
    assert due.mode == RefreshMode.ACQUIRE
    assert due.triggered_families == (TriggerFamily.SCHEDULED,)


def test_validity_clock_uses_fractional_validity_interval() -> None:
    policy = ValidityClockRefreshPolicy(alpha=0.4)
    early = policy.decide(
        _state(now=39.9),
        (_claim(validity_until=100.0),),
        _pending(observed_at=0.0, commitment_horizon_end=120.0),
    )
    due = policy.decide(
        _state(now=40.0),
        (_claim(validity_until=100.0),),
        _pending(observed_at=0.0, commitment_horizon_end=120.0),
    )
    assert early.mode == RefreshMode.CONTINUE
    assert early.next_due_at == pytest.approx(40.0)
    assert due.mode == RefreshMode.ACQUIRE


def test_invalid_consequence_parameters_are_rejected() -> None:
    with pytest.raises(ValidationError, match="safe_loss"):
        _pending(safe_loss=100.0)
    with pytest.raises(ValidationError, match="regret assumption"):
        _pending(epsilon_c=7.5)
