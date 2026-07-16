from __future__ import annotations

import argparse
from html import escape
from pathlib import Path
from typing import Any

import yaml


DEFAULT_SCENARIO = Path("configs/scenarios/riverside_flood_v1.yaml")
SVG_WIDTH = 1200
SVG_HEIGHT = 760


def load_scenario(path: Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"scenario must be a mapping: {path}")
    return payload


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _svg_document(body: str, *, title: str, width: int = SVG_WIDTH, height: int = SVG_HEIGHT) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"
     viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">{escape(title)}</title>
  <desc id="desc">TRACE-JEPA flood search-and-rescue teaching figure.</desc>
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3"
            orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L0,6 L9,3 z" fill="#334155"/>
    </marker>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#0f172a" flood-opacity="0.18"/>
    </filter>
    <style>
      .title {{ font: 700 28px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; fill: #0f172a; }}
      .subtitle {{ font: 500 16px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; fill: #475569; }}
      .heading {{ font: 700 18px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; fill: #0f172a; }}
      .label {{ font: 600 15px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; fill: #0f172a; }}
      .body {{ font: 400 14px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; fill: #334155; }}
      .small {{ font: 400 12px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; fill: #475569; }}
      .mono {{ font: 500 12px ui-monospace, SFMono-Regular, Menlo, monospace; fill: #1e293b; }}
      .route-label {{ font: 700 14px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; paint-order: stroke; stroke: white; stroke-width: 5px; stroke-linejoin: round; }}
    </style>
  </defs>
  <rect width="100%" height="100%" fill="#f8fafc"/>
  {body}
</svg>
'''


def _line(x1: float, y1: float, x2: float, y2: float, *, dashed: bool = False) -> str:
    dash = ' stroke-dasharray="8 7"' if dashed else ""
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'stroke="#334155" stroke-width="2.2" marker-end="url(#arrow)"{dash}/>'
    )


def _multiline_text(
    x: float,
    y: float,
    lines: list[str],
    *,
    css_class: str = "body",
    line_height: int = 20,
    anchor: str = "start",
) -> str:
    spans = []
    for index, line in enumerate(lines):
        dy = 0 if index == 0 else line_height
        spans.append(f'<tspan x="{x}" dy="{dy}">{escape(line)}</tspan>')
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" class="{css_class}">' + "".join(spans) + "</text>"


def _box(
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    title: str,
    lines: list[str],
    fill: str,
    stroke: str,
    title_class: str = "heading",
) -> str:
    text_y = y + 34
    body = [
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="16" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="2"/>',
        f'<text x="{x + width / 2}" y="{text_y}" text-anchor="middle" class="{title_class}">{escape(title)}</text>',
    ]
    if lines:
        body.append(
            _multiline_text(
                x + width / 2,
                text_y + 28,
                lines,
                css_class="body",
                line_height=20,
                anchor="middle",
            )
        )
    return "\n".join(body)


def render_operational_cast(output_path: Path) -> Path:
    """Render the operational entities and ownership boundaries.

    Planner, World Model, TRACE Gate, and Dispatcher are modules inside one
    Mission Controller. The drone and boat are field agents. The environment
    owns hidden truth. Offline evaluation is outside the command loop.
    """

    parts: list[str] = [
        '<text x="60" y="55" class="title">Operational cast: one controller, two field agents, one world</text>',
        '<text x="60" y="85" class="subtitle">TRACE is a gate inside Mission Control, not a robot, planner, or hidden evaluator.</text>',
    ]

    parts.append(
        _box(
            420,
            108,
            360,
            108,
            title="Incident Commander",
            lines=["External human authority", "Approves consequential dispatch classes"],
            fill="#fff7ed",
            stroke="#c2410c",
        )
    )

    parts.append(
        '<rect x="105" y="262" width="990" height="300" rx="22" fill="#e0e7ff" '
        'stroke="#4338ca" stroke-width="3"/>'
    )
    parts.append('<text x="600" y="300" text-anchor="middle" class="heading">Mission Controller</text>')
    parts.append('<text x="600" y="325" text-anchor="middle" class="small">One central program at the command post</text>')

    module_specs = [
        (135, "Mission State", ["Reported knowledge", "No hidden truth"]),
        (325, "Planner", ["Proposes grounded", "candidate actions"]),
        (515, "World Model", ["Predicts candidate", "consequences"]),
        (705, "TRACE Gate", ["Checks whether", "recorded evidence may", "authorize action"]),
        (895, "Dispatcher", ["Sends only", "cleared commands"]),
    ]
    for x, title, lines in module_specs:
        parts.append(
            _box(
                x,
                365,
                160,
                145,
                title=title,
                lines=lines,
                fill="#ffffff",
                stroke="#6366f1",
                title_class="label",
            )
        )

    parts.append(
        _box(
            55,
            620,
            260,
            105,
            title="Survey Drone",
            lines=["Observes a requested route", "Reports imagery and telemetry"],
            fill="#f5f3ff",
            stroke="#7c3aed",
        )
    )
    parts.append(
        _box(
            470,
            620,
            260,
            105,
            title="Flood Environment",
            lines=["Owns hidden route status", "Produces observations and outcomes"],
            fill="#ecfeff",
            stroke="#0891b2",
        )
    )
    parts.append(
        _box(
            885,
            620,
            260,
            105,
            title="Rescue Boat",
            lines=["Executes an authorized route", "Transports stranded residents"],
            fill="#eff6ff",
            stroke="#2563eb",
        )
    )

    parts.append(
        '<rect x="950" y="112" width="200" height="108" rx="14" fill="#f1f5f9" '
        'stroke="#64748b" stroke-width="2" stroke-dasharray="7 6"/>'
    )
    parts.append('<text x="1050" y="145" text-anchor="middle" class="label">Offline Evaluation</text>')
    parts.append(_multiline_text(1050, 173, ["Reads logs and hidden truth", "only after the episode"], css_class="small", anchor="middle"))

    # Human authorization enters the controller.
    parts.append(_line(600, 216, 600, 260))
    parts.append('<text x="615" y="242" class="small">approval</text>')

    # Field-agent observations go up; cleared commands go down.
    parts.append(_line(185, 620, 215, 562))
    parts.append(_line(245, 562, 215, 620))
    parts.append('<text x="110" y="588" class="small">observations / commands</text>')

    parts.append(_line(1015, 620, 975, 562))
    parts.append(_line(945, 562, 985, 620))
    parts.append('<text x="900" y="588" class="small">telemetry / commands</text>')

    # Environment supplies consequences to the field agents and simulator loop.
    parts.append(_line(470, 676, 315, 676))
    parts.append(_line(730, 676, 885, 676))
    parts.append(_line(600, 620, 600, 562))
    parts.append('<text x="615" y="594" class="small">observations and outcomes</text>')

    # Offline scoring is deliberately outside the operational loop.
    parts.append(_line(1095, 262, 1045, 220, dashed=True))
    parts.append('<text x="1010" y="246" class="small">post-episode only</text>')

    return _write(
        Path(output_path),
        _svg_document("\n".join(parts), title="TRACE-JEPA operational cast"),
    )


def _map_transform(scenario: dict[str, Any]) -> tuple[Any, Any, float, float]:
    x_min, x_max = [float(v) for v in scenario["map"]["x_limits"]]
    y_min, y_max = [float(v) for v in scenario["map"]["y_limits"]]
    left, top, width, height = 85.0, 150.0, 1030.0, 500.0

    def sx(x: float) -> float:
        return left + (x - x_min) / (x_max - x_min) * width

    def sy(y: float) -> float:
        return top + height - (y - y_min) / (y_max - y_min) * height

    return sx, sy, left, top  # type: ignore[return-value]


def _polyline(points: list[list[float]], sx: Any, sy: Any) -> str:
    return " ".join(f"{sx(float(x)):.1f},{sy(float(y)):.1f}" for x, y in points)


def _polygon(points: list[list[float]], sx: Any, sy: Any) -> str:
    return _polyline(points, sx, sy)


def _location_symbol(key: str, x: float, y: float, label: str) -> str:
    colors = {
        "incident_command": "#0f172a",
        "rescue_base": "#1d4ed8",
        "drone_pad": "#7c3aed",
        "riverside_apartments": "#d97706",
    }
    color = colors.get(key, "#334155")
    if key == "drone_pad":
        shape = f'<path d="M{x},{y-11} L{x-11},{y+9} L{x+11},{y+9} Z" fill="{color}" stroke="white" stroke-width="2"/>'
    elif key == "riverside_apartments":
        shape = f'<path d="M{x},{y-12} L{x+4},{y-4} L{x+13},{y-3} L{x+6},{y+3} L{x+8},{y+12} L{x},{y+7} L{x-8},{y+12} L{x-6},{y+3} L{x-13},{y-3} L{x-4},{y-4} Z" fill="{color}" stroke="white" stroke-width="2"/>'
    elif key == "rescue_base":
        shape = f'<rect x="{x-10}" y="{y-10}" width="20" height="20" rx="4" fill="{color}" stroke="white" stroke-width="2"/>'
    else:
        shape = f'<circle cx="{x}" cy="{y}" r="10" fill="{color}" stroke="white" stroke-width="2"/>'
    return shape + f'<text x="{x+16}" y="{y-12}" class="label">{escape(label)}</text>'


def render_map_view(
    scenario: dict[str, Any],
    *,
    view: str,
    output_path: Path,
) -> Path:
    if view not in {"mission_controller_knowledge", "simulation_ground_truth"}:
        raise ValueError(f"unknown view: {view}")

    sx, sy, left, top = _map_transform(scenario)
    title = (
        "Mission Controller knowledge at time zero"
        if view == "mission_controller_knowledge"
        else "Simulation ground truth: withheld from Mission Control"
    )
    subtitle = (
        "The North Channel is unverified. No obstruction is shown because none has been reported."
        if view == "mission_controller_knowledge"
        else "The environment contains a debris obstruction. This view is for teaching and post-episode scoring only."
    )

    parts: list[str] = [
        f'<text x="60" y="55" class="title">{escape(title)}</text>',
        f'<text x="60" y="84" class="subtitle">{escape(subtitle)}</text>',
    ]

    # Mission card.
    mission = scenario["mission"]
    parts.append(
        '<rect x="60" y="103" width="1080" height="55" rx="13" fill="#ffffff" '
        'stroke="#cbd5e1" stroke-width="1.5"/>'
    )
    mission_line = (
        f"Mission: rescue {int(mission['people_to_rescue'])} residents at Riverside Apartments | "
        f"Boat: rescue_boat_1 at Rescue Base | Deadline: {int(mission['deadline_s']) // 60} minutes"
    )
    parts.append(f'<text x="600" y="137" text-anchor="middle" class="label">{escape(mission_line)}</text>')

    # Map frame and flood region.
    parts.append('<rect x="70" y="165" width="1060" height="515" rx="18" fill="#f8fafc" stroke="#94a3b8" stroke-width="2"/>')
    flood = scenario["map"]["flood_polygon"]
    parts.append(
        f'<polygon points="{_polygon(flood, sx, sy)}" fill="#bae6fd" fill-opacity="0.65" '
        'stroke="#0284c7" stroke-width="2"/>'
    )
    parts.append('<text x="600" y="190" text-anchor="middle" class="heading" fill="#075985">Riverside floodplain</text>')

    north = scenario["routes"]["north_channel"]
    south = scenario["routes"]["south_detour"]
    north_points = _polyline(north["waypoints"], sx, sy)
    south_points = _polyline(south["waypoints"], sx, sy)

    if view == "mission_controller_knowledge":
        parts.append(
            f'<polyline points="{north_points}" fill="none" stroke="#64748b" stroke-width="7" '
            'stroke-dasharray="16 11" stroke-linecap="round" stroke-linejoin="round"/>'
        )
        qx, qy = sx(60), sy(64)
        parts.append(f'<circle cx="{qx}" cy="{qy}" r="23" fill="#ffffff" stroke="#64748b" stroke-width="3"/>')
        parts.append(f'<text x="{qx}" y="{qy+8}" text-anchor="middle" class="heading" fill="#475569">?</text>')
        parts.append(f'<text x="{qx}" y="{qy-34}" text-anchor="middle" class="small">current observation required</text>')
        north_label = "North Channel: UNKNOWN"
        north_color = "#475569"
    else:
        parts.append(
            f'<polyline points="{north_points}" fill="none" stroke="#b91c1c" stroke-width="7" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )
        bx, by = north["blockage_position"]
        bx_s, by_s = sx(float(bx)), sy(float(by))
        parts.append(f'<line x1="{bx_s-14}" y1="{by_s-14}" x2="{bx_s+14}" y2="{by_s+14}" stroke="#7f1d1d" stroke-width="7"/>')
        parts.append(f'<line x1="{bx_s+14}" y1="{by_s-14}" x2="{bx_s-14}" y2="{by_s+14}" stroke="#7f1d1d" stroke-width="7"/>')
        parts.append(f'<text x="{bx_s}" y="{by_s-31}" text-anchor="middle" class="label" fill="#7f1d1d">debris obstruction</text>')
        north_label = "North Channel: BLOCKED"
        north_color = "#991b1b"

    parts.append(
        f'<polyline points="{south_points}" fill="none" stroke="#15803d" stroke-width="7" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
    )

    # Route labels.
    nx, ny = sx(42), sy(51)
    sx_label, sy_label = sx(52), sy(18)
    parts.append(f'<text x="{nx}" y="{ny-16}" text-anchor="middle" class="route-label" fill="{north_color}">{escape(north_label)}</text>')
    parts.append(f'<text x="{sx_label}" y="{sy_label+33}" text-anchor="middle" class="route-label" fill="#166534">South Detour: REPORTED OPEN</text>')

    # Locations.
    for key, item in scenario["locations"].items():
        x, y = item["position"]
        parts.append(_location_symbol(key, sx(float(x)), sy(float(y)), str(item["label"])))

    # Legend / information boundary.
    note = (
        "Input to Planner and World Model"
        if view == "mission_controller_knowledge"
        else "Never input to Planner or World Model before observation"
    )
    note_fill = "#ecfdf5" if view == "mission_controller_knowledge" else "#fef2f2"
    note_stroke = "#15803d" if view == "mission_controller_knowledge" else "#b91c1c"
    parts.append(
        f'<rect x="745" y="615" width="355" height="48" rx="12" fill="{note_fill}" stroke="{note_stroke}" stroke-width="2"/>'
    )
    parts.append(f'<text x="922" y="645" text-anchor="middle" class="label" fill="{note_stroke}">{escape(note)}</text>')

    return _write(Path(output_path), _svg_document("\n".join(parts), title=title))


def render_scenario(scenario_path: Path, output: Path) -> dict[str, Path]:
    scenario = load_scenario(scenario_path)
    output = Path(output)
    paths = {
        "operational_cast": render_operational_cast(output / "operational_cast.svg"),
        "mission_controller_knowledge": render_map_view(
            scenario,
            view="mission_controller_knowledge",
            output_path=output / "mission_controller_knowledge.svg",
        ),
        "simulation_ground_truth": render_map_view(
            scenario,
            view="simulation_ground_truth",
            output_path=output / "simulation_ground_truth.svg",
        ),
    }
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render the TRACE-JEPA operational cast and flood-rescue knowledge views"
    )
    parser.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    parser.add_argument("--output", type=Path, default=Path("artifacts/runs/scenario_brief"))
    args = parser.parse_args()
    for name, path in render_scenario(args.scenario, args.output).items():
        print(f"Wrote {name}: {path}")


if __name__ == "__main__":
    main()
