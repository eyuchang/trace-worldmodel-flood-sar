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
        "Build an End-to-End TRACE Flood-SAR Controller",
        40,
        (
            "PUBLIC EVIDENCE → TRACE → DISPATCH → COMMITMENT → OUTCOME → REPAIR",
            "No GPU  •  No model download  •  Offline execution",
            "Screen-only review draft — narration supplied as captions",
        ),
        narration=(
            "Welcome. In this lab you will run the delivered TRACE Small Flood-SAR "
            "teaching simulator and finish a controller that turns a TRACE consumer "
            "action plus visible resource state into an allocation or a refusal."
        ),
    ),
    Slide(
        "Learning objectives and scientific scope",
        60,
        (
            "RUN: fresh deterministic Small scenario and exact replay",
            "TRACE: follow public evidence and exact record versions",
            "BUILD: deterministic dispatch, refusal, and append-only repair",
            "EXPLAIN: why CLEAR is necessary but not sufficient for allocation",
            "BOUNDARY: synthetic, reduced-order, non-operational teaching system",
            "Debate and regret are separate workshop components.",
        ),
        narration=(
            "The goal is one complete, understandable rescue path, not a "
            "reimplementation of the full research simulator. Small is synthetic and "
            "reduced-order, and student variants are not research results."
        ),
    ),
    Slide(
        "Architecture: who owns each decision?",
        75,
        (
            "1  Synthetic public call",
            "2  Controller-visible evidence from the Toy teaching predictor",
            "3  TRACE record: claim, evidence refs, verdict, consumer action",
            "4  YOUR CODE: authorization + visible capacity → allocate or refuse",
            "5  Exact record/version → commitment → public observed outcome",
            "6  Later visible report → append-only repair",
            "Latent truth is never an input to the student controller.",
        ),
        narration=(
            "Your code begins at the downstream rescue-controller boundary. It checks "
            "whether TRACE permits use and whether compatible, reachable, available "
            "capacity exists."
        ),
    ),
    Slide(
        "Five-minute offline preflight",
        60,
        (
            "Checks Python, checkout, complete dependencies, public hashes, and temp output.",
            "If a hash fails: replace the checkout; never edit a manifest.",
        ),
        terminal=(
            "(trace-lab) $ .venv/bin/python labs/07_small_sar_codelab/scripts/preflight.py",
            "[PASS] python: Python 3.11 (preferred workshop version)",
            "[PASS] checkout: repository checkout and lab files found",
            "[PASS] dependencies: hash-locked Small runtime dependencies import correctly",
            "[PASS] public-data: public artifact hashes and four teaching chains verified",
            "[PASS] temporary-output: per-student temporary output is writable",
            "READY: no GPU, model checkpoint, or live data connection is needed.",
        ),
        narration=(
            "Preflight performs no network request and does not write scientific artifacts. "
            "Run it before the room starts coding."
        ),
    ),
    Slide(
        "Run Small once, then replay every byte",
        65,
        (
            "These are synthetic controller events—not counts of real rescues.",
            "Replay identity does not establish real-world correctness.",
        ),
        terminal=(
            '(trace-lab) $ sar_work_root="$(mktemp -d)"',
            '(trace-lab) $ trace-jepa-delta-small run --output "$sar_work_root/run"',
            "INFO completed WF-DFLD-01-SMALL: allocated=8 refused=12 repaired=8",
            '(trace-lab) $ trace-jepa-delta-small replay --reference "$sar_work_root/run" …',
            "INFO replay is byte-identical",
        ),
        narration=(
            "The fresh deterministic scenario produces eight allocations, twelve "
            "refusals, and eight visible-evidence repairs. Replay regenerates the run "
            "and compares every byte."
        ),
    ),
    Slide(
        "Four public decision cases",
        90,
        (
            "ALLOCATION — TRACE clear + compatible capacity",
            "EVIDENCE REFUSAL — TRACE hold, even though capacity exists",
            "CAPACITY REFUSAL — TRACE clear, but no compatible capacity",
            "VISIBLE REPAIR — allocation@v2 → repair@v4; no new commitment",
            "The walkthrough renders public book records; it does not reveal the solution.",
        ),
        terminal=(
            "allocation: TRACE=clear -> allocation, resource=RES-ENGINE-01",
            "evidence_hold: TRACE=hold -> refusal (trace_not_clear)",
            "capacity_refusal: TRACE=clear -> refusal (no_compatible_capacity)",
            "visible_repair: allocation@v2 -> repair@v4 (new commitment=false)",
        ),
        narration=(
            "The capacity-refusal case is crucial: TRACE clears, but no compatible "
            "resource is currently available. Authorization and allocation are "
            "different layers."
        ),
    ),
    Slide(
        "TODO 1 — Filter resources deterministically",
        75,
        (
            "Keep only resources that are:",
            "  YES — currently available",
            "  YES — route-reachable",
            "  YES — on the requested route",
            "  YES — capable of the requested service",
            "Sort by (routed_travel_s, resource_id). Never hard-code the example engine.",
        ),
        terminal=(
            "TRACE_SMALL_SAR_CONTROLLER=starter … pytest … -k eligible_resources",
            ".                                                                        [100%]",
        ),
        narration=(
            "The resource ID tie-break prevents input order from changing dispatch when "
            "travel times tie."
        ),
    ),
    Slide(
        "TODO 2 — TRACE authorization plus capacity",
        90,
        (
            "TRACE not CLEAR  + any capacity   → evidence refusal",
            "TRACE CLEAR      + no capacity    → capacity refusal",
            "TRACE CLEAR      + capacity       → allocation",
            "First validate the call and belief cluster. Then apply checks in this order.",
        ),
        narration=(
            "A consumer action other than CLEAR must refuse before dispatch. With CLEAR, "
            "call your resource filter. No eligible resource produces a capacity refusal; "
            "otherwise allocate the first deterministic resource."
        ),
    ),
    Slide(
        "TODO 3 — Append visible-evidence repair",
        75,
        (
            "Require an existing history.",
            "Require the same belief cluster and TRACE record chain.",
            "Require a later version and nonempty visible evidence basis.",
            "Return: old history + one REPAIR event.",
            "Do not erase allocation@v2. Do not create a duplicate commitment.",
        ),
        terminal=("allocation@v2  ───────────────→  repair@v4", "      retained       appended"),
        narration=(
            "Append-only history lets a reviewer see what the controller represented and "
            "why it acted at each time."
        ),
    ),
    Slide(
        "Focused tests, then your end-to-end run",
        60,
        (
            "Tests cover normal decisions, malformed links, visible-only access, hashes,",
            "protected output paths, documentation, and determinism.",
        ),
        terminal=(
            "(trace-lab) $ TRACE_SMALL_SAR_CONTROLLER=starter … pytest -q …/tests",
            "...................                                                      [100%]",
            "19 passed",
            "(trace-lab) $ python …/lab_runtime.py --controller starter --case all",
            "Scope: public Small artifacts; lab-only controller; registered result untouched.",
        ),
        narration=(
            "Your decisions should match the public walkthrough. The scaffold owns artifact "
            "loading and contract validation; your code owns downstream controller choices."
        ),
    ),
    Slide(
        "Teaching-only capacity comparisons",
        75,
        (
            "NO CAPACITY:  TRACE clear → refusal (no_compatible_capacity)",
            "RESTORED:     TRACE clear → allocation (allocated_compatible_capacity)",
            "TEACHING-ONLY — copied resource view; canonical TRACE and book unchanged",
            "Do not pool these outputs or call them an experiment.",
        ),
        narration=(
            "The variants alter copied lab resource views only. They show the layer boundary "
            "without changing TRACE, the canonical book, or a registered result."
        ),
    ),
    Slide(
        "Replay the committed book",
        60,
        (
            "Reference: wf_dfld_01_small_book_v6",
            "Bound report: WF_DFLD_01_SMALL_VALIDATION_V6.json",
            "Expected: replay is byte-identical to the committed book",
            "Evidence status: authorized artifact-reconstruction replication",
            "Do not call it untouched confirmation.",
        ),
        narration=(
            "The retained evidence follows original and recovery artifact-retention failures. "
            "Describe that history exactly."
        ),
    ),
    Slide(
        "What you built — and what it does not prove",
        65,
        (
            "DONE — Ran real Small teaching code and exact replay",
            "DONE — Followed public evidence and exact TRACE record versions",
            "DONE — Implemented dispatch, two refusal pathways, and append-only repair",
            "LIMIT — Does not prove claims are true or actions are optimal",
            "LIMIT — Does not establish operational emergency-response validity",
            "LIMIT — Toy predictor and student variants are not effectiveness evidence",
            "The retained book is artifact-reconstruction evidence.",
        ),
        narration=(
            "The audit chain explains what the controller represented and why it acted. It "
            "does not prove real-world truth, optimality, or operational readiness."
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
    title_font = _font(FONT_BOLD, 58)
    body_font = _font(FONT_REGULAR, 34)
    body_bold = _font(FONT_BOLD, 34)
    terminal_font = _font(FONT_REGULAR, 26)
    footer_font = _font(FONT_REGULAR, 24)

    draw.rectangle((0, 0, WIDTH, 14), fill=CYAN)
    draw.text((90, 70), slide.title, font=title_font, fill=TEXT)
    draw.text((90, 148), f"{index:02d} / {len(SLIDES):02d}", font=footer_font, fill=CYAN)

    body_lines = _wrapped(slide.body, 82)
    body_top = 210
    terminal_height = 330 if slide.terminal else 0
    body_bottom = HEIGHT - 110 - terminal_height
    line_height = 48
    for line_index, line in enumerate(body_lines):
        y = body_top + line_index * line_height
        if y > body_bottom:
            break
        color = TEXT
        font = body_font
        if any(token in line for token in ("BOUNDARY:", "TEACHING-ONLY", "not ", "LIMIT")):
            color = AMBER
        if any(token in line for token in ("YES", "DONE", "YOUR CODE", "ALLOCATION")):
            color = GREEN
        if line[:2].isdigit() or line.startswith(("RUN:", "TRACE:", "BUILD:", "EXPLAIN:")):
            font = body_bold
            color = CYAN
        draw.text((110, y), line, font=font, fill=color)

    if slide.terminal:
        top = HEIGHT - 390
        draw.rounded_rectangle((85, top, WIDTH - 85, HEIGHT - 82), radius=20, fill=PANEL)
        draw.text((115, top + 20), "TERMINAL / EXPECTED OUTPUT", font=footer_font, fill=CYAN)
        for line_index, line in enumerate(slide.terminal):
            y = top + 66 + line_index * 37
            if y > HEIGHT - 110:
                break
            color = GREEN if line.startswith(("[PASS]", "READY", "INFO", "19 passed")) else TEXT
            draw.text((115, y), line[:108], font=terminal_font, fill=color)

    draw.text(
        (90, HEIGHT - 52),
        "TRACE Small SAR  •  screen-only local review draft  •  no personal content",
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
            "title=TRACE Small SAR screen-only review draft",
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
