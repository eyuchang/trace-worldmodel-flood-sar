from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from trace_jepa.scenario.delta.artifacts import (
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    verify_scenario_artifacts,
)

SVG_WIDTH = 960
SVG_HEIGHT = 640
COLORS = {
    "ink": "#17202a",
    "muted": "#59636e",
    "water": "#9ecae1",
    "andrus": "#d9ead3",
    "brannan": "#fce5cd",
    "hazard": "#c0392b",
    "capacity": "#21618c",
    "demand": "#a93226",
    "accent": "#6c3483",
}


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def _text(x: float, y: float, value: object, *, size: int = 14, weight: int = 400) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{COLORS["ink"]}">'
        f"{html.escape(str(value))}</text>"
    )


def _svg_document(title: str, body: list[str]) -> bytes:
    payload = [
        (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{SVG_WIDTH}" height="{SVG_HEIGHT}" '
            f'viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}">'
        ),
        f"<title>{html.escape(title)}</title>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        _text(36, 40, title, size=22, weight=700),
        *body,
        _text(
            36,
            SVG_HEIGHT - 18,
            "WF-DFLD-01-SMALL · simulation-grade teaching artifact · not for navigation",
            size=11,
        ),
        "</svg>",
    ]
    return ("\n".join(payload) + "\n").encode("utf-8")


def _topology_figure(geography: Any, resources: Any) -> bytes:
    islands = list(geography["islands"])
    waterways = list(geography["waterways"])
    coordinates: list[tuple[float, float]] = []
    for island in islands:
        for polygon in island["geometry"]["polygons"]:
            coordinates.extend(
                (point["easting_mm"] / 1000.0, point["northing_mm"] / 1000.0)
                for point in polygon["points"]
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
        body.append(_text(x - 34, y, island["name"], size=13, weight=700))
    for crossing in geography["crossings"]:
        x, y = project(crossing["location"]["easting_mm"], crossing["location"]["northing_mm"])
        body.append(f'<rect x="{x - 4:.1f}" y="{y - 4:.1f}" width="8" height="8" fill="#333"/>')
        body.append(_text(x + 7, y - 5, crossing["crossing_id"], size=11, weight=700))
    for facility in geography["facilities"]:
        x, y = project(facility["location"]["easting_mm"], facility["location"]["northing_mm"])
        operative = bool(facility["operational_for_routing"])
        body.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{COLORS["accent"]}" '
            + ("" if operative else 'fill-opacity="0.35" stroke-dasharray="2 2" ')
            + "/>"
        )
        suffix = "" if operative else " (approx.; non-operative)"
        body.append(_text(x + 9, y + 4, facility["name"] + suffix, size=10))
    body.append(
        '<rect x="680" y="62" width="245" height="500" rx="8" fill="#f7f9f9" stroke="#ccd1d1"/>'
    )
    body.append(_text(700, 92, "Gauge registry", size=16, weight=700))
    gauge_labels = {
        "RVB": "Rio Vista Bridge",
        "MRU": "Middle River / Undine Rd",
        "FPT": "Freeport",
    }
    y = 122
    for gauge in geography["gauges"]:
        operative = gauge["threshold_status"] != "unavailable-non-operative"
        label = gauge_labels[gauge["gauge_id"]]
        body.append(_text(700, y, f"{gauge['gauge_id']}: {label}", size=11, weight=700))
        body.append(
            _text(
                700, y + 17, "threshold-operative" if operative else "observational only", size=10
            )
        )
        y += 55
    body.append(_text(700, y + 8, "Local resource inventory", size=16, weight=700))
    y += 38
    for unit in resources["units"]:
        body.append(_text(700, y, f"{unit['resource_id']}: {unit['resource_class']}", size=10))
        y += 20
    body.append(_text(700, y + 22, "CRS: EPSG:26910 for metric operations", size=10))
    body.append(_text(700, y + 39, "Source geometries retained in WGS84", size=10))
    return _svg_document("Delta Small topology and reviewed operational anchors", body)


