"""Strict, uncapped, historical, and residual-capacity figure families."""

from __future__ import annotations

from typing import Any

from .primitives import COLORS, svg_document, text


def gross_load_figure(windows: Any) -> bytes:
    body = [
        text(64, 82, "Normalized service units", size=12, weight=700),
        text(560, 82, "Headline metric: policy- and predictor-independent", size=9),
    ]
    maximum = max(
        max(
            int(item["active_demand_service_units"]),
            int(item["gross_compatible_capacity_units"]),
        )
        for item in windows
    )

    def x(seconds: float) -> float:
        return 80 + float(seconds) / 21_600 * 820

    def y(units: float) -> float:
        return 540 - float(units) / max(maximum, 1) * 410

    for item in windows:
        if item["gross_unserviceable"]:
            px = x(item["window_start_s"])
            body.append(
                f'<rect x="{px:.1f}" y="110" width="34.2" height="430" fill="#f5b7b1" fill-opacity="0.45"/>'
            )
    demand_points = [
        (x(item["window_start_s"]), y(item["active_demand_service_units"])) for item in windows
    ]
    capacity_points = [
        (x(item["window_start_s"]), y(item["gross_compatible_capacity_units"])) for item in windows
    ]
    for points, color, label, label_y in (
        (demand_points, COLORS["demand"], "active truth demand", 105),
        (capacity_points, COLORS["capacity"], "gross compatible capacity", 125),
    ):
        body.append(
            '<polyline points="'
            + " ".join(f"{px:.1f},{py:.1f}" for px, py in points)
            + f'" fill="none" stroke="{color}" stroke-width="3"/>'
        )
        body.append(
            f'<line x1="80" y1="{label_y}" x2="105" y2="{label_y}" stroke="{color}" stroke-width="3"/>'
        )
        body.append(text(112, label_y + 4, label, size=10))
    for hour in range(7):
        px = x(hour * 3600)
        body.append(text(px - 8, 575, f"+{hour}h", size=10))
    return svg_document("Gross compatible scenario load (peak ratio 1.5)", body)


def residual_pressure_figure(windows: Any) -> bytes:
    body = [
        text(64, 82, "Normalized service units", size=12, weight=700),
        text(535, 82, "Diagnostic only: depends on TRACE commitments", size=9),
    ]
    maximum = max(
        max(
            int(item["residual_unassigned_demand_units"]),
            int(item["free_compatible_capacity_units"]),
        )
        for item in windows
    )

    def x(seconds: float) -> float:
        return 80 + float(seconds) / 21_600 * 820

    def y(units: float) -> float:
        return 540 - float(units) / max(maximum, 1) * 410

    for item in windows:
        if item["residual_unserviceable"]:
            px = x(item["window_start_s"])
            body.append(
                f'<rect x="{px:.1f}" y="110" width="34.2" height="430" '
                'fill="#f5b7b1" fill-opacity="0.45"/>'
            )
    series = (
        (
            "residual_unassigned_demand_units",
            COLORS["demand"],
            "residual unassigned demand",
            105,
        ),
        (
            "free_compatible_capacity_units",
            COLORS["capacity"],
            "free compatible capacity",
            125,
        ),
    )
    for key, color, label, label_y in series:
        points = [(x(item["window_start_s"]), y(item[key])) for item in windows]
        body.append(
            '<polyline points="'
            + " ".join(f"{px:.1f},{py:.1f}" for px, py in points)
            + f'" fill="none" stroke="{color}" stroke-width="3"/>'
        )
        body.append(
            f'<line x1="80" y1="{label_y}" x2="105" y2="{label_y}" '
            f'stroke="{color}" stroke-width="3"/>'
        )
        body.append(text(112, label_y + 4, label, size=10))
    for hour in range(7):
        px = x(hour * 3600)
        body.append(text(px - 8, 575, f"+{hour}h", size=10))
    return svg_document("Residual operational pressure and unserviceable windows", body)


