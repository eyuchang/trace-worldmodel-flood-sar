"""Deterministic development figures derived from a verified Reference bundle."""

from __future__ import annotations

from collections import Counter

from trace_reference.domain import ReferenceResourceActivationPhase

from .inputs import ReferencePublicationInputs
from .svg import SvgBoxStyle, SvgCircleStyle, SvgDocument, SvgLineStyle, SvgTextStyle

_INK = "#0f172a"
_BLUE = "#2563eb"
_CYAN = "#0891b2"
_ORANGE = "#ea580c"
_RED = "#dc2626"
_GREEN = "#15803d"
_GRAY = "#64748b"


def _title(document: SvgDocument, title: str, subtitle: str) -> None:
    document.text(50, 42, title, style=SvgTextStyle(size=22, weight=700))
    document.text(50, 67, subtitle, style=SvgTextStyle(size=12, fill=_GRAY))


def topology_figure(values: ReferencePublicationInputs) -> bytes:
    """Show the simulation topology, communities, and registered resource staging."""

    document = SvgDocument()
    _title(
        document,
        "WF-DFLD-01-REFERENCE simulation topology",
        "Simulation-grade geometry curated from authoritative sources; not navigation-grade",
    )
    points = {
        item.node_id: (
            item.anchor.easting_mm_epsg26910,
            item.anchor.northing_mm_epsg26910,
        )
        for item in values.geography.route_nodes
    }
    all_x = [item[0] for item in points.values()]
    all_y = [item[1] for item in points.values()]
    x_min, x_max = min(all_x), max(all_x)
    y_min, y_max = min(all_y), max(all_y)

    def project(point: tuple[int, int]) -> tuple[int, int]:
        x = 90 + (point[0] - x_min) * 770 // max(1, x_max - x_min)
        y = 525 - (point[1] - y_min) * 410 // max(1, y_max - y_min)
        return x, y

    for edge in values.geography.route_edges:
        start = project(points[edge.from_node_id])
        end = project(points[edge.to_node_id])
        color = _BLUE if edge.mode == "road-crossing" else _CYAN
        document.line(*start, *end, style=SvgLineStyle(stroke=color, width=3))
        document.text(
            (start[0] + end[0]) // 2,
            (start[1] + end[1]) // 2 - 5,
            edge.edge_id,
            style=SvgTextStyle(size=10, fill=color, anchor="middle"),
        )
    resource_counts = Counter(item.staged_node_id for item in values.resources.resources)
    for node_id, point in sorted(points.items()):
        x, y = project(point)
        document.circle(x, y, 8, style=SvgCircleStyle(fill=_INK))
        document.text(x + 11, y - 7, node_id, style=SvgTextStyle(size=11, weight=700))
        if resource_counts[node_id]:
            document.text(
                x + 11,
                y + 11,
                f"{resource_counts[node_id]} resources",
                style=SvgTextStyle(size=10),
            )
    for community in values.geography.communities:
        x, y = project(
            (
                community.anchor.easting_mm_epsg26910,
                community.anchor.northing_mm_epsg26910,
            )
        )
        document.circle(x, y, 5, style=SvgCircleStyle(fill=_ORANGE))
        document.text(
            x + 8,
            y + 16,
            community.name,
            style=SvgTextStyle(size=10, fill=_ORANGE),
        )
    document.text(
        50,
        575,
        "Blue: road crossing   Cyan: simulation water transfer",
        style=SvgTextStyle(size=11),
    )
    return document.render(
        title="Reference simulation topology",
        description="Eight-island route graph with communities and registered resource staging.",
    )


