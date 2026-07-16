from __future__ import annotations

import hashlib

import numpy as np


class MockVideoEncoder:
    """Deterministic laptop-safe stand-in for a frozen video encoder."""

    def __init__(self, embedding_dim: int = 32, version: str = "mock-video-v1"):
        self.embedding_dim = embedding_dim
        self.version = version

    def encode(self, payload: bytes | np.ndarray) -> np.ndarray:
        raw = payload.tobytes() if isinstance(payload, np.ndarray) else payload
        digest = hashlib.sha256(raw).digest()
        seed = int.from_bytes(digest[:8], "big", signed=False)
        rng = np.random.default_rng(seed)
        vector = rng.standard_normal(self.embedding_dim).astype(np.float32)
        norm = np.linalg.norm(vector)
        return vector / norm if norm else vector
