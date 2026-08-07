from __future__ import annotations

import argparse
import json
from pathlib import Path

from trace_jepa.scenario.delta.environment import (
    inspect_reference_environment,
    require_reference_environment,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify the exact Delta reference environment.")
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--require-match", action="store_true")
    arguments = parser.parse_args()
    verification = inspect_reference_environment(arguments.contract, arguments.lock)
    print(json.dumps(verification.model_dump(mode="json"), indent=2, sort_keys=True))
    if arguments.require_match:
        require_reference_environment(arguments.contract, arguments.lock)


if __name__ == "__main__":
    main()
