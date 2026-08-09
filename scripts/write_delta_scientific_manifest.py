from __future__ import annotations

import argparse
from pathlib import Path

from trace_jepa.scenario.delta.scientific_manifest import write_scientific_input_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze the Delta artifact-reconstruction inputs.")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    write_scientific_input_manifest(arguments.repository, arguments.output)


if __name__ == "__main__":
    main()
