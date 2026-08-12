"""Build the Reference geography from committed offline sources."""

from __future__ import annotations

import argparse
from pathlib import Path

from .builder import build_reference_geography


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--receipts", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    build_reference_geography(
        geography_root=args.input_root,
        metadata_relative_name=args.metadata,
        retrieval_relative_name=args.receipts,
        output_root=args.output_root,
    )


if __name__ == "__main__":
    main()
