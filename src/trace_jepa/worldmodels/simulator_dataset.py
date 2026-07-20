from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from trace_jepa.util import sha256_file, sha256_value
from trace_jepa.worldmodels.contracts import RouteWorldModelRequest
from trace_jepa.worldmodels.dataset import ACTION_NAMES, TARGET_NAMES
from trace_jepa.worldmodels.simulator_observations import (
    SimulatorSensorSnapshot,
    SimulatorVisualObservationStore,
)


DEVELOPMENT_SPLITS = ("train", "tuning", "calibration", "validation")


@dataclass(frozen=True)
class SimulatorDevelopmentEpisode:
    episode_id: str
    split: str
    request: RouteWorldModelRequest
    snapshot: SimulatorSensorSnapshot
    target_by_action: dict[str, np.ndarray]
    outcome_by_action: dict[str, int]
    observation_hash: str | None = None


def _development_split(episode_id: str, split_seed: int) -> str:
    value = int.from_bytes(
        hashlib.sha256(f"{split_seed}:{episode_id}".encode()).digest()[:8], "big"
    ) / float(2**64)
    if value < 0.55:
        return "train"
    if value < 0.70:
        return "tuning"
    if value < 0.85:
        return "calibration"
    return "validation"


def generate_simulator_development_episodes(
    count: int,
    *,
    data_seed: int,
    split_seed: int,
) -> tuple[SimulatorDevelopmentEpisode, ...]:
    """Generate independent development episodes from the declared flood dynamics.

    The image renderer receives the synchronized latent sensor snapshot. The model
    request receives only the categorical report and declared controller-visible
    parameters. Labels are computed from the same zero-process-noise water update
    used by the workbench, at each action's arrival horizon.
    """

    if count < 40:
        raise ValueError("at least 40 episodes are required for all development splits")
    rng = np.random.default_rng(data_seed)
    episodes: list[SimulatorDevelopmentEpisode] = []
    for index in range(count):
        episode_id = f"sim-development-{index + 1:05d}"
        threshold = float(rng.uniform(0.58, 0.88))
        water_depth = float(rng.uniform(0.12, threshold * 1.08))
        debris_blocked = bool(rng.random() < 0.22)
        rain = float(rng.uniform(0.0, 1.0))
        inflow = float(rng.uniform(0.0, 1.0))
        rise = float(rng.uniform(0.00004, 0.00038))
        susceptibility = float(rng.uniform(0.72, 1.32))
        travel = float(rng.uniform(240.0, 1080.0))
        weather = float(rng.uniform(0.05, 0.92))
        sensor_noise = float(rng.uniform(0.02, 0.30))
        sensor_quality = float(rng.uniform(0.68, 1.0))
        packet_loss = float(rng.uniform(0.0, 0.15))
        report_accuracy = float(rng.uniform(0.78, 0.98))
        actual_open = water_depth < threshold and not debris_blocked
        accurate = bool(rng.random() <= report_accuracy)
        report_open = actual_open if accurate else not actual_open
        report_status = "open" if report_open else "blocked"
        observed_at = float(rng.uniform(0.0, 600.0))
        asset_resource = float(rng.uniform(0.65, 1.0))
        asset_tolerance = float(rng.uniform(0.62, 0.96))
        forcing = 0.25 + 0.75 * rain + 0.85 * inflow
        # The structured forecast starts from a declared status-conditioned prior,
        # never from the latent water depth used to render and adjudicate the clip.
        prior_depth = threshold * (0.62 if report_open else 0.92)
        projected_depth = prior_depth + rise * forcing * susceptibility * travel
        snapshot = SimulatorSensorSnapshot(
            run_id=f"campaign-{data_seed}",
            episode_id=episode_id,
            route_id=f"sim-route-{index % 7}",
            asset_id=f"survey-drone-{index % 5}",
            observed_at=observed_at,
            environment_tick_index=int(observed_at),
            sensor_seed=data_seed * 100_000 + index,
            water_depth_m=water_depth,
            route_closure_depth_m=threshold,
            debris_blocked=debris_blocked,
            rain_intensity=rain,
            upstream_inflow=inflow,
            weather_severity=weather,
            sensor_noise=sensor_noise,
            sensor_quality=sensor_quality,
            # This benchmark is explicitly conditional on delivered evidence.
            # Packet loss remains a controller input and is evaluated elsewhere.
            packet_delivered=True,
            categorical_report_accurate=accurate,
        )
        request = RouteWorldModelRequest(
            plan_id=f"{episode_id}:template",
            route_id=snapshot.route_id,
            asset_id=f"rescue-boat-{index % 5}",
            belief_status=report_status,
            belief_confidence=report_accuracy * sensor_quality,
            observation_age_s=0.0,
            observed_depth_m=None,
            projected_depth_m=projected_depth,
            route_closure_depth_m=threshold,
            route_susceptibility=susceptibility,
            travel_time_s=travel,
            water_rise_rate=rise,
            rain_intensity=rain,
            upstream_inflow=inflow,
            weather_forecast=weather,
            sensor_noise=sensor_noise,
            packet_loss=packet_loss,
            declared_ood_severity=float(rng.uniform(0.0, 0.45)),
            sensor_quality=sensor_quality,
            asset_resource=asset_resource,
            asset_weather_tolerance=asset_tolerance,
        )
        target_by_action: dict[str, np.ndarray] = {}
        outcome_by_action: dict[str, int] = {}
        for action_index, action_name in enumerate(ACTION_NAMES):
            action_travel = travel + 180.0 * action_index
            future_depth = (
                water_depth + rise * forcing * susceptibility * action_travel
            )
            route_succeeds = future_depth < threshold and not debris_blocked
            hazard = float(
                np.clip(
                    0.72 * (future_depth / threshold)
                    + 0.22 * float(debris_blocked)
                    + 0.13 * weather
                    + 0.04 * action_index,
                    0.0,
                    1.0,
                )
            )
            remaining_resource = float(
                np.clip(
                    asset_resource
                    - action_travel * (0.00018 + 0.00005 * action_index)
                    - 0.04 * max(0.0, weather - asset_tolerance),
                    -1.0,
                    1.0,
                )
            )
            outcome = int(route_succeeds and remaining_resource > 0.0)
            target_by_action[action_name] = np.asarray(
                [
                    float(outcome),
                    action_travel / 1800.0,
                    hazard,
                    remaining_resource,
                ],
                dtype=np.float32,
            )
            outcome_by_action[action_name] = outcome
        episodes.append(
            SimulatorDevelopmentEpisode(
                episode_id=episode_id,
                split=_development_split(episode_id, split_seed),
                request=request,
                snapshot=snapshot,
                target_by_action=target_by_action,
                outcome_by_action=outcome_by_action,
            )
        )
    split_counts = {
        split: sum(episode.split == split for episode in episodes)
        for split in DEVELOPMENT_SPLITS
    }
    if any(count == 0 for count in split_counts.values()):
        raise ValueError(f"deterministic development split is empty: {split_counts}")
    return tuple(episodes)


