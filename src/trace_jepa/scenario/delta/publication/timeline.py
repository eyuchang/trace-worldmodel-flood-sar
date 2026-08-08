"""Hazard, stage, incident, observation, and coordination timeline figure."""

from __future__ import annotations

from typing import Any

from .primitives import COLORS, svg_document, text


def timeline_figure(
    meteorology: Any,
    hydrology: Any,
    calls: Any,
    resources: Any,
    ground_truth: Any | None = None,
    coordination: Any | None = None,
) -> bytes:
    expanded_v8 = ground_truth is not None or coordination is not None
    body = [
        text(55, 78, "Rain (milli-in/hr)", size=12, weight=700),
        text(55, 280, "RVB stage (millifeet)", size=12, weight=700),
        text(
            55,
            470 if expanded_v8 else 485,
            (
                "Truth episodes → reports → controller delivery"
                if expanded_v8
                else "Controller-visible reports"
            ),
            size=12,
            weight=700,
        ),
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
    if ground_truth is not None:
        for incident in ground_truth["incidents"]:
            px = x(incident["onset_s"])
            body.append(f'<circle cx="{px:.1f}" cy="492" r="3" fill="{COLORS["ink"]}"/>')
    delivery_by_call = (
        {item["call_id"]: item["available_to_controller_s"] for item in coordination["deliveries"]}
        if coordination is not None
        else {}
    )
    for index, call in enumerate(calls):
        px = x(call["received_s"])
        py = 515 + (index % 3) * 10 if expanded_v8 else 520 + (index % 4) * 12
        color = taxonomy_colors[call["reported"]["call_type"]]
        body.append(
            f'<line x1="{px:.1f}" y1="{502 if expanded_v8 else 500}" '
            f'x2="{px:.1f}" y2="{py:.1f}" stroke="{color}" stroke-width="2"/>'
        )
        if call["call_id"] in delivery_by_call:
            delivery_x = x(delivery_by_call[call["call_id"]])
            body.append(
                f'<line x1="{px:.1f}" y1="550" x2="{delivery_x:.1f}" y2="550" '
                f'stroke="{COLORS["muted"]}" stroke-width="1"/>'
            )
            body.append(f'<circle cx="{delivery_x:.1f}" cy="550" r="2" fill="{COLORS["accent"]}"/>')
    automatic_aid_arrival = min(
        unit["available_from_s"]
        for unit in resources["units"]
        if unit["availability_mode"] == "preauthorized-automatic-aid-fixed-staging"
    )
    aid_x = x(automatic_aid_arrival)
    body.append(
        f'<line x1="{aid_x:.1f}" y1="90" x2="{aid_x:.1f}" y2="570" '
        f'stroke="{COLORS["hazard"]}" stroke-width="2" stroke-dasharray="6 4"/>'
    )
    body.append(text(aid_x + 5, 105, "automatic aid staged", size=10, weight=700))
    for hour in range(7):
        px = x(hour * 3600)
        body.append(f'<line x1="{px:.1f}" y1="90" x2="{px:.1f}" y2="570" stroke="#e5e7e9"/>')
        body.append(text(px - 8, 592, f"+{hour}h", size=10))
    return svg_document(
        (
            "Hazard, incident, report, and coordination-delivery timeline"
            if expanded_v8
            else "Hazard, RVB stage, and observed-call timeline"
        ),
        body,
    )
