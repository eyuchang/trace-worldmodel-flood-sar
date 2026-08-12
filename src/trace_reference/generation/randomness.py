"""Keyed deterministic draws shared by Reference generation stages."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from functools import lru_cache


def _append_encoded(payload: bytearray, value: object) -> None:
    encoded = str(value).encode("utf-8")
    payload.extend(len(encoded).to_bytes(8, "big"))
    payload.extend(encoded)


@lru_cache(maxsize=1_024)
def _prefix(seed: int, namespace: str) -> bytes:
    payload = bytearray()
    for value in ("WF-DFLD-01-REFERENCE", namespace, seed):
        _append_encoded(payload, value)
    return bytes(payload)


def keyed_digest(seed: int, namespace: str, *parts: object) -> bytes:
    """Return a stable digest without relying on process-global RNG state."""

    if seed < 0:
        raise ValueError("Reference generation seeds must be nonnegative")
    payload = bytearray(_prefix(seed, namespace))
    for value in parts:
        _append_encoded(payload, value)
    return hashlib.sha256(payload).digest()


def uniform_micros(seed: int, namespace: str, *parts: object) -> int:
    """Map a keyed digest to an integer draw in the half-open range [0, 1e6)."""

    return int.from_bytes(keyed_digest(seed, namespace, *parts)[:8], "big") % 1_000_000


def uniform_fraction(seed: int, namespace: str, *parts: object) -> float:
    """Return a deterministic open-interval fraction suitable for transforms."""

    value = int.from_bytes(keyed_digest(seed, namespace, *parts)[:8], "big")
    return (value + 0.5) / (2**64)


def standard_normal(seed: int, namespace: str, *parts: object) -> float:
    """Return one Box-Muller standard-normal draw from two keyed uniforms."""

    first = uniform_fraction(seed, namespace, *parts, "normal-u1")
    second = uniform_fraction(seed, namespace, *parts, "normal-u2")
    return math.sqrt(-2.0 * math.log(first)) * math.cos(2.0 * math.pi * second)


def digest_order(
    seed: int, namespace: str, values: Iterable[str], *parts: object
) -> tuple[str, ...]:
    """Return values in deterministic pseudorandom order without mutable shuffling."""

    return tuple(sorted(values, key=lambda value: keyed_digest(seed, namespace, *parts, value)))