def capture_simulator_development_episodes(
    episodes: tuple[SimulatorDevelopmentEpisode, ...],
    store: SimulatorVisualObservationStore,
) -> tuple[SimulatorDevelopmentEpisode, ...]:
    captured_episodes: list[SimulatorDevelopmentEpisode] = []
    for episode in episodes:
        captured = store.capture(episode.snapshot)
        if not captured.controller_usable:
            raise ValueError("development campaign unexpectedly produced audit-only imagery")
        captured_episodes.append(
            SimulatorDevelopmentEpisode(
                episode_id=episode.episode_id,
                split=episode.split,
                request=episode.request.model_copy(
                    update={
                        "visual_observation_id": captured.observation_id,
                        "visual_observation_age_s": 0.0,
                    }
                ),
                snapshot=episode.snapshot,
                target_by_action=episode.target_by_action,
                outcome_by_action=episode.outcome_by_action,
                observation_hash=captured.observation_hash,
            )
        )
    return tuple(captured_episodes)


def write_simulator_feature_dataset(
    path: Path,
    episodes: tuple[SimulatorDevelopmentEpisode, ...],
    cache_dir: Path,
    *,
    encoder_manifest: dict[str, object],
    data_seed: int,
    split_seed: int,
) -> Path:
    """Join verified offline features to episode-level requests and outcomes."""

    rows = [(episode, action) for episode in episodes for action in ACTION_NAMES]
    feature_by_observation: dict[str, np.ndarray] = {}
    for episode in episodes:
        observation_id = episode.request.visual_observation_id
        if observation_id is None or episode.observation_hash is None:
            raise ValueError("episode has not been captured")
        cache_path = Path(cache_dir) / f"{observation_id}.npz"
        if not cache_path.is_file():
            raise ValueError(f"missing encoded feature: {observation_id}")
        with np.load(cache_path, allow_pickle=False) as payload:
            if str(payload["observation_hash"].item()) != episode.observation_hash:
                raise ValueError("feature and captured observation hash mismatch")
            feature = payload["feature"].astype(np.float32)
        if feature.ndim != 1 or not np.isfinite(feature).all():
            raise ValueError("cached simulator feature is invalid")
        feature_by_observation[observation_id] = feature

    structured = np.asarray(
        [episode.request.structured_features for episode, _ in rows], dtype=np.float32
    )
    visual = np.asarray(
        [feature_by_observation[str(episode.request.visual_observation_id)] for episode, _ in rows],
        dtype=np.float32,
    )
    actions = np.asarray(
        [ACTION_NAMES.index(action) for _, action in rows], dtype=np.int64
    )
    targets = np.asarray(
        [episode.target_by_action[action] for episode, action in rows], dtype=np.float32
    )
    outcomes = np.asarray(
        [episode.outcome_by_action[action] for episode, action in rows], dtype=np.int64
    )
    episode_ids = np.asarray([episode.episode_id for episode, _ in rows], dtype="U64")
    splits = np.asarray([episode.split for episode, _ in rows], dtype="U16")
    observation_hashes = np.asarray(
        [str(episode.observation_hash) for episode, _ in rows], dtype="U64"
    )
    path = Path(path)
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
    split_counts = {
        split: sum(episode.split == split for episode in episodes)
        for split in DEVELOPMENT_SPLITS
    }
    manifest = {
        "dataset_version": "synchronized-flood-simulator-jepa-development-v1",
        "dataset_sha256": sha256_file(path),
        "episode_count": len(episodes),
        "row_count": len(rows),
        "data_seed": data_seed,
        "split_seed": split_seed,
        "split_unit": "complete_episode",
        "split_episode_counts": split_counts,
        "study_partition": "development",
        "test_generated": False,
        "test_included": False,
        "structured_feature_count": int(structured.shape[1]),
        "visual_feature_count": int(visual.shape[1]),
        "action_names": ACTION_NAMES,
        "target_names": TARGET_NAMES,
        "encoder": encoder_manifest,
        "observation_source": "flood-sim-drone-rgb-v2",
        "observation_condition": "conditional_on_delivered_drone_evidence",
        "label_contract": (
            "zero-process-noise workbench water update evaluated at each action arrival; "
            "latent depth and debris adjudicate labels but are absent from structured inputs"
        ),
        "limitations": (
            "simulator imagery tests synchronized integration and visual channel value; "
            "it does not establish field-video generalization or operational safety"
        ),
        "episode_inventory_sha256": sha256_value(
            [
                {
                    "episode_id": episode.episode_id,
                    "split": episode.split,
                    "request": episode.request.model_dump(mode="json"),
                    "snapshot_sha256": sha256_value(
                        episode.snapshot.model_dump(mode="json")
                    ),
                    "targets": {
                        action: episode.target_by_action[action].tolist()
                        for action in ACTION_NAMES
                    },
                    "outcomes": episode.outcome_by_action,
                    "observation_hash": episode.observation_hash,
                }
                for episode in episodes
            ]
        ),
    }
    manifest_path = path.with_suffix(path.suffix + ".json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    return manifest_path