def strict_load_figure(windows: Any) -> bytes:
    body = [
        text(64, 82, "Service units", size=12, weight=700),
        text(515, 82, "Primary: one resource can cover at most one incident", size=9),
    ]
    maximum = max(
        max(int(item["active_demand_units"]), int(item["strict_matched_capacity_units"]))
        for item in windows
    )

    def x(seconds: float) -> float:
        return 80 + float(seconds) / 21_600 * 820

    def y(units: float) -> float:
        return 540 - float(units) / max(maximum, 1) * 410

    for item in windows:
        if item["strict_unserviceable"]:
            px = x(item["window_start_s"])
            body.append(
                f'<rect x="{px:.1f}" y="110" width="34.2" height="430" '
                'fill="#f5b7b1" fill-opacity="0.45"/>'
            )
    for key, color, label, label_y in (
        ("active_demand_units", COLORS["demand"], "active truth demand", 105),
        (
            "strict_matched_capacity_units",
            COLORS["capacity"],
            "strict matched capacity",
            125,
        ),
    ):
        points = [(x(item["window_start_s"]), y(item[key])) for item in windows]
        body.append(
            '<polyline points="'
            + " ".join(f"{px:.1f},{py:.1f}" for px, py in points)
            + f'" fill="none" stroke="{color}" stroke-width="3"/>'
        )
        body.append(
            f'<line x1="80" y1="{label_y}" x2="105" y2="{label_y}" '
            f'stroke="{color}" stroke-width="3"/>'
        )
        body.append(text(112, label_y + 4, label, size=10))
    for hour in range(7):
        px = x(hour * 3600)
        body.append(text(px - 8, 575, f"+{hour}h", size=10))
    return svg_document("Strict concurrent incident load", body)


def strict_residual_pressure_figure(windows: Any) -> bytes:
    body = [
        text(64, 82, "Service units", size=12, weight=700),
        text(535, 82, "Diagnostic only: depends on TRACE commitments", size=9),
    ]
    maximum = max(
        max(
            int(item["residual_demand_units"]),
            int(item["free_strict_compatible_capacity_units"]),
        )
        for item in windows
    )

    def x(seconds: float) -> float:
        return 80 + float(seconds) / 21_600 * 820

    def y(units: float) -> float:
        return 540 - float(units) / max(maximum, 1) * 410

    for item in windows:
        if item["residual_strict_unserviceable"]:
            px = x(item["window_start_s"])
            body.append(
                f'<rect x="{px:.1f}" y="110" width="34.2" height="430" '
                'fill="#f5b7b1" fill-opacity="0.45"/>'
            )
    for key, color, label, label_y in (
        ("residual_demand_units", COLORS["demand"], "residual truth demand", 105),
        (
            "free_strict_compatible_capacity_units",
            COLORS["capacity"],
            "free strict compatible capacity",
            125,
        ),
    ):
        points = [(x(item["window_start_s"]), y(item[key])) for item in windows]
        body.append(
            '<polyline points="'
            + " ".join(f"{px:.1f},{py:.1f}" for px, py in points)
            + f'" fill="none" stroke="{color}" stroke-width="3"/>'
        )
        body.append(
            f'<line x1="80" y1="{label_y}" x2="105" y2="{label_y}" '
            f'stroke="{color}" stroke-width="3"/>'
        )
        body.append(text(112, label_y + 4, label, size=10))
    for hour in range(7):
        px = x(hour * 3600)
        body.append(text(px - 8, 575, f"+{hour}h", size=10))
    return svg_document("Strict residual operational pressure", body)


def metric_sensitivity_figure(windows: Any) -> bytes:
    body = [
        text(64, 82, "Load ratio", size=12, weight=700),
        text(590, 82, "Definitions are reported, not interchangeable", size=9),
    ]
    series = (
        ("strict_concurrent_load_ratio_milli", COLORS["demand"], "strict concurrency", 105),
        (
            "uncapped_compatible_load_ratio_milli",
            COLORS["capacity"],
            "uncapped compatible units",
            125,
        ),
        (
            "registered_normalized_coverable_load_index_milli",
            COLORS["accent"],
            "historical normalized index",
            145,
        ),
    )
    finite = [
        int(item[key])
        for item in windows
        for key, _color, _label, _label_y in series
        if item[key] is not None
    ]
    maximum = max(finite, default=1000)

    def x(seconds: float) -> float:
        return 80 + float(seconds) / 21_600 * 820

    def y(ratio_milli: float) -> float:
        return 540 - float(ratio_milli) / max(maximum, 1) * 370

    for key, color, label, label_y in series:
        points = [
            (x(item["window_start_s"]), y(item[key])) for item in windows if item[key] is not None
        ]
        if points:
            body.append(
                '<polyline points="'
                + " ".join(f"{px:.1f},{py:.1f}" for px, py in points)
                + f'" fill="none" stroke="{color}" stroke-width="3"/>'
            )
        body.append(
            f'<line x1="80" y1="{label_y}" x2="105" y2="{label_y}" '
            f'stroke="{color}" stroke-width="3"/>'
        )
        body.append(text(112, label_y + 4, label, size=10))
    for hour in range(7):
        px = x(hour * 3600)
        body.append(text(px - 8, 575, f"+{hour}h", size=10))
    return svg_document("Load-definition sensitivity analysis", body)
