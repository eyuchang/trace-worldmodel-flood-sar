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


def test_student_readme_contains_required_claim_boundaries() -> None:
    readme = STUDENT_DOCS[0].read_text(encoding="utf-8")
    normalized = " ".join(readme.split())
    required = (
        "synthetic Flood-SAR teaching simulator",
        "artifact-reconstruction replication",
        "not an operational emergency-response system",
        "Teaching variants",
        "not registered experiments or research results",
        "TRACE `CLEAR` is necessary but not sufficient for allocation",
        "Debate and regret are separate workshop components",
    )

    for phrase in required:
        assert phrase in normalized


def test_documented_walkthrough_matches_runtime_output() -> None:
    readme = STUDENT_DOCS[0].read_text(encoding="utf-8")
    expected_lines = (
        (
            "allocation: TRACE=clear -> allocation (allocated_compatible_capacity), "
            "resource=RES-ENGINE-01"
        ),
        "evidence_hold: TRACE=hold -> refusal (trace_not_clear), resource=none",
        "capacity_refusal: TRACE=clear -> refusal (no_compatible_capacity), resource=none",
        "visible_repair: allocation@v2 -> repair@v4 (new commitment=false)",
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
