"""Keep instructor preparation and live teaching resources purpose-specific."""

from __future__ import annotations

from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[1]
INSTRUCTOR_ROOT = LAB_ROOT / "instructor"
PREP = INSTRUCTOR_ROOT / "01_PREP_AND_DISTRIBUTION.md"
FULL = INSTRUCTOR_ROOT / "02_FULL_LESSON_RUN_OF_SHOW.md"
SHORT = INSTRUCTOR_ROOT / "03_90_MINUTE_LESSON.md"
QUICK = INSTRUCTOR_ROOT / "04_LIVE_QUICK_REFERENCE.md"


def test_instructor_resources_are_split_by_job() -> None:
    for document in (PREP, FULL, SHORT, QUICK):
        assert document.is_file()

    assert "Day-before release checklist" in PREP.read_text(encoding="utf-8")
    assert "Schedule at a glance" in FULL.read_text(encoding="utf-8")
    assert "Ninety-Minute Lesson Run of Show" in SHORT.read_text(encoding="utf-8")
    assert "Fast triage" in QUICK.read_text(encoding="utf-8")


def test_preparation_covers_scale_distribution_and_novice_rehearsal() -> None:
    text = PREP.read_text(encoding="utf-8")

    assert "more than 100 college students" in text
    assert "standalone student workspace" in text
    assert "Do not distribute the full instructor branch" in text
    assert "someone who did not author the lab" in text
    assert "Do not release the package if the person must ask where to go next" in text
    assert "Avoid a live dependency" in text


def test_complete_solution_is_easy_for_instructors_to_find() -> None:
    solution = INSTRUCTOR_ROOT / "solution" / "rescue_controller.py"
    source = solution.read_text(encoding="utf-8")

    assert solution.is_file()
    for function_name in (
        "eligible_resources",
        "decide_rescue",
        "apply_visible_repair",
    ):
        assert f"def {function_name}(" in source
    for document in (PREP, FULL, SHORT, QUICK):
        assert "solution/rescue_controller.py" in document.read_text(encoding="utf-8")


def test_full_guide_follows_the_student_and_slide_sequence() -> None:
    text = FULL.read_text(encoding="utf-8")
    headings = (
        "## Opening — Mission and system",
        "## Step 1 — Check setup",
        "## Step 2 — Preview the complete scenario",
        "## Step 3 — Four completed decisions",
        "## Step 4A — TODO 1: eligible resources",
        "## Step 4B — TODO 2: allocate or refuse",
        "## Step 4C — TODO 3: append a repair",
        "## Step 5 — Complete tests and controller run",
        "## Step 6 — Capacity comparison",
        "## Step 7 — Replay the saved histories",
    )
    positions = [text.index(heading) for heading in headings]

    assert positions == sorted(positions)
    assert "Slides:** 1\N{EN DASH}4" in text
    for slide in range(5, 14):
        assert f"**Slide:** {slide}" in text
    assert text.count("### Move on when") >= 9
    assert "Ninety-minute fallback" not in text


def test_short_lesson_is_a_complete_separate_route() -> None:
    text = SHORT.read_text(encoding="utf-8")

    assert "90 minutes" in text
    assert "Students implement TODO 2" in text
    assert "Demonstrate TODO 1" in text
    assert "Demonstrate TODO 3" in text
    assert "If the full lesson must switch to this route" in text
    assert "python workshop.py test 2" in text


def test_quick_reference_contains_every_student_command() -> None:
    text = QUICK.read_text(encoding="utf-8")
    for command in (
        "check",
        "scenario",
        "walkthrough",
        "test 1",
        "test 2",
        "test 3",
        "test all",
        "run",
        "what-if",
        "replay",
        "reset",
    ):
        assert f"python workshop.py {command}" in text