def timeline_figure(values: ReferencePublicationInputs) -> bytes:
    """Plot hourly reports beside rain forcing and the modeled breach phase."""

    document = SvgDocument()
    _title(
        document,
        "Hazard, public-report, and activation timeline",
        "Offline modeled hazard is distinguished from controller-visible public reports",
    )
    reports = [0] * 96
    for report in values.reports.reports:
        if 0 <= report.observed_at_s < 345_600:
            reports[report.observed_at_s // 3600] += 1
    rain = []
    breach = []
    for hour in range(96):
        sample = values.physical.samples[(172_800 + hour * 3600) // 300]
        rain.append(sample.weather.effective_rain_milli_in_per_hour)
        breach.append(sample.breach.active)
    maximum_reports = max(95, max(reports, default=0))
    maximum_rain = max(1, max(rain, default=1))
    left, top, width, height = 65, 95, 880, 400
    for hour, active in enumerate(breach):
        if active:
            x = left + hour * width // 96
            next_x = left + (hour + 1) * width // 96
            document.rect(
                x,
                top,
                next_x - x + 1,
                height,
                style=SvgBoxStyle(fill="#fee2e2", opacity_milli=650),
            )
    for hour, count in enumerate(reports):
        x = left + hour * width // 96
        next_x = left + (hour + 1) * width // 96
        bar_height = count * height // maximum_reports
        document.rect(
            x,
            top + height - bar_height,
            max(1, next_x - x - 1),
            bar_height,
            style=SvgBoxStyle(fill=_BLUE),
        )
    rain_points = tuple(
        (
            left + hour * width // 95,
            top + height - value * height // maximum_rain,
        )
        for hour, value in enumerate(rain)
    )
    document.polyline(rain_points, style=SvgLineStyle(stroke=_CYAN, width=3))
    target_y = top + height - 95 * height // maximum_reports
    document.line(
        left,
        target_y,
        left + width,
        target_y,
        style=SvgLineStyle(stroke=_ORANGE, dash="6 5"),
    )
    for hour in range(0, 97, 12):
        x = left + hour * width // 96
        document.line(
            x,
            top + height,
            x,
            top + height + 6,
            style=SvgLineStyle(stroke=_INK, width=1),
        )
        document.text(
            x,
            top + height + 24,
            f"T+{hour}h",
            style=SvgTextStyle(size=10, anchor="middle"),
        )
    available_times = {
        item.resource_id: item.observed_at_s
        for item in values.activations.events
        if item.phase == ReferenceResourceActivationPhase.AVAILABLE
        and item.recipient_authority_id == "AUTH-01"
    }
    document.text(
        65,
        550,
        f"Reports: {sum(reports)} evaluation | registered resources: {len(available_times)} | "
        "orange dashed: 95/hour synthetic design target",
        style=SvgTextStyle(size=11),
    )
    return document.render(
        title="Reference hazard and report timeline",
        description="Hourly report counts, modeled rainfall, breach phase, and design-target marker.",
    )


def _line_segments(
    values: tuple[int | None, ...],
    *,
    maximum: int,
) -> tuple[tuple[tuple[int, int], ...], ...]:
    segments: list[tuple[tuple[int, int], ...]] = []
    current: list[tuple[int, int]] = []
    for index, value in enumerate(values):
        if value is None:
            if current:
                segments.append(tuple(current))
                current = []
            continue
        current.append((65 + index * 880 // 383, 495 - value * 390 // maximum))
    if current:
        segments.append(tuple(current))
    return tuple(segments)


def capacity_figure(values: ReferencePublicationInputs) -> bytes:
    """Plot primary strict load with separately labeled sensitivity definitions."""

    document = SvgDocument()
    _title(
        document,
        "Concurrent load and metric-definition sensitivity",
        "Strict one-resource/one-incident concurrency is primary; no numerical load gate",
    )
    windows = values.capacity.windows
    series = (
        (
            "strict",
            tuple(item.strict_concurrent_load_ratio_milli for item in windows),
            _BLUE,
            None,
        ),
        (
            "uncapped service-unit sensitivity",
            tuple(item.uncapped_compatible_load_ratio_milli for item in windows),
            _CYAN,
            "7 5",
        ),
        (
            "historical normalized sensitivity",
            tuple(item.historical_normalized_coverable_load_index_milli for item in windows),
            _ORANGE,
            "3 4",
        ),
        (
            "residual strict pressure",
            tuple(item.residual_strict_pressure_ratio_milli for item in windows),
            _GREEN,
            "10 4",
        ),
    )
    maximum = max(
        1_000,
        *(item for _name, data, _color, _dash in series for item in data if item is not None),
    )
    for _name, data, color, dash in series:
        for segment in _line_segments(data, maximum=maximum):
            document.polyline(
                segment,
                style=SvgLineStyle(stroke=color, width=3, dash=dash),
            )
    for index, window in enumerate(windows):
        if window.strict_unserviceable:
            x = 65 + index * 880 // 383
            document.circle(
                x,
                95,
                3,
                style=SvgCircleStyle(fill=_RED, stroke=_RED, stroke_width=1),
            )
    document.line(65, 495, 945, 495, style=SvgLineStyle(stroke=_INK, width=1))
    document.line(65, 95, 65, 495, style=SvgLineStyle(stroke=_INK, width=1))
    for hour in range(0, 97, 12):
        x = 65 + hour * 880 // 96
        document.text(
            x,
            520,
            f"T+{hour}h",
            style=SvgTextStyle(size=10, anchor="middle"),
        )
    for index, (label, _data, color, dash) in enumerate(series):
        y = 545 + (index // 2) * 20
        x = 65 + (index % 2) * 430
        document.line(
            x,
            y - 4,
            x + 28,
            y - 4,
            style=SvgLineStyle(stroke=color, width=3, dash=dash),
        )
        document.text(x + 36, y, label, style=SvgTextStyle(size=10))
    return document.render(
        title="Reference load sensitivity",
        description="Strict, uncapped, historical normalized, and residual load traces.",
    )


def trace_flow_figure(values: ReferencePublicationInputs) -> bytes:
    """Summarize the controller-visible evidence-to-outcome consistency path."""

    document = SvgDocument()
    _title(
        document,
        "Public evidence to TRACE authorization and outcome",
        "All joins use controller-visible identities; hidden lineage is excluded",
    )
    confirmed = sum(
        item.status == "confirmed" for artifact in values.reconciliations for item in artifact.links
    )
    suspected = sum(
        item.status == "suspected" for artifact in values.reconciliations for item in artifact.links
    )
    allocations = sum(item.disposition == "allocated" for item in values.decisions)
    refusals = sum(item.disposition == "refused" for item in values.decisions)
    acquisition = sum(item.disposition == "acquisition-requested" for item in values.decisions)
    boxes = (
        (70, "Public reports", f"{len(values.reports.reports)} raw reports", _BLUE),
        (250, "Evidence graph", f"{confirmed} confirmed / {suspected} suspected", _CYAN),
        (430, "TRACE gate", "versioned evidence and authorization", _ORANGE),
        (610, "Mission decision", f"{allocations} allocate / {refusals} refuse", _GREEN),
        (790, "Outcome", f"{acquisition} acquire-then-reassess", _INK),
    )
    for index, (x, title, detail, color) in enumerate(boxes):
        document.rect(
            x,
            210,
            145,
            135,
            style=SvgBoxStyle(
                fill="#f8fafc",
                stroke=color,
                stroke_width=3,
                radius=8,
            ),
        )
        document.text(
            x + 72,
            250,
            title,
            style=SvgTextStyle(size=14, fill=color, anchor="middle", weight=700),
        )
        document.text(
            x + 72,
            285,
            detail,
            style=SvgTextStyle(size=10, anchor="middle"),
        )
        if index < len(boxes) - 1:
            document.line(
                x + 145,
                277,
                x + 180,
                277,
                style=SvgLineStyle(stroke=_GRAY, width=3),
            )
    document.text(
        500,
        420,
        "Development figure: descriptive mechanics only; validation and policy-effect claims remain deferred",
        style=SvgTextStyle(size=12, fill=_RED, anchor="middle"),
    )
    return document.render(
        title="Reference TRACE consistency flow",
        description="Controller-visible reports, reconciliation, TRACE authorization, decisions, and outcomes.",
    )
