"""Appendix B formal-extension / theorem-regime synthetic checks."""

import math

from trace_jepa.experimental.formal import (
    closed_form_deadline,
    periodic_vs_deadline_scheduler_counts,
    run_synthetic_regime_tests,
    subtick_or_rate_limit_decision,
    verify_censored_cost_identity,
    zeno_log_multiplier_mean,
)


def test_closed_form_deadline_matches_gaussian_threshold():
    distance = 2.0
    sigma = 1.0
    eta = 0.1
    deadline = closed_form_deadline(distance=distance, sigma=sigma, eta=eta)
    # d / (sigma * sqrt(t)) == z_{1-eta}
    from trace_jepa.experimental.formal import _norm_ppf

    z = _norm_ppf(1.0 - eta)
    standardized = distance / (sigma * math.sqrt(deadline))
    assert abs(standardized - z) < 1e-9


def test_censored_cost_identity_holds_on_synthetic_path():
    distances = [1.0, 0.7, 0.49, 0.343, 0.2401]
    sigma = 1.0
    eta = 0.1
    # Censor inside the third paid interval.
    t0 = closed_form_deadline(distance=distances[0], sigma=sigma, eta=eta)
    t1 = closed_form_deadline(distance=distances[1], sigma=sigma, eta=eta)
    t2 = closed_form_deadline(distance=distances[2], sigma=sigma, eta=eta)
    horizon = t0 + t1 + 0.5 * t2
    assert verify_censored_cost_identity(
        distances=distances,
        sigma=sigma,
        eta=eta,
        horizon_t=horizon,
    )


def test_scheduler_separation_counting_argument():
    periodic, deadline_checks, ratio = periodic_vs_deadline_scheduler_counts(
        deadlines=(2.0, 3.0, 5.0, 8.0)
    )
    s_n = 18.0
    tau_min = 2.0
    assert deadline_checks == 4
    assert periodic == math.floor(s_n / tau_min) + 1
    assert periodic >= math.ceil(s_n / tau_min)
    assert ratio > 1.0
    assert periodic / deadline_checks > ratio - 1e-12


def test_zeno_subtick_guard_returns_hold():
    decision = subtick_or_rate_limit_decision(
        theoretical_deadline_s=0.1,
        tick_s=1.0,
        verification_rate=0.0,
        max_verification_rate=10.0,
        cumulative_cost=0.0,
        max_cost=100.0,
    )
    assert decision == "HOLD"


def test_zeno_critical_eta_has_near_zero_log_mean():
    # Below η0 the mean log-multiplier is negative (contraction); above, positive.
    mean_low = zeno_log_multiplier_mean(eta=0.20, samples=20_000, seed=1)
    mean_high = zeno_log_multiplier_mean(eta=0.35, samples=20_000, seed=1)
    assert mean_low < 0.0
    assert mean_high > 0.0


def test_synthetic_regime_suite_passes():
    report = run_synthetic_regime_tests()
    assert report.cost_identity_ok
    assert report.scheduler_separation_ok
    assert report.zeno_guard_ok
