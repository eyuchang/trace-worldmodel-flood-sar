from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from trace_jepa.util import sha256_file, sha256_value
from trace_jepa.worldmodels.contracts import RouteWorldModelRequest
from trace_jepa.worldmodels.rendering import ControlledVisualCue


ACTION_NAMES = ("dispatch_rescue_boat", "evacuate_to_safety")
TARGET_NAMES = (
    "route_success_probability",
    "arrival_time_scaled",
    "hazard_score",
    "remaining_resource_margin",
)
SPLIT_NAMES = ("train", "tuning", "calibration", "validation", "test")


@dataclass(frozen=True)
class ControlledEpisode:
    episode_id: str
    request: RouteWorldModelRequest
    cue: ControlledVisualCue
    target_by_action: dict[str, np.ndarray]
    outcome_by_action: dict[str, int]
    split: str


def _episode_split(episode_id: str, split_seed: int) -> str:
    digest = hashlib.sha256(f"{split_seed}:{episode_id}".encode()).digest()
    value = int.from_bytes(digest[:8], "big") / float(2**64)
    if value < 0.55:
        return "train"
    if value < 0.70:
        return "tuning"
    if value < 0.80:
        return "calibration"
    if value < 0.90:
        return "validation"
    return "test"


def generate_controlled_episodes(
    count: int,
    *,
    data_seed: int,
    split_seed: int,
) -> tuple[ControlledEpisode, ...]:
    """Generate controlled, episode-split route scenes and counterfactual actions."""

    if count < 4:
        raise ValueError("at least four episodes are required")
    rng = np.random.default_rng(data_seed)
    episodes: list[ControlledEpisode] = []
    for index in range(count):
        episode_id = f"jepa-route-{index + 1:05d}"
        threshold = float(rng.uniform(0.62, 0.84))
        observed_depth = float(rng.uniform(0.12, threshold * 0.95))
        rise = float(rng.uniform(0.00005, 0.00035))
        rain = float(rng.uniform(0.0, 1.0))
        inflow = float(rng.uniform(0.0, 1.0))
        travel = float(rng.uniform(240.0, 1100.0))
        susceptibility = float(rng.uniform(0.7, 1.35))
        forcing = 0.25 + 0.75 * rain + 0.85 * inflow
        projected_depth = observed_depth + rise * forcing * susceptibility * travel
        weather = float(rng.uniform(0.05, 0.9))
        sensor_noise = float(rng.uniform(0.02, 0.3))
        cue = ControlledVisualCue(
            surface_debris=float(rng.beta(2.0, 3.0)),
            flow_turbulence=float(rng.beta(2.0, 2.5)),
            visibility=float(rng.uniform(0.35, 1.0)),
            cue_seed=data_seed * 100_000 + index,
        )
        request = RouteWorldModelRequest(
            plan_id=f"{episode_id}:template",
            route_id=f"controlled-route-{index % 7}",
            asset_id=f"controlled-boat-{index % 5}",
            belief_status="open",
            belief_confidence=float(rng.uniform(0.65, 0.98)),
            observation_age_s=float(rng.uniform(0.0, 240.0)),
            observed_depth_m=observed_depth,
            projected_depth_m=projected_depth,
            route_closure_depth_m=threshold,
            route_susceptibility=susceptibility,
            travel_time_s=travel,
            water_rise_rate=rise,
            rain_intensity=rain,
            upstream_inflow=inflow,
            weather_forecast=weather,
            sensor_noise=sensor_noise,
            packet_loss=float(rng.uniform(0.0, 0.15)),
            declared_ood_severity=float(rng.uniform(0.0, 0.45)),
            sensor_quality=float(rng.uniform(0.7, 1.0)),
            asset_resource=float(rng.uniform(0.65, 1.0)),
            asset_weather_tolerance=float(rng.uniform(0.65, 0.95)),
            visual_observation_id=episode_id,
        )
        depth_risk = projected_depth / threshold
        visual_risk = 0.45 * cue.surface_debris + 0.35 * cue.flow_turbulence
        weather_risk = 0.25 * weather + 0.10 * (1.0 - cue.visibility)
        target_by_action: dict[str, np.ndarray] = {}
        outcome_by_action: dict[str, int] = {}
        for action_index, action_name in enumerate(ACTION_NAMES):
            action_risk = 0.07 if action_index == 0 else 0.13
            risk = 0.48 * depth_risk + visual_risk + weather_risk + action_risk
            success = float(1.0 / (1.0 + np.exp(6.0 * (risk - 0.92))))
            arrival = float(np.clip((travel + 150.0 * action_index) / 1800.0, 0.0, 1.5))
            hazard = float(np.clip(risk / 1.7, 0.0, 1.0))
            resource = float(
                np.clip(
                    request.asset_resource - 0.13 - 0.10 * action_index - 0.18 * risk, -1.0, 1.0
                )
            )
            target_by_action[action_name] = np.asarray(
                [success, arrival, hazard, resource], dtype=np.float32
            )
            outcome_by_action[action_name] = int(rng.random() < success)
        episodes.append(
            ControlledEpisode(
                episode_id=episode_id,
                request=request,
                cue=cue,
                target_by_action=target_by_action,
                outcome_by_action=outcome_by_action,
                split=_episode_split(episode_id, split_seed),
            )
        )
    return tuple(episodes)


