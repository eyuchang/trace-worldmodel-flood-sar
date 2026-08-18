"""Generate a silent, screen-only review video and timed caption track."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from PIL import Image, ImageDraw, ImageFont

WIDTH: Final = 1920
HEIGHT: Final = 1080
BACKGROUND: Final = "#08131f"
PANEL: Final = "#10263a"
TEXT: Final = "#f4f7fb"
MUTED: Final = "#b7c8d8"
CYAN: Final = "#42d7e8"
GREEN: Final = "#62d38b"
AMBER: Final = "#ffc857"
FONT_REGULAR: Final = (
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)
FONT_BOLD: Final = (
    Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
)


@dataclass(frozen=True, slots=True)
class Slide:
    title: str
    duration_s: int
    body: tuple[str, ...]
    terminal: tuple[str, ...] = ()
    narration: str = ""


SLIDES: Final = (
    Slide(
        "A flood call arrives. Should we send a unit?",
        35,
        (
            "Your mission: build the controller that makes and explains the decision.",
            "No previous rescue-system experience required.",
            "No GPU or model download.",
        ),
        narration=(
            "A welfare-check call arrives during a simulated flood. Should the software "
            "send a response unit? In this lab, you will program that decision."
        ),
    ),
    Slide(
        "A call becomes a recorded decision",
        65,
        (
            "1  CALL — a request for help",
            "2  EVIDENCE — information the controller is allowed to see",
            "3  TRACE — is the proposed action ready to move forward?",
            "4  YOUR CONTROLLER — is a suitable unit available?",
            "5  SAVED ACTION — allocate or refuse, with a reason",
        ),
        narration=(
            "Search and rescue is the work of finding, reaching, and helping people. "
            "The simulation has a hidden answer key, but the controller cannot read it. "
            "A call produces visible evidence, TRACE checks the information, and your "
            "controller checks the response units before saving an action."
        ),
    ),
    Slide(
        "TRACE checks information. You check resources.",
        70,
        (
            "TRACE CLEAR — information checks passed; continue to resources",
            "TRACE HOLD — information is not ready; stop for now",
            "YOUR CODE — check availability, route, and capability",
            "CLEAR means 'continue.' It does not mean 'send a unit.'",
        ),
        narration=(
            "TRACE is the system's decision notebook. CLEAR permits a resource check. "
            "HOLD stops the controller. Your code then decides whether a suitable unit "
            "can actually be sent."
        ),
    ),
    Slide(
        "Three outcomes: allocate, refuse, repair",
        65,
        (
            "ALLOCATE — select a suitable unit",
            "REFUSE: INFORMATION — TRACE did not clear the action",
            "REFUSE: CAPACITY — no suitable unit is free",
            "REPAIR — append a later correction to the decision history",
            "A repair updates the record; it is not a physical repair.",
        ),
        narration=(
            "An allocation selects a unit, a refusal selects none and explains why, and a "
            "repair appends a later correction without erasing the earlier decision."
        ),
    ),
    Slide(
        "One command checks your setup",
        55,
        (
            "Five PASS lines mean Python, files, packages, examples, and scratch space work.",
            "Share the first failed line with an instructor.",
        ),
        terminal=(
            "$ python workshop.py check",
            "[PASS] python: Python 3.11 is ready",
            "[PASS] workshop-files: guide, exercise, tests, and examples found",
            "[PASS] packages: required Python packages are available",
            "[PASS] examples: four rescue examples are ready",
            "[PASS] workspace: practice output is writable",
            "READY: continue to Step 2 with 'python workshop.py scenario'.",
        ),
        narration=(
            "The setup check confirms the workshop is ready. Continue only after five PASS lines and "
            "READY."
        ),
    ),
    Slide(
        "Run the complete flood scenario",
        70,
        (
            "A scenario is one complete simulated flood-response session.",
            "The run saves the path from call to outcome.",
            "You will replay it after your controller is complete.",
        ),
        terminal=(
            "$ python workshop.py scenario",
            "Scenario complete: 8 allocated, 12 refused, 8 repaired.",
            "Saved decision path:",
            "  call -> evidence -> TRACE record -> controller decision",
            "       -> commitment -> outcome",
        ),
        narration=(
            "Run one complete simulated session. The command saves the public path from "
            "call and evidence through the controller decision, commitment, and outcome."
        ),
    ),
    Slide(
        "Four cases reveal the decision rule",
        95,
        (
            "1  WELFARE CHECK — CLEAR + free unit -> allocate Engine 01",
            "2  LEVEE INSPECTION — HOLD -> refuse; information is too old",
            "3  MEDICAL RESPONSE — CLEAR + no free unit -> refuse for capacity",
            "4  LATER UPDATE — keep allocation v2; append repair v4",
            "KEY IDEA — CLEAR allows a resource check; it does not dispatch a unit.",
        ),
        narration=(
            "The four cases show allocation, information refusal, capacity refusal, and "
            "append-only repair. The medical case proves that CLEAR and allocation are "
            "not the same thing."
        ),
    ),
    Slide(
        "TODO 1: Which units can help?",
        75,
        (
            "KEEP a unit only when all four checks pass:",
            "  available now",
            "  route is reachable",
            "  route matches the request",
            "  unit has the required capability",
            "SORT by travel time, then resource ID, for repeatable results.",
        ),
        terminal=(
            "$ python workshop.py test 1",
            ".                                                                        [100%]",
            "1 passed, 7 deselected",
        ),
        narration=(
            "A capability is a task a unit can perform. Keep only available, reachable, "
            "correct-route units with the needed capability, then sort them deterministically."
        ),
    ),
    Slide(
        "TODO 2: Should we send one?",
        90,
        (
            "TRACE not CLEAR + any resources -> refuse: information",
            "TRACE CLEAR + no eligible unit   -> refuse: capacity",
            "TRACE CLEAR + eligible unit      -> allocate first unit",
            "First verify that the request and TRACE record name the same situation.",
        ),
        narration=(
            "First reject mismatched calls or situations. Then apply TRACE before capacity. "
            "With CLEAR, an empty eligible list refuses; otherwise allocate its first unit."
        ),
    ),
    Slide(
        "TODO 3: New information, same history",
        75,
        (
            "Require the same situation and TRACE record chain.",
            "Require a larger record version and visible evidence for the update.",
            "KEEP allocation v2 in history.",
            "APPEND repair v4.",
            "Do not select the resource again.",
        ),
        terminal=(
            "version 2: allocation stays in history",
            "version 4: repair is appended",
        ),
        narration=(
            "A repair is a later correction to the record. Keep the earlier allocation and "
            "append a new repair only when the update belongs to the same chain."
        ),
    ),
    Slide(
        "Tests show which rule is missing",
        75,
        (
            "Run one TODO test while coding.",
            "Run all student tests when the three functions are complete.",
            "Then run your controller and compare all four decisions.",
        ),
        terminal=(
            "$ python workshop.py test all",
            ".......                                                                  [100%]",
            "8 passed",
            "$ python workshop.py run",
            "Key idea: CLEAR lets the controller check resources; it does not dispatch one.",
        ),
        narration=(
            "A failure name points to the rule that still needs work. When every test passes, "
            "run your controller and compare it with the completed walkthrough."
        ),
    ),
    Slide(
        "Change capacity; watch the decision change",
        65,
        (
            "MAKE WELFARE UNITS BUSY:",
            "  TRACE stays CLEAR -> controller now refuses",
            "MAKE A MEDICAL UNIT AVAILABLE:",
            "  TRACE stays CLEAR -> controller now allocates",
            "Changing capacity can change the result even when TRACE does not change.",
        ),
        narration=(
            "The what-if runs change copied resource snapshots. They isolate the resource "
            "decision: capacity changes the result while TRACE remains CLEAR."
        ),
        terminal=(
            "$ python workshop.py what-if",
            "WHAT IF 1: all welfare-check units are busy? -> REFUSE",
            "WHAT IF 2: a medical-response unit is available? -> ALLOCATE",
        ),
    ),
    Slide(
        "You built the bridge from information to action",
        55,
        (
            "I can explain the path from a flood call to a controller decision.",
            "I can explain why CLEAR is not the same as allocation.",
            "I can explain information refusal versus capacity refusal.",
            "I can append a repair without erasing the earlier decision.",
            "Fresh and saved class runs match byte-for-byte after replay.",
        ),
        narration=(
            "You connected evidence, TRACE, resources, and recorded action. You can now explain "
            "both refusals, deterministic allocation, append-only repair, and exact replay. "
            "Finish with python workshop dot py replay; both saved histories match byte for byte."
        ),
    ),
)


def _font(paths: Sequence[Path], size: int) -> ImageFont.FreeTypeFont:
    for path in paths:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    searched = ", ".join(str(path) for path in paths)
    raise RuntimeError(f"required review-draft font not found; searched: {searched}")


def _wrapped(lines: Sequence[str], width: int) -> list[str]:
    output: list[str] = []
    for line in lines:
        if not line:
            output.append("")
        elif line.startswith("  "):
            output.extend(textwrap.wrap(line, width=width, subsequent_indent="  "))
        else:
            output.extend(textwrap.wrap(line, width=width))
    return output


def render_slide(slide: Slide, index: int, output: Path) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    title_font = _font(FONT_BOLD, 64)
    body_size = 40 if slide.terminal else 48
    body_font = _font(FONT_REGULAR, body_size)
    body_bold = _font(FONT_BOLD, body_size)
    terminal_font = _font(FONT_REGULAR, 28)
    footer_font = _font(FONT_REGULAR, 24)

    draw.rectangle((0, 0, WIDTH, 14), fill=CYAN)
    draw.text((90, 70), slide.title, font=title_font, fill=TEXT)
    draw.text((90, 148), f"{index:02d} / {len(SLIDES):02d}", font=footer_font, fill=CYAN)

    body_lines = _wrapped(slide.body, 70)
    line_height = 56 if slide.terminal else 70
    body_area_top = 220
    body_area_bottom = 605 if slide.terminal else HEIGHT - 105
    body_height = max(line_height, len(body_lines) * line_height)
    body_top = body_area_top + max(0, (body_area_bottom - body_area_top - body_height) // 2)
    for line_index, line in enumerate(body_lines):
        y = body_top + line_index * line_height
        if y > body_area_bottom:
            break
        color = TEXT
        font = body_font
        if any(token in line for token in ("HOLD", "REFUSE", "busy", "not ")):
            color = AMBER
        if any(token in line for token in ("CLEAR", "ALLOCATE", "KEEP", "YOUR CONTROLLER")):
            color = GREEN
        if line[:2].isdigit() or line.startswith(("TRACE", "YOU:", "MAKE ")):
            font = body_bold
            color = CYAN
        draw.text((110, y), line, font=font, fill=color)

    if slide.terminal:
        top = 630
        draw.rounded_rectangle((85, top, WIDTH - 85, HEIGHT - 82), radius=24, fill=PANEL)
        draw.text((115, top + 20), "COMMAND / EXPECTED OUTPUT", font=footer_font, fill=CYAN)
        for line_index, line in enumerate(slide.terminal):
            y = top + 68 + line_index * 38
            if y > HEIGHT - 110:
                break
            color = GREEN if line.startswith(("[PASS]", "READY", "INFO", "8 passed")) else TEXT
            draw.text((115, y), line[:108], font=terminal_font, fill=color)

    draw.text(
        (90, HEIGHT - 52),
        "Flood Rescue Controller  •  Student Code Lab",
        font=footer_font,
        fill=MUTED,
    )
    image.save(output, format="PNG", optimize=True)


def _srt_timestamp(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},000"


def write_captions(output: Path) -> None:
    if output.exists():
        raise ValueError(f"refusing to overwrite captions: {output}")
    start = 0
    blocks: list[str] = []
    for index, slide in enumerate(SLIDES, start=1):
        end = start + slide.duration_s
        narration = slide.narration or " ".join(slide.body)
        blocks.append(
            f"{index}\n{_srt_timestamp(start)} --> {_srt_timestamp(end)}\n{narration}\n"
        )
        start = end
    output.write_text("\n".join(blocks), encoding="utf-8")


def build_video(output: Path, captions: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("FFmpeg is required to build the review draft")
    if output.exists():
        raise ValueError(f"refusing to overwrite video: {output}")
    if captions.exists():
        raise ValueError(f"refusing to overwrite captions: {captions}")
    if not output.parent.is_dir() or not captions.parent.is_dir():
        raise ValueError("output parent directories must already exist")

    with tempfile.TemporaryDirectory(
        prefix=".trace-small-sar-video-",
        dir=output.parent,
    ) as directory:
        temporary = Path(directory)
        concat_lines: list[str] = []
        for index, slide in enumerate(SLIDES, start=1):
            frame = temporary / f"slide-{index:02d}.png"
            render_slide(slide, index, frame)
            concat_lines.extend((f"file '{frame}'", f"duration {slide.duration_s}"))
        concat_lines.append(f"file '{frame}'")
        concat_file = temporary / "slides.ffconcat"
        concat_file.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
        temporary_output = temporary / "review-draft.mp4"

        command = [
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
            str(concat_file),
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
        ]
        subprocess.run(command, check=True, timeout=180)
        os.replace(temporary_output, output)
    write_captions(captions)


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
    print(f"review draft ready: {args.output}")
    print(f"captions ready: {args.captions}")
    print(f"duration: {sum(slide.duration_s for slide in SLIDES) // 60}:"
          f"{sum(slide.duration_s for slide in SLIDES) % 60:02d}; audio: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
