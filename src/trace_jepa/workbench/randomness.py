from __future__ import annotations

import hashlib
import math
import struct
from enum import Enum
from typing import Final


RNG_SCHEMA_VERSION: Final = "trace-active-refresh-rng-v1"
SEED_NAMESPACE: Final = "active-refresh-day1-v1"


def _encode_part(value: object) -> bytes:
    """Encode one RNG-key component without type or delimiter ambiguity."""

    if isinstance(value, Enum):
        value = value.value
    if value is None:
        return b"n"
    if isinstance(value, bool):
        return b"b1" if value else b"b0"
    if isinstance(value, int):
        return b"i" + str(value).encode("ascii")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("RNG keys require finite floating-point values")
        return b"f" + value.hex().encode("ascii")
    if isinstance(value, bytes):
        return b"y" + value
    if isinstance(value, str):
        return b"s" + value.encode("utf-8")
    raise TypeError(f"unsupported RNG key type: {type(value).__name__}")


def _key_bytes(namespace: str, *parts: object) -> bytes:
    if not namespace or not namespace.isascii():
        raise ValueError("RNG namespace must be a non-empty ASCII string")
    encoded = [_encode_part(RNG_SCHEMA_VERSION), _encode_part(namespace)]
    encoded.extend(_encode_part(part) for part in parts)
    return b"".join(struct.pack(">I", len(part)) + part for part in encoded)


def keyed_uniform(namespace: str, *parts: object) -> float:
    """Return a deterministic uniform variate strictly inside ``(0, 1)``."""

    digest = hashlib.sha256(_key_bytes(namespace, *parts)).digest()
    integer = int.from_bytes(digest[:8], "big")
    return (integer + 0.5) / float(1 << 64)


def keyed_standard_normal(namespace: str, *parts: object) -> float:
    """Return a deterministic standard normal using a keyed Box--Muller draw."""

    u1 = keyed_uniform(namespace, *parts, "box_muller_radius")
    u2 = keyed_uniform(namespace, *parts, "box_muller_angle")
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