def _timeline_figure(
    meteorology: Any,
    hydrology: Any,
    calls: Any,
) -> bytes:
    body = [
        _text(55, 78, "Rain (milli-in/hr)", size=12, weight=700),
        _text(55, 280, "RVB stage (millifeet)", size=12, weight=700),
        _text(55, 485, "Controller-visible reports", size=12, weight=700),
    ]

    def x(seconds: float) -> float:
        return 80 + float(seconds) / 21_600 * 820

    rain_max = max(float(item["rain_milli_inches_per_hour"]) for item in meteorology)
    rain_points = [
        (
            x(item["simulation_time_s"]),
            240 - float(item["rain_milli_inches_per_hour"]) / rain_max * 130,
        )
        for item in meteorology
    ]
    body.append(
        '<polyline points="'
        + " ".join(f"{px:.1f},{py:.1f}" for px, py in rain_points)
        + f'" fill="none" stroke="{COLORS["water"]}" stroke-width="3"/>'
    )
    rvb = [item for item in hydrology if item["gauge_id"] == "RVB"]
    low = min(float(item["stage_millifeet"]) for item in rvb)
    high = max(float(item["stage_millifeet"]) for item in rvb)
    stage_points = [
        (
            x(item["simulation_time_s"]),
            445 - (float(item["stage_millifeet"]) - low) / (high - low) * 130,
        )
        for item in rvb
    ]
    body.append(
        '<polyline points="'
        + " ".join(f"{px:.1f},{py:.1f}" for px, py in stage_points)
        + f'" fill="none" stroke="{COLORS["capacity"]}" stroke-width="3"/>'
    )
    taxonomy_colors = {
        "C-STR": "#a93226",
        "C-VEH": "#d35400",
        "C-LEV": "#7d6608",
        "C-MED": "#6c3483",
        "C-WEL": "#1e8449",
        "C-MIS": "#2e86c1",
    }
    for index, call in enumerate(calls):
        px = x(call["received_s"])
        py = 520 + (index % 4) * 12
        color = taxonomy_colors[call["reported"]["call_type"]]
        body.append(
            f'<line x1="{px:.1f}" y1="500" x2="{px:.1f}" y2="{py:.1f}" stroke="{color}" stroke-width="2"/>'
        )
    for hour in range(7):
        px = x(hour * 3600)
        body.append(f'<line x1="{px:.1f}" y1="90" x2="{px:.1f}" y2="570" stroke="#e5e7e9"/>')
        body.append(_text(px - 8, 592, f"+{hour}h", size=10))
    return _svg_document("Hazard, RVB stage, and observed-call timeline", body)


def _demand_figure(windows: Any) -> bytes:
    body = [
        _text(64, 82, "Normalized service units", size=12, weight=700),
        _text(600, 82, "Red bands = zero spare compatible capacity", size=9),
    ]
    maximum = max(
        max(
            int(item["uncovered_demand_service_units"]),
            int(item["compatible_uncommitted_capacity_units"]),
        )
        for item in windows
    )

    def x(seconds: float) -> float:
        return 80 + float(seconds) / 21_600 * 820

    def y(units: float) -> float:
        return 540 - float(units) / max(maximum, 1) * 410

    for item in windows:
        if item["explicitly_unserviceable"]:
            px = x(item["window_start_s"])
            body.append(
                f'<rect x="{px:.1f}" y="110" width="34.2" height="430" fill="#f5b7b1" fill-opacity="0.45"/>'
            )
    demand_points = [
        (x(item["window_start_s"]), y(item["uncovered_demand_service_units"])) for item in windows
    ]
    capacity_points = [
        (x(item["window_start_s"]), y(item["compatible_uncommitted_capacity_units"]))
        for item in windows
    ]
    for points, color, label, label_y in (
        (demand_points, COLORS["demand"], "uncovered demand", 105),
        (capacity_points, COLORS["capacity"], "compatible uncommitted capacity", 125),
    ):
        body.append(
            '<polyline points="'
            + " ".join(f"{px:.1f},{py:.1f}" for px, py in points)
            + f'" fill="none" stroke="{color}" stroke-width="3"/>'
        )
        body.append(
            f'<line x1="80" y1="{label_y}" x2="105" y2="{label_y}" stroke="{color}" stroke-width="3"/>'
        )
        body.append(_text(112, label_y + 4, label, size=10))
    for hour in range(7):
        px = x(hour * 3600)
        body.append(_text(px - 8, 575, f"+{hour}h", size=10))
    return _svg_document("Active uncovered demand and compatible local capacity", body)


