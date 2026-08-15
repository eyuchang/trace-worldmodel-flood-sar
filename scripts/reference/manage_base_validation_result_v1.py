"""Write or verify the completed Reference validation-v2 result registry."""

from __future__ import annotations

import argparse
from pathlib import Path

from trace_reference_recovery.result_registry import (
    verify_original_result_registry,
    write_original_result_registry,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        required=True,
        type=Path,
        help="Trusted repository checkout containing the retained result artifacts.",
    )
    parser.add_argument("mode", choices=("write", "verify"))
    return parser.parse_args()


def main() -> int:
    """Execute one deterministic registry operation."""

    args = _parse_args()
    if args.mode == "write":
        registry = write_original_result_registry(args.repository_root)
    else:
        registry = verify_original_result_registry(args.repository_root)
    print(registry.registry_digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
