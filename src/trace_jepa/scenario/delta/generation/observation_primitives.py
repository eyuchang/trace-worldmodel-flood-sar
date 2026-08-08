"""Shared deterministic primitives for the canonical observation channel."""

from __future__ import annotations

import math
from dataclasses import dataclass

from trace_jepa.scenario.delta.domain import CallLocation
from trace_jepa.scenario.delta.generation.randomness import KeyedRandom

BASE_LOCATION_METHOD_MILLI = {
    "gps-or-address-intersection": 550,
    "landmark": 270,
    "cell-sector": 180,
}
BASE_PRECISION_RANGES_M = {
    "gps-or-address-intersection": (15, 75),
    "landmark": (200, 800),
    "cell-sector": (400, 1_500),
}
OTHER_CALL_TYPES = ("C-STR", "C-VEH", "C-LEV", "C-MED", "C-WEL", "C-MIS")


@dataclass(frozen=True)
class LocationRequest:
    """Controller-visible anchor and channel parameters for one noisy location."""

    call_id: str
    easting_mm: int
    northing_mm: int
    structure_number: int
    iota: float
    conflict: bool


def channel_probabilities(iota: float) -> dict[str, float]:
    """Return frozen monotone channel probabilities for information quality."""

    degradation_scale = max(0.0, (1.0 - iota) / 0.1)
    return {
        "duplicate": min(0.85, 0.1164 * degradation_scale),
        "multi_channel": min(0.70, 0.0741 * degradation_scale),
        "revision": min(0.80, 0.2116 * degradation_scale),
        "conflict": min(0.70, 0.10 * degradation_scale),
        "callback_failure": min(0.80, 0.1033 * degradation_scale),
        "drop": min(0.50, 0.04 * degradation_scale),
        "false_report_mean": min(18.0, 4.6667 * degradation_scale),
    }


def location_method_mixture(iota: float) -> dict[str, float]:
    shift = (0.9 - iota) / 0.6
    gps = min(0.65, max(0.15, 0.55 - 0.40 * shift))
    landmark = min(0.30, max(0.17, 0.27 - 0.10 * shift))
    return {
        "gps-or-address-intersection": gps,
        "landmark": landmark,
        "cell-sector": round(1.0 - gps - landmark, 12),
    }


def location_error_scale(iota: float) -> float:
    return min(3.0, 0.9 / iota)


def select_location_method(keyed: KeyedRandom, call_id: str, iota: float) -> str:
    mixture = location_method_mixture(iota)
    draw = keyed.uniform("call", call_id, "location-method")
    cumulative = 0.0
    for method in ("gps-or-address-intersection", "landmark", "cell-sector"):
        cumulative += mixture[method]
        if draw < cumulative:
            return method
    return "cell-sector"


def call_location(
    keyed: KeyedRandom,
    request: LocationRequest,
) -> CallLocation:
    """Generate one noisy, fixed-point controller-visible location."""

    method = select_location_method(keyed, request.call_id, request.iota)
    base_lower, base_upper = BASE_PRECISION_RANGES_M[method]
    scale = location_error_scale(request.iota)
    lower = max(1, round(base_lower * scale))
    upper = max(lower, round(base_upper * scale))
    precision_m = keyed.randint(lower, upper, "call", request.call_id, "precision")
    radius_m = precision_m * math.sqrt(keyed.uniform("call", request.call_id, "radius"))
    if request.conflict:
        radius_m = min(precision_m * 1.5, radius_m + 0.75 * precision_m)
    angle = 2.0 * math.pi * keyed.uniform("call", request.call_id, "angle")
    return CallLocation(
        stated=f"synthetic landmark {request.structure_number:02d}",
        easting_mm=request.easting_mm + round(1_000 * radius_m * math.cos(angle)),
        northing_mm=request.northing_mm + round(1_000 * radius_m * math.sin(angle)),
        precision_m=precision_m,
        method=method,
        confidence_milli=max(50, round(1_000 / (1.0 + precision_m / 100.0))),
    )
