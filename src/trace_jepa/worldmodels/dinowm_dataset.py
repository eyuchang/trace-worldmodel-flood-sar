from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from trace_jepa.util import sha256_value
from trace_jepa.worldmodels.dataset import ACTION_NAMES
from trace_jepa.worldmodels.simulator_dataset import (
    SimulatorDevelopmentEpisode,
    generate_simulator_development_episodes,
)
from trace_jepa.worldmodels.simulator_observations import (
    CapturedVisualObservation,
    SimulatorSensorSnapshot,
    SimulatorVisualObservationStore,
    validate_test_authorization,
)


@dataclass(frozen=True)
class DINOWMTransition:
    """One action-conditioned simulator transition at the episode split unit."""

    episode: SimulatorDevelopmentEpisode
    action_name: str
    action_index: int
    current_snapshot: SimulatorSensorSnapshot
    next_snapshot: SimulatorSensorSnapshot
    current_observation: CapturedVisualObservation | None = None
    next_observation: CapturedVisualObservation | None = None

    @property
    def split(self) -> str:
        return self.episode.split


def _future_snapshot(
    episode: SimulatorDevelopmentEpisode,
    action_name: str,
    action_index: int,
    *,
    study_partition: str,
) -> SimulatorSensorSnapshot:
    request = episode.request
    action_travel_s = float(episode.target_by_action[action_name][1] * 1800.0)
    forcing = 0.25 + 0.75 * request.rain_intensity + 0.85 * request.upstream_inflow
    future_depth = (
        episode.snapshot.water_depth_m
        + request.water_rise_rate
        * forcing
        * request.route_susceptibility
        * action_travel_s
    )
    observed_at = episode.snapshot.observed_at + action_travel_s
    return episode.snapshot.model_copy(
        update={
            "study_partition": study_partition,
            "observed_at": observed_at,
            "environment_tick_index": int(observed_at),
            "water_depth_m": future_depth,
            # Keep the sensor stream coupled within an episode while making the
            # action horizon explicit in the deterministic observation hash.
            "sensor_seed": episode.snapshot.sensor_seed + 10_000 * (action_index + 1),
        }
    )


def generate_dinowm_transitions(
    count: int,
    *,
    data_seed: int,
    split_seed: int,
    study_partition: str = "development",
    test_authorization_manifest: Path | None = None,
) -> tuple[DINOWMTransition, ...]:
    """Generate synchronized current/action/next tuples without changing TRACE dynamics.

    Development episodes use the existing zero-process-noise Flood-SAR generator.
    Test generation is unavailable unless an activated freeze manifest is supplied.
    """

    if study_partition not in {"development", "test"}:
        raise ValueError("study_partition must be development or test")
    if study_partition == "test":
        validate_test_authorization(test_authorization_manifest)

    base = generate_simulator_development_episodes(
        count,
        data_seed=data_seed,
        split_seed=split_seed,
    )
    transitions: list[DINOWMTransition] = []
    for episode in base:
        split = episode.split if study_partition == "development" else "test"
        current = episode.snapshot.model_copy(update={"study_partition": study_partition})
        partitioned_episode = SimulatorDevelopmentEpisode(
            episode_id=episode.episode_id,
            split=split,
            request=episode.request,
            snapshot=current,
            target_by_action=episode.target_by_action,
            outcome_by_action=episode.outcome_by_action,
        )
        for action_index, action_name in enumerate(ACTION_NAMES):
            transitions.append(
                DINOWMTransition(
                    episode=partitioned_episode,
                    action_name=action_name,
                    action_index=action_index,
                    current_snapshot=current,
                    next_snapshot=_future_snapshot(
                        partitioned_episode,
                        action_name,
                        action_index,
                        study_partition=study_partition,
                    ),
                )
            )
    return tuple(transitions)


def capture_dinowm_transitions(
    transitions: tuple[DINOWMTransition, ...],
    store: SimulatorVisualObservationStore,
) -> tuple[DINOWMTransition, ...]:
    """Capture each unique current state once and every action-specific next state."""

    current_by_episode: dict[str, CapturedVisualObservation] = {}
    captured: list[DINOWMTransition] = []
    for transition in transitions:
        current = current_by_episode.get(transition.episode.episode_id)
        if current is None:
            current = store.capture(transition.current_snapshot)
            current_by_episode[transition.episode.episode_id] = current
        next_observation = store.capture(transition.next_snapshot)
        if not current.controller_usable or not next_observation.controller_usable:
            raise ValueError("DINO-WM transition unexpectedly contains audit-only imagery")
        captured.append(
            DINOWMTransition(
                episode=transition.episode,
                action_name=transition.action_name,
                action_index=transition.action_index,
                current_snapshot=transition.current_snapshot,
                next_snapshot=transition.next_snapshot,
                current_observation=current,
                next_observation=next_observation,
            )
        )
    return tuple(captured)


def write_dinowm_transition_inventory(
    path: Path,
    transitions: tuple[DINOWMTransition, ...],
    *,
    data_seed: int,
    split_seed: int,
    study_partition: str,
) -> Path:
    if not transitions or any(
        row.current_observation is None or row.next_observation is None
        for row in transitions
    ):
        raise ValueError("all transitions must be captured before inventorying")
    episode_ids = {row.episode.episode_id for row in transitions}
    split_by_episode = {row.episode.episode_id: row.split for row in transitions}
    if any(
        split_by_episode[row.episode.episode_id] != row.split for row in transitions
    ):
        raise ValueError("one episode crosses split boundaries")
    inventory = [
        {
            "episode_id": row.episode.episode_id,
            "split": row.split,
            "action_name": row.action_name,
            "action_index": row.action_index,
            "current_observation_id": row.current_observation.observation_id,
            "current_observation_hash": row.current_observation.observation_hash,
            "next_observation_id": row.next_observation.observation_id,
            "next_observation_hash": row.next_observation.observation_hash,
            "structured_features": list(row.episode.request.structured_features),
            "target": row.episode.target_by_action[row.action_name].tolist(),
            "outcome": row.episode.outcome_by_action[row.action_name],
        }
        for row in transitions
    ]
    payload = {
        "inventory_version": "flood-sar-dinowm-transitions-v1",
        "study_partition": study_partition,
        "episode_count": len(episode_ids),
        "transition_count": len(transitions),
        "data_seed": data_seed,
        "split_seed": split_seed,
        "split_unit": "complete_episode",
        "split_episode_counts": {
            split: sum(value == split for value in split_by_episode.values())
            for split in sorted(set(split_by_episode.values()))
        },
        "action_names": list(ACTION_NAMES),
        "dynamics_contract": "workbench_zero_process_noise_water_update_at_action_arrival_v1",
        "test_authorization_required": study_partition == "test",
        "transitions_sha256": sha256_value(inventory),
        "transitions": inventory,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    return path
