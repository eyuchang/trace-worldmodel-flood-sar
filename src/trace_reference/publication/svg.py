"""Small deterministic SVG primitives with no ambient metadata."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class SvgLineStyle:
    stroke: str = "#334155"
    width: int = 2
    dash: str | None = None


@dataclass(frozen=True)
class SvgBoxStyle:
    fill: str = "none"
    stroke: str = "none"
    stroke_width: int = 1
    opacity_milli: int = 1000
    radius: int = 0


@dataclass(frozen=True)
class SvgCircleStyle:
    fill: str
    stroke: str = "#ffffff"
    stroke_width: int = 2


@dataclass(frozen=True)
class SvgTextStyle:
    size: int = 14
    fill: str = "#0f172a"
    anchor: str = "start"
    weight: int = 400


_DEFAULT_LINE_STYLE = SvgLineStyle()
_DEFAULT_BOX_STYLE = SvgBoxStyle()
_DEFAULT_TEXT_STYLE = SvgTextStyle()


class SvgDocument:
    """Integer-coordinate SVG builder for reproducible scientific figures."""

    def __init__(self, *, width: int = 1000, height: int = 600) -> None:
        self.width = width
        self.height = height
        self._items: list[str] = []

    def line(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        *,
        style: SvgLineStyle = _DEFAULT_LINE_STYLE,
    ) -> None:
        dashed = "" if style.dash is None else f' stroke-dasharray="{escape(style.dash)}"'
        self._items.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{style.stroke}" stroke-width="{style.width}"{dashed}/>'
        )

    def rect(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        *,
        style: SvgBoxStyle = _DEFAULT_BOX_STYLE,
    ) -> None:
        self._items.append(
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{style.radius}" '
            f'fill="{style.fill}" stroke="{style.stroke}" '
            f'stroke-width="{style.stroke_width}" opacity="{style.opacity_milli / 1000:.3f}"/>'
        )

    def circle(
        self,
        x: int,
        y: int,
        radius: int,
        *,
        style: SvgCircleStyle,
    ) -> None:
        self._items.append(
            f'<circle cx="{x}" cy="{y}" r="{radius}" fill="{style.fill}" '
            f'stroke="{style.stroke}" stroke-width="{style.stroke_width}"/>'
        )

    def polyline(
        self,
        points: tuple[tuple[int, int], ...],
        *,
        style: SvgLineStyle,
        fill: str = "none",
    ) -> None:
        if len(points) < 2:
            return
        encoded = " ".join(f"{x},{y}" for x, y in points)
        dashed = "" if style.dash is None else f' stroke-dasharray="{escape(style.dash)}"'
        self._items.append(
            f'<polyline points="{encoded}" fill="{fill}" stroke="{style.stroke}" '
            f'stroke-width="{style.width}" stroke-linejoin="round"{dashed}/>'
        )

    def text(
        self,
        x: int,
        y: int,
        value: object,
        *,
        style: SvgTextStyle = _DEFAULT_TEXT_STYLE,
    ) -> None:
        self._items.append(
            f'<text x="{x}" y="{y}" font-family="Arial,Helvetica,sans-serif" '
            f'font-size="{style.size}" font-weight="{style.weight}" fill="{style.fill}" '
            f'text-anchor="{style.anchor}">{escape(str(value))}</text>'
        )

    def render(self, *, title: str, description: str) -> bytes:
        body = "".join(self._items)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" '
            f'height="{self.height}" viewBox="0 0 {self.width} {self.height}">'
            f"<title>{escape(title)}</title><desc>{escape(description)}</desc>"
            f'<rect width="100%" height="100%" fill="#ffffff"/>{body}</svg>\n'
        ).encode()
