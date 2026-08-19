"""Build a silent text-screen preflight for the Small SAR code-along."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from PIL import Image, ImageDraw, ImageFont

WIDTH: Final = 1920
HEIGHT: Final = 1080
BACKGROUND: Final = "#101418"
PANEL: Final = "#151b21"
TERMINAL: Final = "#0a0d10"
BORDER: Final = "#3c4650"
TEXT: Final = "#f5f7f8"
MUTED: Final = "#b8c0c7"
CYAN: Final = "#8bd5e8"
GREEN: Final = "#a6e3a1"
AMBER: Final = "#f9e2af"
RED: Final = "#f38ba8"
FONT_REGULAR: Final = (
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)
FONT_BOLD: Final = (
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
)


@dataclass(frozen=True, slots=True)
class Scene:
    """One text-screen state from the final human recording."""

    key: str
    duration_s: int
    title: str
    caption: str


SCENES: Final = (
    Scene(
        "intro",
        35,
        "The flood-response decision you will build",
        "A welfare-check call becomes a recorded decision.",
    ),
    Scene(
        "readme",
        35,
        "Your one-file workspace",
        "The README is the route map; edit one file and run one command surface.",
    ),
    Scene(
        "check",
        35,
        "Set up this laptop, then check it",
        "The local environment needs no package or model download; five PASS lines mean ready.",
    ),
    Scene(
        "scenario",
        55,
        "Run the supplied Small scenario",
        "The supplied scenario records one allocation, two refusals, and one repair before coding.",
    ),
    Scene(
        "cases",
        55,
        "Read the four completed decision cases",
        "CLEAR allows a resource check; it does not dispatch a unit.",
    ),
    Scene(
        "todo1",
        95,
        "TODO 1: choose eligible units",
        "Pause to try the TODO, then return to the same file to inspect and test the completed function.",
    ),
    Scene(
        "todo2",
        145,
        "TODO 2: allocate or refuse",
        "Pause to try the TODO, then apply TRACE before capacity and test the same file.",
    ),
    Scene(
        "todo3",
        85,
        "TODO 3: append a repair",
        "Pause to try the TODO, then keep the prior allocation and append a later repair.",
    ),
    Scene(
        "complete",
        80,
        "Test and run your controller",
        "The terminal now prints decisions returned by the student's code.",
    ),
    Scene(
        "capacity",
        55,
        "Change capacity while TRACE stays CLEAR",
        "Capacity can change the controller action without changing TRACE.",
    ),
    Scene(
        "replay",
        55,
        "Replay the saved histories",
        "The saved teaching history regenerates byte-identically.",
    ),
    Scene(
        "close",
        75,
        "What students built",
        "A call, TRACE, the controller, and append-only decision history.",
    ),
)


def _font(paths: Sequence[Path], size: int) -> ImageFont.FreeTypeFont:
    for path in paths:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    raise RuntimeError(f"required font not found: {', '.join(str(path) for path in paths)}")


def _text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    content: str,
    *,
    size: int,
    color: str = TEXT,
    bold: bool = False,
) -> None:
    draw.text(
        xy,
        content,
        font=_font(FONT_BOLD if bold else FONT_REGULAR, size),
        fill=color,
    )


def _box(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[int, int, int, int],
    *,
    fill: str,
    outline: str = BORDER,
) -> None:
    draw.rounded_rectangle(bounds, radius=16, fill=fill, outline=outline, width=2)


def _header(draw: ImageDraw.ImageDraw, scene: Scene, index: int) -> None:
    _text(
        draw,
        (70, 50),
        "TRACE SMALL SAR · SCREEN-RECORDING PREFLIGHT",
        size=22,
        color=CYAN,
        bold=True,
    )
    _text(draw, (70, 96), scene.title, size=46, bold=True)
    _text(draw, (1660, 55), f"{index:02d}/{len(SCENES):02d}", size=21, color=MUTED)
    _text(
        draw,
        (70, 1025),
        "Silent review draft — final tutorial is a narrated, real code-along",
        size=20,
        color=MUTED,
    )


def _terminal(draw: ImageDraw.ImageDraw, lines: Sequence[tuple[str, str]]) -> None:
    _box(draw, (120, 250, 1800, 905), fill=TERMINAL, outline="#2f3a43")
    _text(draw, (165, 290), "trace-small-sar-workshop", size=22, color=MUTED)
    for index, (line, color) in enumerate(lines):
        _text(draw, (165, 350 + index * 57), line, size=28, color=color)


def _editor(draw: ImageDraw.ImageDraw, *, label: str, lines: Sequence[tuple[str, str]]) -> None:
    _box(draw, (90, 235, 1830, 920), fill=PANEL)
    _text(draw, (130, 270), "exercise/rescue_controller.py", size=24, bold=True)
    _text(draw, (1645, 270), label, size=20, color=CYAN, bold=True)
    for index, (line, color) in enumerate(lines):
        y = 345 + index * 41
        _text(draw, (130, y), f"{index + 1:>2}", size=21, color=MUTED)
        _text(draw, (195, y), line, size=24, color=color)


def _readme(draw: ImageDraw.ImageDraw, *, closing: bool = False) -> None:
    _box(draw, (90, 240, 1830, 915), fill="#fbfcfd", outline="#aeb9c2")
    dark = "#14212b"
    accent = "#22617a"
    _text(draw, (140, 290), "Flood Rescue Controller Workshop", size=41, color=dark, bold=True)
    if closing:
        _text(draw, (140, 370), "Completion checklist", size=31, color=accent, bold=True)
        rows = (
            "[x] Setup reports READY",
            "[x] Twelve behavior tests pass",
            "[x] Controller produces four expected decisions",
            "[x] Capacity changes the action while TRACE stays CLEAR",
            "[x] Replay is byte-identical",
        )
    else:
        _text(draw, (140, 370), "What system are you building?", size=31, color=accent, bold=True)
        rows = (
            "call -> visible evidence -> TRACE -> controller -> saved action",
            "TRACE: is the information ready to use?",
            "Controller: is a suitable response unit available?",
            "CLEAR means continue to the resource check.",
            "CLEAR does not mean a unit was sent.",
        )
    for index, row in enumerate(rows):
        _text(draw, (165, 470 + index * 72), row, size=27, color=dark, bold=index == 0)


def _draw_scene(scene: Scene, index: int, output: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    _header(draw, scene, index)
    if scene.key in {"intro", "readme"}:
        _readme(draw)
    elif scene.key == "check":
        _terminal(
            draw,
            (
                ("$ python3 setup_workshop.py", TEXT),
                ("SETUP READY: .venv created; no package or model download was needed.", GREEN),
                ("$ source .venv/bin/activate", TEXT),
                ("$ python workshop.py check", TEXT),
                ("[PASS] python: Python 3.12 is ready", GREEN),
                ("[PASS] workshop-files: guide, setup tool, exercise, tests, and teaching data found", GREEN),
                ("[PASS] teaching-data: four public teaching cases are ready", GREEN),
                ("[PASS] tests: Python's built-in test runner is ready", GREEN),
                ("[PASS] workspace: practice output is writable", GREEN),
                ("READY: continue to Step 2 with 'python workshop.py scenario'.", CYAN),
            ),
        )
    elif scene.key == "scenario":
        _terminal(
            draw,
            (
                ("$ python workshop.py scenario", TEXT),
                ("Scenario complete: 1 allocated, 2 refused, 1 repaired.", GREEN),
                ("Saved decision path:", MUTED),
                ("  call -> evidence -> TRACE record -> controller decision", TEXT),
                ("       -> commitment -> outcome", TEXT),
                ("$ python workshop.py walkthrough", TEXT),
            ),
        )
    elif scene.key == "cases":
        _terminal(
            draw,
            (
                ("TRACE Small SAR walkthrough", TEXT),
                ("1. Welfare check", TEXT),
                ("   TRACE: CLEAR - continue to the resource check", GREEN),
                ("   Controller: ALLOCATE RES-ENGINE-01", GREEN),
                ("2. Levee inspection: HOLD -> REFUSE before resource check", AMBER),
                ("3. Medical response: CLEAR -> REFUSE, no suitable unit", AMBER),
                ("4. Later information: keep allocation v2, append repair v4", CYAN),
            ),
        )
    elif scene.key == "todo1":
        _editor(
            draw,
            label="TODO 1 — after pause",
            lines=(
                ("eligible = (", CYAN),
                ("    resource for resource in resources", TEXT),
                ("    if resource.currently_available", TEXT),
                ("    and resource.route_reachable", TEXT),
                ("    and resource.route_id == request.route_id", TEXT),
                ("    and request.required_capability in resource.capabilities", TEXT),
                (")", CYAN),
                ("return tuple(sorted(eligible, key=lambda item: (item.routed_travel_s, item.resource_id)))", GREEN),
            ),
        )
    elif scene.key == "todo2":
        _editor(
            draw,
            label="TODO 2 — after pause",
            lines=(
                ("if authorization.call_id != request.call_id:", CYAN),
                ("    raise ValueError(\"...same call\")", RED),
                ("if authorization.belief_cluster_id != request.belief_cluster_id:", CYAN),
                ("    raise ValueError(\"...same belief cluster\")", RED),
                ("if authorization.decision is not TraceDecision.CLEAR:", CYAN),
                ("    return _decision_from_trace(... REFUSAL, TRACE_NOT_CLEAR)", AMBER),
                ("compatible = eligible_resources(request, resources)", TEXT),
                ("if not compatible:", CYAN),
                ("    return _decision_from_trace(... REFUSAL, NO_COMPATIBLE_CAPACITY)", AMBER),
                ("return _decision_from_trace(... ALLOCATION, compatible[0].resource_id)", GREEN),
            ),
        )
    elif scene.key == "todo3":
        _editor(
            draw,
            label="TODO 3 — after pause",
            lines=(
                ("if not history:", CYAN),
                ("    raise ValueError(\"a repair requires existing history\")", RED),
                ("prior = history[-1]", TEXT),
                ("# Same situation, record chain, later version, visible evidence", MUTED),
                ("repair = _decision_from_trace(", CYAN),
                ("    repair_authorization, RescueEventType.REPAIR,", TEXT),
                ("    ReasonCode.VISIBLE_EVIDENCE_REPAIR,", TEXT),
                (")", CYAN),
                ("return (*history, repair)", GREEN),
            ),
        )
    elif scene.key == "complete":
        _terminal(
            draw,
            (
                ("$ python workshop.py test all", TEXT),
                ("Ran 12 tests in 0.001s", GREEN),
                ("OK", GREEN),
                ("PASS: Run your controller: python workshop.py run", GREEN),
                ("$ python workshop.py run", TEXT),
                ("1. Welfare check      TRACE: CLEAR -> ALLOCATE RES-ENGINE-01", GREEN),
                ("2. Levee inspection   TRACE: HOLD  -> REFUSE", AMBER),
                ("3. Medical response   TRACE: CLEAR -> REFUSE", AMBER),
                ("4. Later information  keep allocation v2, append repair v4", CYAN),
            ),
        )
    elif scene.key == "capacity":
        _terminal(
            draw,
            (
                ("$ python workshop.py what-if", TEXT),
                ("WHAT IF 1: all welfare-check units are busy?", MUTED),
                ("TRACE: CLEAR -> REFUSE: no suitable unit is currently available", AMBER),
                ("", TEXT),
                ("WHAT IF 2: a medical-response unit becomes available?", MUTED),
                ("TRACE: CLEAR -> ALLOCATE: RES-MEDICAL-01", GREEN),
                ("Notice: capacity changed the action while TRACE stayed CLEAR.", CYAN),
            ),
        )
    elif scene.key == "replay":
        _terminal(
            draw,
            (
                ("$ python workshop.py replay", TEXT),
                ("Replay: byte-identical.", GREEN),
                ("COMPLETE: CLEAR permits a resource check; allocation also requires capacity.", CYAN),
            ),
        )
    elif scene.key == "close":
        _readme(draw, closing=True)
    image.save(output, format="PNG", optimize=True)


def _srt_timestamp(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},000"


def _write_captions(output: Path) -> None:
    blocks: list[str] = []
    start = 0
    for index, scene in enumerate(SCENES, start=1):
        end = start + scene.duration_s
        blocks.append(
            f"{index}\n{_srt_timestamp(start)} --> {_srt_timestamp(end)}\n{scene.caption}\n"
        )
        start = end
    output.write_text("\n".join(blocks), encoding="utf-8")


def build_video(output: Path, captions: Path) -> None:
    """Render the text-screen preflight and package it as one silent MP4."""

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("FFmpeg is required to build the review draft")
    if output.exists() or captions.exists():
        raise ValueError("review-draft outputs must not already exist")
    with tempfile.TemporaryDirectory(prefix=".trace-small-sar-video-", dir=output.parent) as directory:
        temporary = Path(directory)
        concat_lines: list[str] = []
        for index, scene in enumerate(SCENES, start=1):
            frame = temporary / f"scene-{index:02d}.png"
            _draw_scene(scene, index, frame)
            concat_lines.extend((f"file '{frame}'", f"duration {scene.duration_s}"))
        concat_lines.append(f"file '{frame}'")
        concat = temporary / "scenes.ffconcat"
        concat.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
        temporary_output = temporary / "review-draft.mp4"
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-n",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat),
                "-vf",
                "format=yuv420p",
                "-fps_mode",
                "vfr",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-tune",
                "stillimage",
                "-bf",
                "0",
                "-g",
                "1",
                "-crf",
                "23",
                "-movflags",
                "+faststart",
                "-an",
                "-metadata",
                "title=Flood Rescue Controller student review video",
                str(temporary_output),
            ],
            check=True,
            timeout=180,
        )
        os.replace(temporary_output, output)
    _write_captions(captions)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--captions", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        build_video(args.output.expanduser(), args.captions.expanduser())
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    total = sum(scene.duration_s for scene in SCENES)
    print(f"review draft ready: {args.output}")
    print(f"captions ready: {args.captions}")
    print(f"duration: {total // 60}:{total % 60:02d}; audio: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
