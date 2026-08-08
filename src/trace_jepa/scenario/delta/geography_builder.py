"""One-release compatibility facade for the secure geography builder."""

from trace_jepa.scenario.delta.geography.builder import (
    BUILDER_VERSION,
    COORDINATE_REFERENCE,
    DEM_ARCHIVE_MEMBER,
    DEM_EXTRACTION_COMMAND,
    FROZEN_V3_BUILD_UTC,
    MAXIMUM_SOURCE_BYTES,
    RETRIEVED_UTC,
    SIMPLIFICATION_TOLERANCE_M,
    BuildBounds,
    GeographyBuildManifest,
    GeographyBuildRequest,
    GeographyBuildSecurityError,
    _fetch_source,
    _safe_output_path,
    _verify_archive_member,
    build_delta_small_geography,
)

__all__ = [
    "BUILDER_VERSION",
    "COORDINATE_REFERENCE",
    "DEM_ARCHIVE_MEMBER",
    "DEM_EXTRACTION_COMMAND",
    "FROZEN_V3_BUILD_UTC",
    "MAXIMUM_SOURCE_BYTES",
    "RETRIEVED_UTC",
    "SIMPLIFICATION_TOLERANCE_M",
    "BuildBounds",
    "GeographyBuildManifest",
    "GeographyBuildRequest",
    "GeographyBuildSecurityError",
    "_fetch_source",
    "_safe_output_path",
    "_verify_archive_member",
    "build_delta_small_geography",
]
