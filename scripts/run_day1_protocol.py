#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from trace_jepa.evaluation.day1 import run_g2, run_smoke


def main() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    private_root = repository_root.parent
    parser = argparse.ArgumentParser(
        description="Run the predeclared Day-1 G2 pilot and gated 3x3 smoke matrix."
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--duration", type=float, default=7200.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=private_root / "day1-evidence/day1-protocol",
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=private_root / "README_EXPERIMENTS.md",
    )
    parser.add_argument("--no-resume", action="store_true")
    arguments = parser.parse_args()

    g2 = run_g2(
        output_root=arguments.output / "g2",
        repository_root=repository_root,
        protocol_path=arguments.protocol,
        duration_s=arguments.duration,
        workers=arguments.workers,
        resume=not arguments.no_resume,
    )
    result: dict[str, object] = {"g2": g2, "smoke": None}
    if g2["status"] == "passed":
        result["smoke"] = run_smoke(
            noise=float(g2["selected_positive_noise"]),
            output_root=arguments.output / "smoke",
            repository_root=repository_root,
            protocol_path=arguments.protocol,
            duration_s=arguments.duration,
            workers=arguments.workers,
            resume=not arguments.no_resume,
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
