"""Exact fixed-point probability arithmetic shared by Reference truth paths."""

from __future__ import annotations

_PROBABILITY_DENOMINATOR = 10**24


def probability_micros(intercept_micros: int, factor: int) -> int:
    """Use integer half-up rounding for auditable fixed-point probabilities."""

    rounded = (intercept_micros * factor + _PROBABILITY_DENOMINATOR // 2) // (
        _PROBABILITY_DENOMINATOR
    )
    return min(1_000_000, rounded)


def minimum_accepting_intercept(draw_micros: int, factor: int) -> int:
    """Invert the fixed-point probability exactly for one keyed draw."""

    required = (draw_micros + 1) * _PROBABILITY_DENOMINATOR - _PROBABILITY_DENOMINATOR // 2
    return max(0, (required + factor - 1) // factor)
