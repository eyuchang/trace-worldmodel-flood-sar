"""Print a local, non-acceptance Reference scale characterization."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .loading import load_reference_config
from .scale import benchmark_reference_event_ordering, characterize_reference_scale


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/scenarios/wf_dfld_01_reference_development.yaml"),
    )
    parser.add_argument("--repeats", type=int, default=5)
    arguments = parser.parse_args()
    configuration = load_reference_config(arguments.repo_root, arguments.config)
    characterization = characterize_reference_scale(configuration)
    benchmark = benchmark_reference_event_ordering(
        characterization,
        repeats=arguments.repeats,
    )
    print(
        json.dumps(
            {
                "characterization": characterization.model_dump(mode="json"),
                "benchmark": benchmark.model_dump(mode="json"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
