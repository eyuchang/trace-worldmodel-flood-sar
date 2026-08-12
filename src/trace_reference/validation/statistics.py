"""Deterministic seed-cluster intervals without call-level pseudoreplication."""

from __future__ import annotations

import hashlib
import math
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel


class ReferenceSeedMetric(DeltaModel):
    """One fixed-point mission-level value; a mission seed is the sampling unit."""

    seed: int = Field(ge=0, le=2_147_483_647)
    value_micros: int


class ReferenceClusterInterval(DeltaModel):
    """One deterministic fixed-point interval over mission-level clusters."""

    schema_version: Literal["delta-reference-cluster-interval-v1"]
    metric_name: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    method: Literal[
        "deterministic-cluster-bootstrap-percentile-v1",
        "exact-binomial-order-statistic-median-v1",
    ]
    cluster_count: int = Field(ge=2)
    resample_count: int | None = Field(default=None, ge=1_000, le=100_000)
    point_micros: int
    lower_micros: int
    upper_micros: int
    nominal_coverage_micros: int = Field(ge=500_000, le=999_999)
    achieved_coverage_micros: int | None = Field(default=None, ge=500_000, le=1_000_000)
    randomness_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_interval(self) -> ReferenceClusterInterval:
        if not self.lower_micros <= self.point_micros <= self.upper_micros:
            raise ValueError("Reference interval does not contain its point estimate")
        bootstrap = self.method == "deterministic-cluster-bootstrap-percentile-v1"
        if bootstrap != (self.resample_count is not None and self.randomness_sha256 is not None):
            raise ValueError("Reference bootstrap interval lacks exact randomness provenance")
        if bootstrap == (self.achieved_coverage_micros is not None):
            raise ValueError("Only the exact median interval reports achieved coverage")
        return self


def _canonical_metrics(values: tuple[ReferenceSeedMetric, ...]) -> tuple[ReferenceSeedMetric, ...]:
    ordered = tuple(sorted(values, key=lambda item: item.seed))
    seeds = tuple(item.seed for item in ordered)
    if len(ordered) < 2:
        raise ValueError("Reference seed-cluster inference requires at least two missions")
    if len(set(seeds)) != len(seeds):
        raise ValueError("Reference seed-cluster inference received a duplicate mission seed")
    return ordered


def _round_ratio(numerator: int, denominator: int) -> int:
    sign = -1 if numerator < 0 else 1
    absolute = abs(numerator)
    quotient, remainder = divmod(absolute, denominator)
    return sign * (quotient + int(2 * remainder >= denominator))


def _uniform_index(namespace: bytes, counter: int, size: int) -> int:
    modulus = 1 << 64
    limit = modulus - (modulus % size)
    nonce = 0
    while True:
        digest = hashlib.sha256(
            namespace + b"|" + str(counter).encode("ascii") + b"|" + str(nonce).encode("ascii")
        ).digest()
        candidate = int.from_bytes(digest[:8], "big")
        if candidate < limit:
            return candidate % size
        nonce += 1


def cluster_bootstrap_mean_interval(
    values: tuple[ReferenceSeedMetric, ...],
    *,
    protocol_hash: str,
    metric_name: str,
    resample_count: int = 10_000,
    coverage_micros: int = 950_000,
) -> ReferenceClusterInterval:
    """Return a deterministic percentile interval over whole mission clusters."""

    if len(protocol_hash) != 64 or any(item not in "0123456789abcdef" for item in protocol_hash):
        raise ValueError("Reference bootstrap protocol hash must be lowercase SHA-256")
    if not 1_000 <= resample_count <= 100_000:
        raise ValueError("Reference bootstrap resample count is outside the registered bounds")
    if not 500_000 <= coverage_micros <= 999_999:
        raise ValueError("Reference bootstrap coverage is outside the supported bounds")
    ordered = _canonical_metrics(values)
    namespace = f"{protocol_hash}|{metric_name}|cluster-bootstrap-v1".encode()
    randomness_sha256 = hashlib.sha256(namespace).hexdigest()
    size = len(ordered)
    estimates = []
    draw = 0
    for _ in range(resample_count):
        total = 0
        for _ in range(size):
            total += ordered[_uniform_index(namespace, draw, size)].value_micros
            draw += 1
        estimates.append(_round_ratio(total, size))
    estimates.sort()
    tail_micros = (1_000_000 - coverage_micros) // 2
    lower_rank = (tail_micros * resample_count + 999_999) // 1_000_000
    lower_index = max(0, lower_rank - 1)
    upper_rank = ((1_000_000 - tail_micros) * resample_count + 999_999) // 1_000_000
    upper_index = min(resample_count - 1, upper_rank - 1)
    return ReferenceClusterInterval(
        schema_version="delta-reference-cluster-interval-v1",
        metric_name=metric_name,
        method="deterministic-cluster-bootstrap-percentile-v1",
        cluster_count=size,
        resample_count=resample_count,
        point_micros=_round_ratio(sum(item.value_micros for item in ordered), size),
        lower_micros=estimates[lower_index],
        upper_micros=estimates[upper_index],
        nominal_coverage_micros=coverage_micros,
        randomness_sha256=randomness_sha256,
    )


def exact_median_interval(
    values: tuple[ReferenceSeedMetric, ...],
    *,
    metric_name: str,
    coverage_micros: int = 950_000,
) -> ReferenceClusterInterval:
    """Return the widest central exact binomial order-statistic interval."""

    if not 500_000 <= coverage_micros <= 999_999:
        raise ValueError("Reference median coverage is outside the supported bounds")
    ordered = _canonical_metrics(values)
    samples = sorted(item.value_micros for item in ordered)
    size = len(samples)
    alpha_micros = 1_000_000 - coverage_micros
    denominator = 2**size
    lower_order = 1
    for candidate in range(1, size // 2 + 1):
        tail_numerator = sum(math.comb(size, index) for index in range(candidate))
        if 2 * tail_numerator * 1_000_000 <= alpha_micros * denominator:
            lower_order = candidate
        else:
            break
    lower = samples[lower_order - 1]
    upper = samples[size - lower_order]
    tail_numerator = sum(math.comb(size, index) for index in range(lower_order))
    achieved = _round_ratio(
        (denominator - 2 * tail_numerator) * 1_000_000,
        denominator,
    )
    middle = size // 2
    point = samples[middle] if size % 2 else _round_ratio(samples[middle - 1] + samples[middle], 2)
    return ReferenceClusterInterval(
        schema_version="delta-reference-cluster-interval-v1",
        metric_name=metric_name,
        method="exact-binomial-order-statistic-median-v1",
        cluster_count=size,
        point_micros=point,
        lower_micros=lower,
        upper_micros=upper,
        nominal_coverage_micros=coverage_micros,
        achieved_coverage_micros=achieved,
    )