def _flow_figure(summary: Any, trace_records: Any) -> bytes:
    body: list[str] = []
    nodes = [
        (40, "Hidden causal truth", f"{summary['latent_incidents']} latent incidents", "#d5f5e3"),
        (225, "Lossy evidence", f"{summary['observed_calls']} visible reports", "#d6eaf8"),
        (
            410,
            "Controller beliefs",
            f"{summary['visible_evidence_repairs']} visible repairs",
            "#fcf3cf",
        ),
        (595, "TRACE governance", f"{len(trace_records)} record versions", "#e8daef"),
        (
            780,
            "Durable outcomes",
            f"{summary['allocations']} allocate · {summary['refusals']} refuse",
            "#fadbd8",
        ),
    ]
    for x, title, subtitle, color in nodes:
        body.append(
            f'<rect x="{x}" y="220" width="145" height="120" rx="10" fill="{color}" stroke="#566573"/>'
        )
        body.append(_text(x + 12, 255, title, size=13, weight=700))
        body.append(_text(x + 12, 283, subtitle, size=11))
        if x < 780:
            body.append(
                f'<line x1="{x + 145}" y1="280" x2="{x + 180}" y2="280" stroke="#566573" stroke-width="2"/>'
            )
            body.append(
                f'<polygon points="{x + 180},280 {x + 170},274 {x + 170},286" fill="#566573"/>'
            )
    body.append(
        _text(
            45,
            395,
            "Truth IDs and person IDs never cross the hidden/public boundary.",
            size=13,
            weight=700,
        )
    )
    body.append(
        _text(
            45,
            425,
            "Repairs use shared callback tokens, report revisions, and spatial/temporal similarity.",
            size=12,
        )
    )
    body.append(
        _text(
            45,
            455,
            "Every allocation cites the exact consumed TRACE record version that authorized it.",
            size=12,
        )
    )
    body.append(
        _text(
            45,
            485,
            "Toy is a transparent teaching fixture; MLP and V-JEPA remain unqualified by default.",
            size=12,
        )
    )
    return _svg_document("Ground truth → lossy evidence → beliefs → TRACE decisions", body)


def publish_reference_bundle(reference_root: Path, output_root: Path) -> dict[str, object]:
    verify_scenario_artifacts(reference_root)
    output_root.mkdir(parents=True, exist_ok=True)
    geography = _load_json(reference_root / "geography.json")
    resources = _load_json(reference_root / "resources.json")
    meteorology = _load_json(reference_root / "meteorology.json")
    hydrology = _load_json(reference_root / "hydrology.json")
    calls = _load_json(reference_root / "calls.json")
    windows = _load_json(reference_root / "demand_capacity.json")
    summary = _load_json(reference_root / "result_summary.json")
    validation = _load_json(reference_root / "validation_summary.json")
    trace_records = _load_json(reference_root / "trace_records.json")
    figures = {
        "delta_small_topology.svg": _topology_figure(geography, resources),
        "delta_small_timeline.svg": _timeline_figure(meteorology, hydrology, calls),
        "delta_small_demand_capacity.svg": _demand_figure(windows),
        "delta_small_trace_walkthrough.svg": _flow_figure(summary, trace_records),
    }
    descriptors: list[dict[str, object]] = []
    for file_name, payload in sorted(figures.items()):
        destination = output_root / file_name
        if destination.is_symlink():
            raise ValueError(f"publication output must not be a symlink: {destination}")
        destination.write_bytes(payload)
        descriptors.append(
            {"file_name": file_name, "sha256": sha256_bytes(payload), "byte_length": len(payload)}
        )
    result_table = canonical_json_bytes(
        {
            "schema_version": "delta-small-publication-result-table-v2",
            "book_walkthrough": summary,
            "registered_validation": validation,
        }
    )
    (output_root / "publication_result_table.json").write_bytes(result_table)
    descriptors.append(
        {
            "file_name": "publication_result_table.json",
            "sha256": sha256_bytes(result_table),
            "byte_length": len(result_table),
        }
    )
    manifest: dict[str, object] = {
        "schema_version": "delta-small-publication-bundle-v1",
        "reference_manifest_sha256": sha256_file(reference_root / "manifest.json"),
        "metadata_policy": "deterministic-svg-no-timestamps-no-notebook",
        "artifacts": descriptors,
    }
    (output_root / "publication_manifest.json").write_bytes(canonical_json_bytes(manifest))
    return manifest
