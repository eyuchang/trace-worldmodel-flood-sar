from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from trace_jepa.util import sha256_file, sha256_value
from trace_jepa.worldmodels.dataset import ACTION_NAMES, TARGET_NAMES
from trace_jepa.worldmodels.encoding import load_verified_simulator_frames
from trace_jepa.worldmodels.simulator_observations import validate_test_authorization


def _load_observation_image(
    observation_dir: Path,
    observation_id: str,
    expected_hash: str,
    *,
    frame_index: int,
) -> np.ndarray:
    manifest_path = observation_dir / f"{observation_id}.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError(f"observation manifest is absent or unsafe: {observation_id}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("observation_hash") != expected_hash:
        raise ValueError("transition inventory and observation hash disagree")
    frames = load_verified_simulator_frames(observation_dir, manifest)
    if frame_index < 0 or frame_index >= len(frames):
        raise ValueError("state frame index is outside the captured observation")
    return frames[frame_index]


def encode_dinowm_transition_inventory(
    inventory_path: Path,
    observation_dir: Path,
    output_path: Path,
    encoder,
    *,
    encoder_manifest: dict[str, object],
    frame_index: int,
    batch_size: int = 32,
    test_authorization_manifest: Path | None = None,
) -> Path:
    """Encode verified current/next observations into spatial DINOv2 trajectories."""

    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    inventory_path = Path(inventory_path)
    payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    if payload.get("inventory_version") != "flood-sar-dinowm-transitions-v1":
        raise ValueError("unsupported DINO-WM transition inventory")
    partition = payload.get("study_partition")
    if partition == "test":
        validate_test_authorization(test_authorization_manifest)
    elif partition != "development":
        raise ValueError("transition inventory has an invalid study partition")
    rows = payload.get("transitions")
    if not isinstance(rows, list) or sha256_value(rows) != payload.get("transitions_sha256"):
        raise ValueError("transition inventory digest mismatch")

    observation_dir = Path(observation_dir)
    observation_hashes: dict[str, str] = {}
    for row in rows:
        for prefix in ("current", "next"):
            observation_id = str(row[f"{prefix}_observation_id"])
            observation_hash = str(row[f"{prefix}_observation_hash"])
            previous = observation_hashes.setdefault(observation_id, observation_hash)
            if previous != observation_hash:
                raise ValueError("one observation identifier maps to multiple hashes")

    feature_by_observation: dict[str, np.ndarray] = {}
    identifiers = sorted(observation_hashes)
    for start in range(0, len(identifiers), batch_size):
        batch_ids = identifiers[start : start + batch_size]
        images = np.asarray(
            [
                _load_observation_image(
                    observation_dir,
                    observation_id,
                    observation_hashes[observation_id],
                    frame_index=frame_index,
                )
                for observation_id in batch_ids
            ],
            dtype=np.uint8,
        )
        features = np.asarray(encoder.encode_images(images), dtype=np.float32)
        if features.ndim != 3 or len(features) != len(batch_ids):
            raise ValueError("spatial encoder returned an invalid batch")
        for observation_id, feature in zip(batch_ids, features, strict=True):
            feature_by_observation[observation_id] = feature

    current = np.asarray(
        [feature_by_observation[str(row["current_observation_id"])] for row in rows],
        dtype=np.float16,
    )
    future = np.asarray(
        [feature_by_observation[str(row["next_observation_id"])] for row in rows],
        dtype=np.float16,
    )
    structured = np.asarray([row["structured_features"] for row in rows], dtype=np.float32)
    actions = np.asarray([row["action_index"] for row in rows], dtype=np.int64)
    targets = np.asarray([row["target"] for row in rows], dtype=np.float32)
    outcomes = np.asarray([row["outcome"] for row in rows], dtype=np.int64)
    episode_ids = np.asarray([row["episode_id"] for row in rows], dtype="U64")
    splits = np.asarray([row["split"] for row in rows], dtype="U16")
    current_hashes = np.asarray(
        [row["current_observation_hash"] for row in rows], dtype="U64"
    )
    future_hashes = np.asarray(
        [row["next_observation_hash"] for row in rows], dtype="U64"
    )
    if not np.isfinite(current).all() or not np.isfinite(future).all():
        raise ValueError("encoded transition features must be finite")
    split_by_episode: dict[str, str] = {}
    for episode_id, split in zip(episode_ids.astype(str), splits.astype(str), strict=True):
        if split_by_episode.setdefault(episode_id, split) != split:
            raise ValueError("one episode crosses split boundaries")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_path,
        current_latents=current,
        next_latents=future,
        structured=structured,
        actions=actions,
        targets=targets,
        outcomes=outcomes,
        episode_ids=episode_ids,
        splits=splits,
        current_observation_hashes=current_hashes,
        next_observation_hashes=future_hashes,
        action_names=np.asarray(ACTION_NAMES, dtype="U64"),
        target_names=np.asarray(TARGET_NAMES, dtype="U64"),
    )
    manifest = {
        "dataset_version": "flood-sar-dinowm-spatial-transitions-v1",
        "dataset_sha256": sha256_file(output_path),
        "source_inventory_sha256": sha256_file(inventory_path),
        "study_partition": partition,
        "episode_count": len(set(episode_ids.astype(str))),
        "transition_count": len(rows),
        "split_unit": "complete_episode",
        "split_episode_counts": payload["split_episode_counts"],
        "data_seed": payload["data_seed"],
        "split_seed": payload["split_seed"],
        "state_frame_index": frame_index,
        "patch_count": int(current.shape[1]),
        "feature_dim": int(current.shape[2]),
        "storage_dtype": str(current.dtype),
        "encoder": encoder_manifest,
        "test_included": partition == "test",
        "test_authorization_manifest_sha256": (
            sha256_file(test_authorization_manifest)
            if partition == "test" and test_authorization_manifest is not None
            else None
        ),
    }
    manifest_path = output_path.with_suffix(output_path.suffix + ".json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    return manifest_path


def load_dinowm_transition_dataset(
    path: Path,
    *,
    allow_test: bool = False,
    test_authorization_manifest: Path | None = None,
) -> tuple[dict[str, np.ndarray], dict[str, object]]:
    path = Path(path)
    manifest = json.loads(path.with_suffix(path.suffix + ".json").read_text())
    if manifest.get("dataset_sha256") != sha256_file(path):
        raise ValueError("DINO-WM dataset hash does not match its manifest")
    if manifest.get("test_included"):
        if not allow_test:
            raise ValueError("test transition loading is disabled")
        validate_test_authorization(test_authorization_manifest)
    with np.load(path, allow_pickle=False) as payload:
        arrays = {name: payload[name].copy() for name in payload.files}
    required = {
        "current_latents",
        "next_latents",
        "structured",
        "actions",
        "targets",
        "outcomes",
        "episode_ids",
        "splits",
        "action_names",
    }
    if required - arrays.keys():
        raise ValueError("DINO-WM transition dataset is incomplete")
    if arrays["current_latents"].shape != arrays["next_latents"].shape:
        raise ValueError("current and next latent shapes differ")
    episode_ids = arrays["episode_ids"].astype(str)
    splits = arrays["splits"].astype(str)
    split_by_episode: dict[str, str] = {}
    for episode_id, split in zip(episode_ids, splits, strict=True):
        if split_by_episode.setdefault(episode_id, split) != split:
            raise ValueError("one episode crosses split boundaries")
    return arrays, manifest
