"""Public geometry conversions for downstream Reference generation stages."""

from __future__ import annotations

from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from .catalog_models import ReferenceBoundary, ReferenceMetricPoint

_TO_METRIC = Transformer.from_crs(4326, 26910, always_xy=True)
_TO_WGS84 = Transformer.from_crs(26910, 4326, always_xy=True)


def boundary_metric_geometry(boundary: ReferenceBoundary) -> BaseGeometry:
    """Reconstruct one frozen boundary in the registered metric CRS."""

    polygons = []
    for polygon in boundary.polygons_e6:
        exterior = [(x / 1_000_000, y / 1_000_000) for x, y in polygon[0]]
        holes = [[(x / 1_000_000, y / 1_000_000) for x, y in ring] for ring in polygon[1:]]
        metric_exterior = [_TO_METRIC.transform(x, y) for x, y in exterior]
        metric_holes = [[_TO_METRIC.transform(x, y) for x, y in ring] for ring in holes]
        polygons.append(Polygon(metric_exterior, metric_holes))
    geometry: BaseGeometry = polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
    if not geometry.is_valid or geometry.is_empty:
        raise ValueError("registered Reference boundary cannot be reconstructed safely")
    return geometry


def metric_point(easting_m: float, northing_m: float) -> ReferenceMetricPoint:
    """Quantize one generated metric coordinate in both registered CRSs."""

    longitude, latitude = _TO_WGS84.transform(easting_m, northing_m)
    return ReferenceMetricPoint(
        longitude_e6=round(longitude * 1_000_000),
        latitude_e6=round(latitude * 1_000_000),
        easting_mm_epsg26910=round(easting_m * 1_000),
        northing_mm_epsg26910=round(northing_m * 1_000),
    )
