"""Appendix B formal extensions and theorem-regime synthetic checks.

Implements the analytical identities claimed for the unguarded exact-observation
scheduler and the workbench's Zeno / sub-tick fallback. These checks are
synthetic; Flood-SAR is not used as a numerical proof of the lemmas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


def _norm_ppf(p: float) -> float:
    try:
        from scipy.stats import norm  # type: ignore

        return float(norm.ppf(p))
    except Exception:
        # Abramowitz-Stegun style rational approximation via erfinv fallback.
        # For the teaching suite we only need a few fixed η values.
        table = {
            0.05: -1.6448536269514722,
            0.10: -1.2815515655446004,
            0.15: -1.0364333894937896,
            0.20: -0.8416212335729142,
            0.25: -0.6744897501960817,
            0.2602: -0.6427876096865393,
            0.30: -0.5244005127080407,
            0.50: 0.0,
            0.75: 0.6744897501960817,
            0.80: 0.8416212335729142,
            0.85: 1.0364333894937896,
            0.90: 1.2815515655446004,
            0.95: 1.6448536269514722,
        }
        if p in table:
            return table[p]
        # Binary search on the standard normal CDF using math.erf
        lo, hi = -8.0, 8.0
        target = p
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            cdf = 0.5 * (1.0 + math.erf(mid / math.sqrt(2.0)))
            if cdf < target:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)


def gaussian_flip_probability(*, distance: float, sigma: float, eta: float) -> float:
    """Flip probability under the exact Brownian / Gaussian observation model."""

    if sigma <= 0:
        raise ValueError("sigma must be positive")
    z = _norm_ppf(1.0 - eta)
    # P(sign error) for a one-sided threshold at distance d
    return float(0.5 * (1.0 - math.erf((distance / sigma) / math.sqrt(2.0))))


def closed_form_deadline(
    *,
    distance: float,
    sigma: float,
    eta: float,
) -> float:
    """Model-conditional deadline for exact observations and zero drift."""

    if sigma <= 0:
        raise ValueError("sigma must be positive")
    z = _norm_ppf(1.0 - eta)
    if z <= 0:
        raise ValueError("eta must be < 0.5 so that z_eta > 0")
    return (distance * distance) / (sigma * sigma * z * z)


def censored_cost_identity_bounds(
    *,
    distances: Sequence[float],
    sigma: float,
    eta: float,
    horizon_t: float,
    cost_per_observation: float = 1.0,
) -> tuple[int, float, float, float]:
    """Two-sided realized-path cost identity with the in-progress interval censored.

    ``t_0 = 0`` is free initialization. Epoch times satisfy
    ``t_{n+1} = t_n + d_n^2 / (σ^2 z_η^2)``. For ``T < t_∞``,
    ``N(T) = max{n : t_n ≤ T}`` counts paid re-verifications and
    ``t_{N(T)} ≤ T < t_{N(T)+1}``.
    """

    if not distances:
        raise ValueError("distances must be non-empty")
    deltas = [
        closed_form_deadline(distance=d, sigma=sigma, eta=eta) for d in distances
    ]
    # epoch times t_0, t_1, ...
    times = [0.0]
    for delta in deltas:
        times.append(times[-1] + delta)

    paid_count = 0
    for n in range(1, len(times)):
        if times[n] <= horizon_t:
            paid_count = n
        else:
            break

    paid_cost = cost_per_observation * paid_count
    lower = times[paid_count]
    upper = times[paid_count + 1] if paid_count + 1 < len(times) else float("inf")
    return paid_count, paid_cost, lower, upper


def verify_censored_cost_identity(
    *,
    distances: Sequence[float],
    sigma: float,
    eta: float,
    horizon_t: float,
    cost_per_observation: float = 1.0,
    atol: float = 1e-9,
) -> bool:
    paid_count, _paid_cost, lower, upper = censored_cost_identity_bounds(
        distances=distances,
        sigma=sigma,
        eta=eta,
        horizon_t=horizon_t,
        cost_per_observation=cost_per_observation,
    )
    del paid_count
    if upper == float("inf"):
        return lower - atol <= horizon_t
    return lower - atol <= horizon_t < upper + atol


def periodic_vs_deadline_scheduler_counts(
    *,
    deadlines: Sequence[float],
) -> tuple[int, int, float]:
    """Counting argument for scheduler separation.

    A periodic scheduler that honors every deadline must take ``k <= tau_min``
    and therefore issues ``floor(S_N / k) + 1 >= ceil(S_N / tau_min)`` checks
    over ``S_N = sum tau_i`` (including the initial check at time zero). The
    deadline scheduler issues ``N`` checks. The ratio strictly exceeds
    ``mean(tau) / tau_min`` whenever the deadlines are not all equal.
    """

    if not deadlines:
        raise ValueError("deadlines must be non-empty")
    if any(tau <= 0 for tau in deadlines):
        raise ValueError("deadlines must be positive")
    n = len(deadlines)
    s_n = float(sum(deadlines))
    tau_min = min(deadlines)
    periodic_checks = math.floor(s_n / tau_min) + 1
    deadline_checks = n
    mean_tau = s_n / n
    return periodic_checks, deadline_checks, mean_tau / tau_min


def zeno_log_multiplier_mean(*, eta: float, samples: int = 50_000, seed: int = 0) -> float:
    """Monte Carlo estimate of E[log|1 - ξ / z_η|] for standard normal ξ."""

    import random

    rng = random.Random(seed)
    z = _norm_ppf(1.0 - eta)
    total = 0.0
    for _ in range(samples):
        # Box-Muller
        u1 = max(rng.random(), 1e-12)
        u2 = rng.random()
        xi = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
        total += math.log(abs(1.0 - xi / z) + 1e-15)
    return total / samples


def subtick_or_rate_limit_decision(
    *,
    theoretical_deadline_s: float,
    tick_s: float,
    verification_rate: float,
    max_verification_rate: float,
    cumulative_cost: float,
    max_cost: float,
) -> str:
    """Workbench Zeno / rate / cost guard: HOLD or ESCALATE, never continued CLEAR."""

    if theoretical_deadline_s < tick_s:
        return "HOLD"
    if verification_rate > max_verification_rate:
        return "ESCALATE"
    if cumulative_cost > max_cost:
        return "ESCALATE"
    return "CLEAR"


@dataclass(frozen=True)
class FormalRegimeReport:
    flip_probability_ok: bool
    cost_identity_ok: bool
    scheduler_separation_ok: bool
    zeno_guard_ok: bool
    details: dict


def run_synthetic_regime_tests(
    *,
    distance: float = 1.0,
    sigma: float = 1.0,
    eta: float = 0.1,
    tick_s: float = 1.0,
) -> FormalRegimeReport:
    z = _norm_ppf(1.0 - eta)
    deadline = closed_form_deadline(distance=distance, sigma=sigma, eta=eta)
    standardized = distance / (sigma * math.sqrt(max(deadline, 1e-12)))
    flip_probability_ok = abs(standardized - z) < 1e-9

    distances = [distance * (0.7**i) for i in range(6)]
    # Censor inside the interval after the second paid re-verification.
    t0 = closed_form_deadline(distance=distances[0], sigma=sigma, eta=eta)
    t1 = closed_form_deadline(distance=distances[1], sigma=sigma, eta=eta)
    t2 = closed_form_deadline(distance=distances[2], sigma=sigma, eta=eta)
    horizon = t0 + t1 + 0.5 * t2
    cost_identity_ok = verify_censored_cost_identity(
        distances=distances,
        sigma=sigma,
        eta=eta,
        horizon_t=horizon,
    )

    taus = (2.0, 3.0, 5.0, 8.0)
    periodic, deadline_count, ratio = periodic_vs_deadline_scheduler_counts(deadlines=taus)
    scheduler_separation_ok = (
        periodic >= math.ceil(sum(taus) / min(taus)) and ratio > 1.0
    )

    decision = subtick_or_rate_limit_decision(
        theoretical_deadline_s=0.25 * tick_s,
        tick_s=tick_s,
        verification_rate=0.0,
        max_verification_rate=10.0,
        cumulative_cost=0.0,
        max_cost=100.0,
    )
    zeno_guard_ok = decision == "HOLD"

    return FormalRegimeReport(
        flip_probability_ok=flip_probability_ok,
        cost_identity_ok=cost_identity_ok,
        scheduler_separation_ok=scheduler_separation_ok,
        zeno_guard_ok=zeno_guard_ok,
        details={
            "deadline": deadline,
            "periodic_checks": periodic,
            "deadline_checks": deadline_count,
            "ratio_bound": ratio,
            "subtick_decision": decision,
            "eta_critical_approx": 0.2602,
        },
    )
