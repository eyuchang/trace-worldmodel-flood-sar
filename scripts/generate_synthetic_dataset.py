from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


FEATURE_NAMES = [
    "water_depth",
    "debris_density",
    "weather_severity",
    "initial_resource_margin",
    "people_count_scaled",
    "current_speed",
]
TARGET_NAMES = [
    "route_success_probability",
    "arrival_time_scaled",
    "hazard_score",
    "remaining_resource_margin",
]
ACTION_NAMES = ["dispatch_north", "verify_north", "dispatch_south"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic flood-SAR action-prefix data")
    parser.add_argument("--episodes", type=int, default=1000)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    if args.episodes < 50:
        raise SystemExit("Use at least 50 episodes so a held-out split is meaningful")

    rng = np.random.default_rng(args.seed)
    state_dim = 39
    action_dim = len(ACTION_NAMES)

    # Mission variables that are legitimately visible to the predictor.
    water = rng.uniform(0.0, 1.0, size=args.episodes)
    debris = rng.uniform(0.0, 1.0, size=args.episodes)
    weather = rng.uniform(0.0, 1.0, size=args.episodes)
    initial_resource = rng.uniform(0.60, 1.00, size=args.episodes)
    people_count = rng.integers(1, 13, size=args.episodes) / 12.0
    current_speed = rng.uniform(0.0, 1.0, size=args.episodes)

    # Remaining dimensions stand in for cached visual and relational features.
    states = rng.normal(0.0, 0.35, size=(args.episodes, state_dim)).astype(np.float32)
    visible = np.stack(
        [water, debris, weather, initial_resource, people_count, current_speed], axis=1
    ).astype(np.float32)
    states[:, : visible.shape[1]] = visible

    action_index = rng.integers(0, action_dim, size=args.episodes)
    actions = np.eye(action_dim, dtype=np.float32)[action_index]

    # Each action exposes the fleet to a different combination of hazards. The
    # targets depend only on visible state plus action, so the exercise does not
    # accidentally teach students to fit labels generated from hidden variables.
    north_risk = 0.58 * water + 0.72 * debris + 0.24 * current_speed + 0.10 * weather
    verify_risk = 0.12 + 0.18 * weather + 0.08 * current_speed
    south_risk = 0.30 * water + 0.18 * debris + 0.34 * weather + 0.10 * current_speed
    route_risk = np.choose(action_index, [north_risk, verify_risk, south_risk])

    success_probability = 1.0 / (1.0 + np.exp(8.0 * (route_risk - 0.72)))
    # Keep labels continuous; sampled binary outcomes belong in a later environment
    # exercise, while this dataset teaches calibrated predicate prediction.
    arrival = (
        360.0
        + 760.0 * route_risk
        + np.choose(action_index, [0.0, 160.0, 300.0])
        + 70.0 * people_count
    ) / 1800.0
    hazard = np.clip(route_risk / 1.35, 0.0, 1.0)
    action_cost = np.choose(action_index, [0.28, 0.10, 0.36])
    resource = np.clip(
        initial_resource - action_cost - 0.24 * route_risk - 0.05 * people_count,
        -1.0,
        1.0,
    )

    targets = np.stack([success_probability, arrival, hazard, resource], axis=1).astype(
        np.float32
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output,
        states=states,
        actions=actions,
        targets=targets,
        feature_names=np.asarray(FEATURE_NAMES, dtype="U64"),
        action_names=np.asarray(ACTION_NAMES, dtype="U64"),
        target_names=np.asarray(TARGET_NAMES, dtype="U64"),
    )
    manifest = {
        "dataset_version": "synthetic-flood-v2",
        "episodes": args.episodes,
        "seed": args.seed,
        "state_dim": state_dim,
        "action_dim": action_dim,
        "feature_names": FEATURE_NAMES,
        "action_names": ACTION_NAMES,
        "target_names": TARGET_NAMES,
        "label_rule": "targets depend only on visible state variables and the action prefix",
    }
    args.output.with_suffix(args.output.suffix + ".json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"Wrote {args.episodes} examples to {args.output}")
    print(f"Wrote dataset manifest to {args.output.with_suffix(args.output.suffix + '.json')}")


if __name__ == "__main__":
    main()
