from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import numpy as np

from trace_jepa.util import sha256_file, sha256_value
from trace_jepa.worldmodels.dinowm import load_dinowm_checkpoint
from trace_jepa.worldmodels.dinowm_io import load_dinowm_transition_dataset


def _predict(model, current: np.ndarray, actions: np.ndarray, batch_size: int) -> np.ndarray:
    import torch

    predictions: list[np.ndarray] = []
    model.eval()
    with torch.inference_mode():
        for start in range(0, len(current), batch_size):
            current_batch = torch.from_numpy(
                current[start : start + batch_size].astype(np.float32)
            )
            action_batch = torch.from_numpy(
                actions[start : start + batch_size].astype(np.int64)
            )
            predictions.append(
                model(current_batch, action_batch).cpu().numpy().astype(np.float32)
            )
    return np.concatenate(predictions, axis=0)


def build_dinowm_action_feature_cache(
    inventory_path: Path,
    transition_dataset_path: Path,
    dynamics_checkpoint_path: Path,
    cache_dir: Path,
    *,
    encoder_version: str,
    encoder_checkpoint_sha256: str,
    batch_size: int = 8,
) -> Path:
    """Materialize action-conditioned future features for the TRACE runtime seam."""

    inventory = json.loads(Path(inventory_path).read_text())
    rows = inventory.get("transitions")
    if not isinstance(rows, list) or sha256_value(rows) != inventory.get(
        "transitions_sha256"
    ):
        raise ValueError("DINO-WM transition inventory digest mismatch")
    arrays, dataset_manifest = load_dinowm_transition_dataset(
        transition_dataset_path
    )
    if len(rows) != len(arrays["actions"]):
        raise ValueError("transition inventory and encoded dataset lengths differ")
    for index, row in enumerate(rows):
        if row["episode_id"] != str(arrays["episode_ids"][index]):
            raise ValueError("transition inventory and encoded dataset order differ")
        if row["action_index"] != int(arrays["actions"][index]):
            raise ValueError("transition action order differs")
        if row["current_observation_hash"] != str(
            arrays["current_observation_hashes"][index]
        ):
            raise ValueError("transition observation hashes differ")

    model, _, metadata = load_dinowm_checkpoint(dynamics_checkpoint_path)
    if metadata["training_dataset_sha256"] != dataset_manifest["dataset_sha256"]:
        raise ValueError("DINO-WM checkpoint was trained on a different transition dataset")
    predictions = _predict(
        model,
        arrays["current_latents"],
        arrays["actions"],
        batch_size,
    ).mean(axis=1)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_inventory: list[dict[str, str]] = []
    for row, feature in zip(rows, predictions, strict=True):
        observation_id = str(row["current_observation_id"])
        action_type = str(row["action_name"])
        cache_id = f"{observation_id}--{action_type}"
        destination = cache_dir / f"{cache_id}.npz"
        with tempfile.NamedTemporaryFile(
            dir=cache_dir, suffix=".npz", delete=False
        ) as handle:
            temporary = Path(handle.name)
            np.savez_compressed(
                handle,
                feature=feature.astype(np.float32),
                observation_hash=np.asarray(row["current_observation_hash"]),
                action_type=np.asarray(action_type),
                encoder_version=np.asarray(encoder_version),
                encoder_checkpoint_sha256=np.asarray(encoder_checkpoint_sha256),
            )
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(destination)
        cache_inventory.append(
            {
                "cache_id": cache_id,
                "cache_file_sha256": sha256_file(destination),
                "observation_hash": str(row["current_observation_hash"]),
                "action_type": action_type,
            }
        )
    manifest = {
        "cache_schema": "flood-sar-dinowm-action-feature-cache-v1",
        "entry_count": len(cache_inventory),
        "transition_dataset_sha256": dataset_manifest["dataset_sha256"],
        "dynamics_checkpoint_sha256": sha256_file(dynamics_checkpoint_path),
        "encoder_version": encoder_version,
        "encoder_checkpoint_sha256": encoder_checkpoint_sha256,
        "cache_inventory_sha256": sha256_value(cache_inventory),
        "entries": cache_inventory,
    }
    manifest_path = cache_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    return manifest_path
