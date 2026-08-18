"""Keep the one student lesson executable, progressive, and jargon-light."""

from __future__ import annotations

import re
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[1]
STUDENT_ROOT = LAB_ROOT / "student"
README = STUDENT_ROOT / "README.md"
INSTRUCTOR_DOCS = tuple((LAB_ROOT / "instructor").glob("*.md"))


def test_all_relative_markdown_links_resolve() -> None:
    link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for document in (README, *INSTRUCTOR_DOCS):
        for target in link_pattern.findall(document.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path_part = target.split("#", maxsplit=1)[0]
            assert (document.parent / path_part).resolve().exists(), (
                f"broken link in {document.name}: {target}"
            )


def test_readme_is_the_only_student_entry_document() -> None:
    assert README.is_file()
    assert not (LAB_ROOT / "START_HERE.md").exists()
    assert not (STUDENT_ROOT / "START_HERE.md").exists()
    assert list(STUDENT_ROOT.glob("*.md")) == [README]


def test_student_commands_use_only_the_workshop_runner() -> None:
    text = README.read_text(encoding="utf-8")
    bash_blocks = re.findall(r"```bash\n(.*?)```", text, flags=re.DOTALL)

    assert bash_blocks
    for block in bash_blocks:
        commands = [line for line in block.splitlines() if line.strip()]
        assert all(line.startswith("python workshop.py") for line in commands)
    assert "TRACE_SMALL_SAR_CONTROLLER" not in text
    assert "trace-jepa-delta-small" not in text
    assert "labs/07_small_sar_codelab" not in text


def test_student_readme_teaches_terms_before_the_numbered_route() -> None:
    text = README.read_text(encoding="utf-8")
    normalized = " ".join(text.split())
    route = text.index("## Your seven-step route")
    required = (
        "Search and rescue (SAR)",
        "TRACE—the system's **decision notebook**",
        "hidden answer key",
        "visible evidence",
        "CLEAR does **not** send a unit",
        "Capacity",
        "Repair",
        "not a physical repair",
    )

    for phrase in required:
        assert phrase in normalized
        assert text.index(phrase) < route


def test_student_lesson_is_sequential_and_has_move_on_checks() -> None:
    text = README.read_text(encoding="utf-8")
    positions = [text.index(f"## Step {number}") for number in range(1, 8)]

    assert positions == sorted(positions)
    assert text.count("**MOVE ON WHEN:**") == 9  # Seven steps plus TODO 1 and TODO 2.
    assert text.count("**GOAL:**") == 7


def test_student_readme_locates_the_visible_decision_outputs() -> None:
    text = README.read_text(encoding="utf-8")
    for filename in (
        "calls.json",
        "evidence_ledger.json",
        "trace_records.json",
        "controller_decisions.json",
        "commitments.json",
        "outcomes.json",
    ):
        assert filename in text


def test_student_lesson_excludes_research_governance_jargon() -> None:
    text = README.read_text(encoding="utf-8").lower()
    for phrase in (
        "artifact-reconstruction",
        "confirmation run",
        "confirmatory evidence",
        "descriptive seed",
        "registered result",
        "registered experiment",
        "holdout",
        "reduced-order",
    ):
        assert phrase not in text


def test_student_lesson_preserves_plain_scientific_boundary() -> None:
    text = README.read_text(encoding="utf-8")

    assert "simulated flood" in text
    assert "hidden answer key" in text
    assert "controller cannot read it" in text
    assert "ground_truth.json" not in text
    assert "call_lineage.json" not in text
    assert "incident_candidate_audit.json" not in text


def test_every_mermaid_diagram_has_a_text_alternative() -> None:
    text = README.read_text(encoding="utf-8")

    assert text.count("```mermaid") == text.count("**Text alternative:**")
