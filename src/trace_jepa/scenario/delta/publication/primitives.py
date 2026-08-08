"""Deterministic metadata-free SVG and JSON primitives."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

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


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def text(x: float, y: float, value: object, *, size: int = 14, weight: int = 400) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{COLORS["ink"]}">'
        f"{html.escape(str(value))}</text>"
    )


def svg_document(title: str, body: list[str]) -> bytes:
    payload = [
        (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{SVG_WIDTH}" height="{SVG_HEIGHT}" '
            f'viewBox="0 0 {SVG_WIDTH} {SVG_HEIGHT}">'
        ),
        f"<title>{html.escape(title)}</title>",
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        text(36, 40, title, size=22, weight=700),
        *body,
        text(
            36,
            SVG_HEIGHT - 18,
            "WF-DFLD-01-SMALL · simulation-grade teaching artifact · not for navigation",
            size=11,
        ),
        "</svg>",
    ]
    return ("\n".join(payload) + "\n").encode("utf-8")
