"""Command-line wrapper for the Reference delivery-history license gate."""

from __future__ import annotations

import argparse
from pathlib import Path

from trace_reference.delivery_history import verify_delivery_history


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--revision", default="HEAD")
    args = parser.parse_args()
    verify_delivery_history(args.repo, args.revision)


if __name__ == "__main__":
    main()
