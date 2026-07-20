from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from trace_jepa.util import sha256_value
from trace_jepa.worldmodels.simulator_observations import validate_test_authorization


FEATURE_CACHE_SCHEMA = "simulator-route-feature-cache-v1"
_SAFE_OBSERVATION_ID = re.compile(r"^simobs-[0-9a-f]{24}$")


class FrameEncoder(Protocol):
    def encode_frames(self, frames: np.ndarray) -> np.ndarray: ...


class DeterministicSmokeEncoder:
    """Cheap plumbing-only encoder; never valid for a learned-model claim."""

    def encode_frames(self, frames: np.ndarray) -> np.ndarray:
        values = frames.astype(np.float32) / 255.0
        channel_mean = values.mean(axis=(0, 1, 2))
        channel_std = values.std(axis=(0, 1, 2))
        motion = np.abs(np.diff(values, axis=0)).mean(axis=(0, 1, 2))
        return np.concatenate([channel_mean, channel_std, motion])[None, :]


@dataclass(frozen=True)
class ObservationEncodingSummary:
    discovered: int
    encoded: int
    cache_hits: int
    skipped_audit_only: int
    skipped_test: int
    observation_ids: tuple[str, ...]


def _frames_digest(frames: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(frames).tobytes()).hexdigest()


def _load_verified_frames(root: Path, manifest: dict[str, object]) -> np.ndarray:
    observation_id = str(manifest.get("observation_id", ""))
    if not _SAFE_OBSERVATION_ID.fullmatch(observation_id):
        raise ValueError("simulator observation manifest has an unsafe identifier")
    expected_file = f"{observation_id}.npz"
    if manifest.get("frames_file") != expected_file:
        raise ValueError("simulator observation frames_file is not content-addressed")
    frames_path = root / expected_file
    if not frames_path.is_file() or frames_path.is_symlink():
        raise ValueError(f"simulator observation frames are absent or unsafe: {observation_id}")
    with np.load(frames_path, allow_pickle=False) as payload:
        required = {"frames", "observation_id", "observation_hash"}
        if required - set(payload.files):
            raise ValueError("simulator observation archive does not satisfy its schema")
        if str(payload["observation_id"].item()) != observation_id:
            raise ValueError("simulator observation archive identifier mismatch")
        if str(payload["observation_hash"].item()) != manifest.get("observation_hash"):
            raise ValueError("simulator observation archive hash mismatch")
        frames = payload["frames"].copy()
    if frames.dtype != np.uint8 or frames.ndim != 4 or frames.shape[-1] != 3:
        raise ValueError("simulator observation frames must be uint8 [T,H,W,3]")
    if list(frames.shape) != manifest.get("frame_shape"):
        raise ValueError("simulator observation frame shape mismatch")
    if str(frames.dtype) != manifest.get("frame_dtype"):
        raise ValueError("simulator observation frame dtype mismatch")
    frames_sha256 = _frames_digest(frames)
    if frames_sha256 != manifest.get("frames_sha256"):
        raise ValueError("simulator observation frame digest mismatch")
    if sha256_value(manifest.get("audit_snapshot")) != manifest.get(
        "audit_snapshot_sha256"
    ):
        raise ValueError("simulator observation audit snapshot digest mismatch")
    expected_observation_hash = sha256_value(
        {
            "snapshot_sha256": manifest.get("audit_snapshot_sha256"),
            "frames_sha256": frames_sha256,
            "shape": list(frames.shape),
            "dtype": str(frames.dtype),
        }
    )
    if expected_observation_hash != manifest.get("observation_hash"):
        raise ValueError("simulator observation content hash mismatch")
    return frames


def encode_simulator_observations(
    observation_dir: Path,
    cache_dir: Path,
    encoder: FrameEncoder,
    *,
    encoder_version: str,
    encoder_checkpoint_sha256: str,
    include_test: bool = False,
    test_authorization_manifest: Path | None = None,
    shard_index: int = 0,
    shard_count: int = 1,
) -> ObservationEncodingSummary:
    """Verify and encode captured observations without exposing raw frames online."""

    observation_dir = Path(observation_dir)
    cache_dir = Path(cache_dir)
    if not observation_dir.is_dir():
        raise ValueError("simulator observation directory does not exist")
    if shard_count < 1 or shard_index < 0 or shard_index >= shard_count:
        raise ValueError("shard_index must identify one of shard_count deterministic shards")
    if include_test:
        validate_test_authorization(test_authorization_manifest)
    cache_dir.mkdir(parents=True, exist_ok=True)

    inventory = sorted(observation_dir.glob("simobs-*.json"))
    manifests = tuple(
        path
        for position, path in enumerate(inventory)
        if position % shard_count == shard_index
    )
    encoded = 0
    cache_hits = 0
    skipped_audit_only = 0
    skipped_test = 0
    observation_ids: list[str] = []
    for manifest_path in manifests:
        if manifest_path.is_symlink():
            raise ValueError("symlinked simulator observation manifests are not accepted")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("manifest_version") != "simulator-visual-observation-v1":
            raise ValueError("unsupported simulator observation manifest version")
        observation_id = str(manifest.get("observation_id", ""))
        if manifest_path.name != f"{observation_id}.json":
            raise ValueError("simulator observation manifest filename mismatch")
        study_partition = manifest.get("study_partition")
        if study_partition not in {"development", "test"}:
            raise ValueError("simulator observation has an invalid study partition")
        if study_partition == "test" and not include_test:
            skipped_test += 1
            continue
        if not bool(manifest.get("controller_usable")):
            skipped_audit_only += 1
            continue

        frames = _load_verified_frames(observation_dir, manifest)
        cache_key = sha256_value(
            {
                "cache_schema": FEATURE_CACHE_SCHEMA,
                "encoder_version": encoder_version,
                "encoder_checkpoint_sha256": encoder_checkpoint_sha256,
                "observation_id": observation_id,
                "observation_hash": manifest["observation_hash"],
                "frames_sha256": manifest["frames_sha256"],
            }
        )
        cache_path = cache_dir / f"{observation_id}.npz"
        if cache_path.is_file() and not cache_path.is_symlink():
            with np.load(cache_path, allow_pickle=False) as cached:
                if (
                    {"cache_key", "feature", "observation_hash"} <= set(cached.files)
                    and str(cached["cache_key"].item()) == cache_key
                    and np.isfinite(cached["feature"]).all()
                ):
                    cache_hits += 1
                    observation_ids.append(observation_id)
                    continue

        feature = np.asarray(encoder.encode_frames(frames), dtype=np.float32).reshape(-1)
        if feature.size == 0 or not np.isfinite(feature).all():
            raise ValueError(f"encoder produced an invalid feature: {observation_id}")
        with tempfile.NamedTemporaryFile(
            dir=cache_dir, suffix=".npz", delete=False
        ) as handle:
            temporary_cache = Path(handle.name)
            np.savez_compressed(
                handle,
                cache_key=np.asarray(cache_key),
                feature=feature,
                observation_hash=np.asarray(manifest["observation_hash"]),
                encoder_version=np.asarray(encoder_version),
                encoder_checkpoint_sha256=np.asarray(encoder_checkpoint_sha256),
            )
            handle.flush()
            os.fsync(handle.fileno())
        temporary_cache.replace(cache_path)
        encoded += 1
        observation_ids.append(observation_id)

    return ObservationEncodingSummary(
        discovered=len(manifests),
        encoded=encoded,
        cache_hits=cache_hits,
        skipped_audit_only=skipped_audit_only,
        skipped_test=skipped_test,
        observation_ids=tuple(observation_ids),
    )
