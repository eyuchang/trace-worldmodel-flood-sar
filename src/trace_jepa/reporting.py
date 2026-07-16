from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, Iterable


def format_event(event: dict[str, Any]) -> str:
    seq = int(event["sequence"])
    kind = str(event["event_type"]).replace("_", " ").upper()
    return f"[{seq:02d}] {kind:<18} {event['message']}"


def write_timeline_text(events: Iterable[dict[str, Any]], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [format_event(event) for event in events]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def render_timeline_svg(events: list[dict[str, Any]], path: str | Path) -> Path:
    """Render a dependency-free vertical timeline for teaching and inspection."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    width = 1200
    top = 100
    row_h = 92
    height = top + row_h * len(events) + 70

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        '<style>.title{font:700 30px Arial;fill:#0f172a}.seq{font:700 18px Arial;fill:white}.kind{font:700 17px Arial;fill:#1d4ed8}.body{font:16px Arial;fill:#0f172a}</style>',
        '<text x="70" y="55" class="title">Emergency call to authorized rescue: action timeline</text>',
    ]

    line_x = 105
    if events:
        parts.append(
            f'<line x1="{line_x}" y1="{top}" x2="{line_x}" y2="{top + row_h * (len(events)-1)}" stroke="#94a3b8" stroke-width="5"/>'
        )

    for index, event in enumerate(events):
        y = top + index * row_h
        parts.append(f'<circle cx="{line_x}" cy="{y}" r="25" fill="#1d4ed8"/>')
        parts.append(f'<text x="{line_x}" y="{y+6}" text-anchor="middle" class="seq">{int(event["sequence"]):02d}</text>')
        parts.append(f'<rect x="155" y="{y-31}" width="970" height="63" rx="12" fill="white" stroke="#cbd5e1" stroke-width="2"/>')
        kind = escape(str(event["event_type"]).replace("_", " ").upper())
        message = escape(str(event["message"]))
        parts.append(f'<text x="180" y="{y-5}" class="kind">{kind}</text>')
        parts.append(f'<text x="180" y="{y+20}" class="body">{message}</text>')

    parts.append('</svg>')
    path.write_text("\n".join(parts), encoding="utf-8")
    return path
