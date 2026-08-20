"""Release checks for the non-personal YouTube recording package."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

LAB_ROOT = Path(__file__).resolve().parents[1]
VIDEO_ROOT = LAB_ROOT / "instructor" / "video"
VIDEO = VIDEO_ROOT / "review_draft.mp4"
CAPTIONS = VIDEO_ROOT / "review_draft.en.srt"
REQUIRED_TEXT_FILES = (
    "title_description.md",
    "recording_script.md",
    "chapters_and_captions.md",
    "recording_checklist.md",
    "review_draft_notes.md",
    "build_review_draft.py",
)


def _seconds(timestamp: str) -> int:
    hours, minutes, seconds = (int(value) for value in timestamp.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def _require_local_video() -> None:
    """The mp4 is git-ignored (*.mp4), so fresh clones do not contain it."""

    if not VIDEO.is_file():
        pytest.skip(
            "review_draft.mp4 is not in this checkout; build it locally with "
            "instructor/video/build_review_draft.py before releasing"
        )


def test_video_package_is_complete_and_locally_reviewable() -> None:
    for name in REQUIRED_TEXT_FILES:
        assert (VIDEO_ROOT / name).is_file(), name
    _require_local_video()
    assert VIDEO.stat().st_size > 100_000
    assert CAPTIONS.is_file() and CAPTIONS.stat().st_size > 1_000


def test_chapters_are_monotonic_and_match_target_length() -> None:
    chapters = (VIDEO_ROOT / "chapters_and_captions.md").read_text(encoding="utf-8")
    values = re.findall(r"^(\d{2}:\d{2}) ", chapters, flags=re.MULTILINE)
    seconds = [_seconds(f"00:{value}") for value in values]

    assert len(seconds) == 12
    assert seconds == sorted(seconds)
    assert seconds[0] == 0
    assert seconds[-1] == 12 * 60 + 10
    assert 12 * 60 <= 13 * 60 + 25 <= 20 * 60


def test_caption_track_covers_all_twelve_chapters() -> None:
    text = CAPTIONS.read_text(encoding="utf-8")
    blocks = [block for block in text.strip().split("\n\n") if block]

    assert len(blocks) == 12
    assert "00:00:00,000 --> 00:00:35,000" in blocks[0]
    assert "00:12:10,000 --> 00:13:25,000" in blocks[-1]
    assert "append-only decision history" in blocks[-1]


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe not installed")
def test_review_video_stream_duration_resolution_and_privacy_metadata() -> None:
    _require_local_video()
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:format_tags=title:stream=codec_type,width,height",
            "-of",
            "json",
            str(VIDEO),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    probe = json.loads(completed.stdout)
    video_streams = [item for item in probe["streams"] if item["codec_type"] == "video"]
    audio_streams = [item for item in probe["streams"] if item["codec_type"] == "audio"]

    assert len(video_streams) == 1
    assert video_streams[0]["width"] == 1920
    assert video_streams[0]["height"] == 1080
    assert audio_streams == []
    assert float(probe["format"]["duration"]) == pytest.approx(805.04, abs=0.1)
    assert (
        probe["format"]["tags"]["title"]
        == "Flood Rescue Controller student review video"
    )
    assert "/Users/" not in completed.stdout


def test_recording_materials_keep_commands_and_claims_in_bounds() -> None:
    text = "\n".join(
        (VIDEO_ROOT / name).read_text(encoding="utf-8")
        for name in REQUIRED_TEXT_FILES
        if name.endswith(".md")
    )

    assert "trace-jepa-delta-small validate" not in text
    assert "trace-jepa-download" not in text
    assert "--model" not in text
    assert "/tmp" not in text
    assert "/Users/" not in text
    assert "Search and rescue" in text
    assert "decision notebook" in text
    assert "CLEAR allows the resource check" in text
    assert "screen tutorial" in text
    assert "Mission Viewer" not in text
    assert "python workshop.py view" not in text
    assert "python workshop.py" in text
    assert "Set up this laptop" in text
    assert "python3 setup_workshop.py" in text
    assert "same-file" in text
    assert "Stop recording now. Do not show the next command." in text
    assert "Record each numbered section below as a separate take." in text
    assert "does not install packages" in text
    assert "model download" in text
    assert "artifact-reconstruction" not in text
    assert "registered result" not in text
    assert "No upload or personal recording is authorized" in text


def test_video_markdown_links_resolve() -> None:
    pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for document in VIDEO_ROOT.glob("*.md"):
        for target in pattern.findall(document.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            assert (document.parent / target.split("#", maxsplit=1)[0]).resolve().exists()
