from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass


def derive_stage_seed(root_seed: int, parameter_hash: str, stage_name: str) -> int:
    payload = f"{root_seed}:{parameter_hash}:{stage_name}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], byteorder="big")


def seeded_random(root_seed: int, parameter_hash: str, stage_name: str) -> random.Random:
    return random.Random(derive_stage_seed(root_seed, parameter_hash, stage_name))


def sample_poisson(rng: random.Random, rate: float) -> int:
    if rate < 0.0:
        raise ValueError("Poisson rate must be non-negative")
    if rate == 0.0:
        return 0
    threshold = math.exp(-rate)
    product = 1.0
    count = 0
    while product > threshold:
        count += 1
        product *= rng.random()
    return count - 1


@dataclass(frozen=True)
class KeyedRandom:
    """Order-independent SHA-256 random variates for causal axis comparisons.

    Each scientific candidate has an explicit semantic key. Adding, removing, or
    accepting another candidate therefore cannot shift the random realization of
    unrelated candidates, which is the common-random-numbers property required by
    the v7 protocol.
    """

    root_seed: int
    parameter_hash: str
    stage_name: str

    def _digest(self, *key: object) -> bytes:
        components = [
            str(self.root_seed),
            self.parameter_hash,
            self.stage_name,
            *(str(item) for item in key),
        ]
        return hashlib.sha256("\x1f".join(components).encode("utf-8")).digest()

    def uniform(self, *key: object) -> float:
        return int.from_bytes(self._digest(*key)[:8], "big") / 2**64

    def randint(self, lower: int, upper: int, *key: object) -> int:
        if upper < lower:
            raise ValueError("upper bound must be at least the lower bound")
        width = upper - lower + 1
        return lower + int.from_bytes(self._digest(*key)[:8], "big") % width

    def choice_index(self, length: int, *key: object) -> int:
        if length <= 0:
            raise ValueError("choice length must be positive")
        return self.randint(0, length - 1, *key)

    def bernoulli(self, probability: float, *key: object) -> bool:
        if not 0.0 <= probability <= 1.0:
            raise ValueError("Bernoulli probability must be between zero and one")
        return self.uniform(*key) < probability

    def poisson(self, rate: float, *key: object) -> int:
        if rate < 0.0:
            raise ValueError("Poisson rate must be non-negative")
        if rate == 0.0:
            return 0
        threshold = math.exp(-rate)
        product = 1.0
        count = 0
        while product > threshold:
            product *= self.uniform(*key, "poisson", count)
            count += 1
        return count - 1
