from __future__ import annotations

import argparse
import logging
from pathlib import Path

from trace_jepa.scenario.delta.geography_builder import build_delta_small_geography

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the frozen authoritative GIS bundle for Delta Small."
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--geography-output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--dem-archive", type=Path, required=True)
    parser.add_argument("--dem-raster", type=Path, required=True)
    parser.add_argument(
        "--refresh-sources",
        action="store_true",
        help="Refresh government snapshots over the network (off by default).",
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    arguments = build_parser().parse_args()
    catalog = build_delta_small_geography(
        arguments.source_root,
        arguments.geography_output,
        arguments.manifest_output,
        arguments.dem_archive,
        arguments.dem_raster,
        refresh_sources=arguments.refresh_sources,
    )
    LOGGER.info(
        "Built %s: islands=%d waterways=%d facilities=%d",
        catalog.schema_version,
        len(catalog.islands),
        len(catalog.waterways),
        len(catalog.facilities),
    )


if __name__ == "__main__":
    main()
