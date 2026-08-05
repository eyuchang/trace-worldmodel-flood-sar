from __future__ import annotations

import hashlib
import math
import random


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
