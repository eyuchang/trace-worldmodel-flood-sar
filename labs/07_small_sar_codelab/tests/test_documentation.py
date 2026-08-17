"""Keep student instructions executable, linked, and scientifically bounded."""

from __future__ import annotations

import re
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[1]
STUDENT_DOCS = (LAB_ROOT / "README.md", LAB_ROOT / "START_HERE.md")
INSTRUCTOR_GUIDE = LAB_ROOT / "instructor_guide.md"
ALL_LAB_DOCS = (*STUDENT_DOCS, *((INSTRUCTOR_GUIDE,) if INSTRUCTOR_GUIDE.exists() else ()))


def _text(paths: tuple[Path, ...]) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def test_all_relative_markdown_links_resolve() -> None:
    link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for document in ALL_LAB_DOCS:
        for target in link_pattern.findall(document.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path_part = target.split("#", maxsplit=1)[0]
            assert (document.parent / path_part).resolve().exists(), (
                f"broken link in {document.name}: {target}"
            )


def test_student_commands_exclude_protected_or_obsolete_paths() -> None:
    text = _text(STUDENT_DOCS)

    assert "trace-jepa-delta-small validate" not in text
    assert "trace-jepa-download" not in text
    assert "--model" not in text
    assert "/tmp" not in text
    assert "ground_truth.json" not in text
    assert "call_lineage.json" not in text
    assert "incident_candidate_audit.json" not in text


def test_student_readme_teaches_required_terms_in_plain_language() -> None:
    readme = STUDENT_DOCS[0].read_text(encoding="utf-8")
    normalized = " ".join(readme.split())
    required = (
        "Search and rescue (SAR)",
        "TRACE is the system's **decision notebook**",
        "hidden answer key",
        "controller-visible evidence",
        "CLEAR does **not** send a unit",
        "Capacity",
        "Repair",
        "this is not a physical repair",
        "belief_cluster_id` groups calls",
        "routed_travel_s` is estimated travel time",
        "Byte-identical",
        "An **evidence ledger** is simply the saved log of evidence entries",
        "Everything happens in a simulation for learning",
    )

    for phrase in required:
        assert phrase in normalized


def test_student_lesson_is_story_first_and_progressive() -> None:
    readme = STUDENT_DOCS[0].read_text(encoding="utf-8")

    story = readme.index("Imagine that you are helping a flood-response team")
    system = readme.index("## Meet the system")
    setup = readme.index("## Part 1 — Check your setup")
    run = readme.index("## Part 2 — Run the flood scenario")
    walkthrough = readme.index("## Part 3 — Walk through four rescue decisions")
    build = readme.index("## Part 4 — Build the controller")

    assert story < system < setup < run < walkthrough < build


def test_student_readme_locates_the_visible_decision_outputs() -> None:
    readme = STUDENT_DOCS[0].read_text(encoding="utf-8")

    for filename in (
        "calls",
        "evidence_ledger",
        "trace_records",
        "controller_decisions",
        "commitments",
        "outcomes",
    ):
        assert filename in readme


def test_student_lesson_excludes_research_governance_jargon() -> None:
    text = _text(STUDENT_DOCS).lower()
    excluded = (
        "artifact-reconstruction",
        "confirmation run",
        "confirmatory evidence",
        "descriptive seed",
        "registered result",
        "registered experiment",
        "holdout",
        "reduced-order",
    )

    for phrase in excluded:
        assert phrase not in text


def test_documented_walkthrough_matches_runtime_output() -> None:
    readme = STUDENT_DOCS[0].read_text(encoding="utf-8")
    expected_lines = (
        "1. Welfare check",
        "TRACE: CLEAR - continue to the resource check",
        "Controller: ALLOCATE RES-ENGINE-01",
        "2. Levee inspection",
        "TRACE: HOLD - stop before checking resources",
        "3. Medical response",
        "Why: no suitable unit is currently available",
        "History: keep allocation v2, then append repair v4",
        "CLEAR lets the controller check resources; it does not dispatch one",
    )

    for line in expected_lines:
        assert line in readme


def test_instructor_guide_has_scale_and_fallback_controls() -> None:
    if not INSTRUCTOR_GUIDE.exists():
        return
    guide = INSTRUCTOR_GUIDE.read_text(encoding="utf-8")

    assert "more than 100 college students" in guide
    assert "Ninety-minute fallback" in guide
    assert "No-network fallback" in guide
    assert "someone who did not author the lab" in guide
    assert "Do not distribute the full instructor branch" in guide


def test_every_mermaid_diagram_has_a_text_alternative() -> None:
    readme = STUDENT_DOCS[0].read_text(encoding="utf-8")

    assert readme.count("```mermaid") == readme.count("Text alternative:")
