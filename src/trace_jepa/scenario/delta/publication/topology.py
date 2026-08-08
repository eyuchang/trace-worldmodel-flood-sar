"""Topology, gauge, facility, and resource-origin publication figure."""

from __future__ import annotations

from typing import Any

from .primitives import COLORS, svg_document, text


def topology_figure(geography: Any, resources: Any, resource_provenance: Any) -> bytes:
    islands = list(geography["islands"])
    waterways = list(geography["waterways"])
    coordinates: list[tuple[float, float]] = []
    for island in islands:
        for polygon in island["geometry"]["polygons"]:
            coordinates.extend(
                (point["easting_mm"] / 1000.0, point["northing_mm"] / 1000.0)
                for point in polygon["points"]
            )
    automatic_aid_location = resource_provenance["facts"]["location"]
    coordinates.append(
        (
            automatic_aid_location["easting_mm_epsg_26910"] / 1000.0,
            automatic_aid_location["northing_mm_epsg_26910"] / 1000.0,
        )
    )
    minimum_east = min(point[0] for point in coordinates)
    maximum_east = max(point[0] for point in coordinates)
    minimum_north = min(point[1] for point in coordinates)
    maximum_north = max(point[1] for point in coordinates)

    def project(easting_mm: int, northing_mm: int) -> tuple[float, float]:
        x = 45 + (easting_mm / 1000.0 - minimum_east) / (maximum_east - minimum_east) * 610
        y = 575 - (northing_mm / 1000.0 - minimum_north) / (maximum_north - minimum_north) * 500
        return x, y

    body: list[str] = []
    for waterway in waterways:
        for segment in waterway["segments"]:
            points = [
                project(item["easting_mm"], item["northing_mm"]) for item in segment["points"]
            ]
            body.append(
                '<polyline points="'
                + " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
                + f'" fill="none" stroke="{COLORS["water"]}" stroke-width="3"/>'
            )
    for island in islands:
        color = COLORS["andrus"] if island["island_id"] == "ISL-01" else COLORS["brannan"]
        for polygon in island["geometry"]["polygons"]:
            points = [
                project(item["easting_mm"], item["northing_mm"]) for item in polygon["points"]
            ]
            body.append(
                '<polygon points="'
                + " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
                + f'" fill="{color}" fill-opacity="0.72" stroke="#657a65" stroke-width="1"/>'
            )
        x, y = project(island["centroid"]["easting_mm"], island["centroid"]["northing_mm"])
        body.append(text(x - 34, y, island["name"], size=13, weight=700))
    for crossing in geography["crossings"]:
        x, y = project(crossing["location"]["easting_mm"], crossing["location"]["northing_mm"])
        body.append(f'<rect x="{x - 4:.1f}" y="{y - 4:.1f}" width="8" height="8" fill="#333"/>')
        body.append(text(x + 7, y - 5, crossing["crossing_id"], size=11, weight=700))
    for facility in geography["facilities"]:
        x, y = project(facility["location"]["easting_mm"], facility["location"]["northing_mm"])
        operative = bool(facility["operational_for_routing"])
        body.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{COLORS["accent"]}" '
            + ("" if operative else 'fill-opacity="0.35" stroke-dasharray="2 2" ')
            + "/>"
        )
        suffix = "" if operative else " (approx.; non-operative)"
        body.append(text(x + 9, y + 4, facility["name"] + suffix, size=10))
    aid_x, aid_y = project(
        automatic_aid_location["easting_mm_epsg_26910"],
        automatic_aid_location["northing_mm_epsg_26910"],
    )
    body.append(
        f'<polygon points="{aid_x:.1f},{aid_y - 7:.1f} {aid_x + 7:.1f},{aid_y:.1f} '
        f'{aid_x:.1f},{aid_y + 7:.1f} {aid_x - 7:.1f},{aid_y:.1f}" '
        f'fill="{COLORS["hazard"]}"/>'
    )
    body.append(text(aid_x + 10, aid_y + 4, "Rio Vista Station 55 (secondary geocode)", size=10))
    body.append(
        '<rect x="680" y="62" width="245" height="500" rx="8" fill="#f7f9f9" stroke="#ccd1d1"/>'
    )
    body.append(text(700, 92, "Gauge registry", size=16, weight=700))
    gauge_labels = {
        "RVB": "Rio Vista Bridge",
        "MRU": "Middle River / Undine Rd",
        "FPT": "Freeport",
    }
    y = 122
    for gauge in geography["gauges"]:
        operative = gauge["threshold_status"] != "unavailable-non-operative"
        label = gauge_labels[gauge["gauge_id"]]
        body.append(text(700, y, f"{gauge['gauge_id']}: {label}", size=11, weight=700))
        body.append(
            text(700, y + 17, "threshold-operative" if operative else "observational only", size=10)
        )
        y += 55
    body.append(text(700, y + 8, "Frozen resource schedule", size=16, weight=700))
    y += 38
    for unit in resources["units"]:
        body.append(
            text(
                700,
                y,
                f"{unit['resource_id']}: {unit['resource_class']} @T+{unit['available_from_s']}s",
                size=9,
            )
        )
        y += 20
    body.append(text(700, y + 22, "CRS: EPSG:26910 for metric operations", size=10))
    body.append(text(700, y + 39, "Source geometries retained in WGS84", size=10))
    return svg_document("Delta Small topology and reviewed operational anchors", body)
