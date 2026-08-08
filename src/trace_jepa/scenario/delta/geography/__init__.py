"""Offline simulation-grade geography curated from authoritative sources."""

from .builder import GeographyBuildSecurityError, build_delta_small_geography
from .models import Gauge, GeographyCatalog

__all__ = [
    "Gauge",
    "GeographyBuildSecurityError",
    "GeographyCatalog",
    "build_delta_small_geography",
]
