from __future__ import annotations

import argparse
import logging
from pathlib import Path

from trace_jepa.scenario.delta.geography.builder import (
    GeographyBuildRequest,
    build_delta_small_geography,
)
from trace_jepa.support import ArtifactLocator

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the frozen authoritative GIS bundle for Delta Small."
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--geography-name", type=Path, required=True)
    parser.add_argument("--manifest-name", type=Path, required=True)
    parser.add_argument("--dem-root", type=Path, required=True)
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
        GeographyBuildRequest(
            source_root=arguments.source_root,
            output_root=arguments.output_root,
            geography_relative_name=arguments.geography_name,
            manifest_relative_name=arguments.manifest_name,
            dem_archive=ArtifactLocator(
                arguments.dem_root,
                arguments.dem_archive,
                2_000_000_000,
                "DEM archive",
            ),
            dem_raster=ArtifactLocator(
                arguments.dem_root,
                arguments.dem_raster,
                2_000_000_000,
                "DEM raster",
            ),
            refresh_sources=arguments.refresh_sources,
        )
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