def write_feature_dataset(
    path: Path,
    episodes: tuple[ControlledEpisode, ...],
    feature_by_episode: dict[str, np.ndarray],
    observation_hash_by_episode: dict[str, str],
    *,
    encoder_manifest: dict[str, object],
    include_test: bool,
    data_seed: int,
    split_seed: int,
) -> Path:
    included = [episode for episode in episodes if include_test or episode.split != "test"]
    missing = sorted({episode.episode_id for episode in included} - set(feature_by_episode))
    if missing:
        raise ValueError(f"missing cached features for episodes: {missing[:3]}")
    rows: list[tuple[ControlledEpisode, str]] = [
        (episode, action_name) for episode in included for action_name in ACTION_NAMES
    ]
    structured = np.asarray(
        [episode.request.structured_features for episode, _ in rows], dtype=np.float32
    )
    visual = np.asarray(
        [feature_by_episode[episode.episode_id] for episode, _ in rows], dtype=np.float32
    )
    actions = np.asarray(
        [ACTION_NAMES.index(action_name) for _, action_name in rows], dtype=np.int64
    )
    targets = np.asarray(
        [episode.target_by_action[action_name] for episode, action_name in rows], dtype=np.float32
    )
    outcomes = np.asarray(
        [episode.outcome_by_action[action_name] for episode, action_name in rows], dtype=np.int64
    )
    episode_ids = np.asarray([episode.episode_id for episode, _ in rows], dtype="U64")
    splits = np.asarray([episode.split for episode, _ in rows], dtype="U16")
    observation_hashes = np.asarray(
        [observation_hash_by_episode[episode.episode_id] for episode, _ in rows], dtype="U64"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        structured=structured,
        visual=visual,
        actions=actions,
        targets=targets,
        outcomes=outcomes,
        episode_ids=episode_ids,
        splits=splits,
        observation_hashes=observation_hashes,
        action_names=np.asarray(ACTION_NAMES, dtype="U64"),
        target_names=np.asarray(TARGET_NAMES, dtype="U64"),
    )
    split_episode_counts = {
        split: len({episode.episode_id for episode in included if episode.split == split})
        for split in SPLIT_NAMES
    }
    manifest = {
        "dataset_version": "controlled-route-jepa-v1",
        "dataset_sha256": sha256_file(path),
        "episode_count": len(included),
        "row_count": len(rows),
        "data_seed": data_seed,
        "split_seed": split_seed,
        "split_unit": "complete_episode",
        "split_episode_counts": split_episode_counts,
        "test_included": include_test,
        "structured_feature_count": int(structured.shape[1]),
        "visual_feature_count": int(visual.shape[1]),
        "action_names": ACTION_NAMES,
        "target_names": TARGET_NAMES,
        "encoder": encoder_manifest,
        "label_contract": (
            "controlled conditional outcomes depend on declared controller-visible telemetry, "
            "action, and visible scene cues; no dynamic simulator truth is an input"
        ),
        "limitations": (
            "synthetic controlled clips validate integration and causal channel ablations; "
            "they are not evidence of field-video generalization"
        ),
        "episode_inventory_sha256": sha256_value(
            [
                {
                    "episode_id": episode.episode_id,
                    "split": episode.split,
                    "request": episode.request.model_dump(mode="json"),
                    "cue": episode.cue.__dict__,
                }
                for episode in included
            ]
        ),
    }
    manifest_path = path.with_suffix(path.suffix + ".json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path


def load_feature_dataset(path: Path) -> tuple[dict[str, np.ndarray], dict[str, object]]:
    path = Path(path)
    manifest_path = path.with_suffix(path.suffix + ".json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["dataset_sha256"] != sha256_file(path):
        raise ValueError("feature dataset hash does not match its manifest")
    with np.load(path, allow_pickle=False) as payload:
        arrays = {name: payload[name].copy() for name in payload.files}
    episode_ids = arrays["episode_ids"].astype(str)
    splits = arrays["splits"].astype(str)
    split_by_episode: dict[str, str] = {}
    for episode_id, split in zip(episode_ids, splits, strict=True):
        previous = split_by_episode.setdefault(episode_id, split)
        if previous != split:
            raise ValueError("rows from one episode cross split boundaries")
    if set(episode_ids[splits == "test"]) and not manifest.get("test_included", False):
        raise ValueError("test rows are present but the manifest says they were excluded")
    return arrays, manifest
