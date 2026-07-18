#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from trace_jepa.evaluation.runner import RunRequest, run_one_sync


def _parser() -> argparse.ArgumentParser:
    repository_root = Path(__file__).resolve().parents[1]
    private_root = repository_root.parent
    parser = argparse.ArgumentParser(
        description=(
            "Run one atomic Day-1 development cell. This command intentionally "
            "rejects validation and test seeds until G3."
        )
    )
    parser.add_argument("--regime", choices=("R-B",), required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--speed", type=float, default=50.0)
    parser.add_argument("--forcing-noise-std", type=float, default=0.35)
    parser.add_argument("--duration", type=float, default=7200.0)
    parser.add_argument("--tick", type=float, default=1.0)
    parser.add_argument(
        "--scenario",
        type=Path,
        default=repository_root / "configs/scenarios/riverside_flood_dynamic_v2.yaml",
    )
    parser.add_argument(
        "--shock-root",
        type=Path,
        default=repository_root / "configs/shocks",
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=private_root / "README_EXPERIMENTS.md",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=private_root / "day1-evidence/runs",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="quarantine and replace an existing complete run",
    )
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    request = RunRequest(
        regime=arguments.regime,
        policy=arguments.policy,
        seed=arguments.seed,
        requested_speed=arguments.speed,
        forcing_noise_std=arguments.forcing_noise_std,
        duration_s=arguments.duration,
        tick_s=arguments.tick,
        scenario_path=arguments.scenario,
        shock_registry_root=arguments.shock_root,
        protocol_path=arguments.protocol,
        output_root=arguments.output,
        resume=not arguments.no_resume,
    )
    directory = run_one_sync(request)
    print(json.dumps({"status": "complete", "run_directory": str(directory)}))


if __name__ == "__main__":
    main()
