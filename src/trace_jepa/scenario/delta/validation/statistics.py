"""Deterministic seed-cluster inference used by registered Delta studies."""

from __future__ import annotations

import hashlib
import math
import random
import statistics
from collections.abc import Sequence

BOOTSTRAP_RESAMPLES = 10_000


def _bootstrap_rng(protocol_hash: str, metric_name: str) -> random.Random:
    digest = hashlib.sha256(f"{protocol_hash}|{metric_name}|cluster-bootstrap-v1".encode()).digest()
    return random.Random(int.from_bytes(digest[:16], "big"))


def _percentile_interval(samples: list[float]) -> tuple[float, float]:
    ordered = sorted(samples)
    return ordered[249], ordered[9_749]


def cluster_mean_interval(
    values: Sequence[float], protocol_hash: str, metric_name: str
) -> dict[str, object]:
    if not values:
        raise ValueError(f"cluster interval requires at least one value: {metric_name}")
    rng = _bootstrap_rng(protocol_hash, metric_name)
    size = len(values)
    samples = [
        statistics.fmean(values[rng.randrange(size)] for _ in range(size))
        for _ in range(BOOTSTRAP_RESAMPLES)
    ]
    lower, upper = _percentile_interval(samples)
    return {
        "estimate": statistics.fmean(values),
        "lower_95": lower,
        "upper_95": upper,
        "method": "deterministic-seed-cluster-percentile-bootstrap-10000-v1",
        "bootstrap_seed_derivation": (
            f"sha256({protocol_hash}|{metric_name}|cluster-bootstrap-v1)"
        ),
    }


def cluster_fraction_interval(
    counts: Sequence[tuple[int, int]], protocol_hash: str, metric_name: str
) -> dict[str, object]:
    if not counts or sum(denominator for _numerator, denominator in counts) == 0:
        raise ValueError(f"cluster fraction requires a positive denominator: {metric_name}")
    rng = _bootstrap_rng(protocol_hash, metric_name)
    size = len(counts)
    samples: list[float] = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        selected = [counts[rng.randrange(size)] for _index in range(size)]
        denominator = sum(item[1] for item in selected)
        samples.append(sum(item[0] for item in selected) / denominator if denominator else 0.0)
    lower, upper = _percentile_interval(samples)
    denominator = sum(item[1] for item in counts)
    return {
        "estimate": sum(item[0] for item in counts) / denominator,
        "lower_95": lower,
        "upper_95": upper,
        "method": "deterministic-seed-cluster-ratio-bootstrap-10000-v1",
        "cluster_count": len(counts),
        "bootstrap_seed_derivation": (
            f"sha256({protocol_hash}|{metric_name}|cluster-bootstrap-v1)"
        ),
    }


def exact_median_interval(values: Sequence[float]) -> dict[str, object]:
    if not values:
        raise ValueError("median interval requires at least one value")
    ordered = sorted(values)
    size = len(ordered)
    cumulative = 0.0
    tail_index = -1
    for successes in range(size + 1):
        cumulative += math.comb(size, successes) * (0.5**size)
        if cumulative <= 0.025:
            tail_index = successes
        else:
            break
    lower_index = max(0, tail_index)
    upper_index = min(size - 1, size - tail_index - 1)
    return {
        "estimate": statistics.median(ordered),
        "lower_95": ordered[lower_index],
        "upper_95": ordered[upper_index],
        "method": "exact-binomial-order-statistic-median-95-v1",
        "lower_order_statistic_one_based": lower_index + 1,
        "upper_order_statistic_one_based": upper_index + 1,
    }
