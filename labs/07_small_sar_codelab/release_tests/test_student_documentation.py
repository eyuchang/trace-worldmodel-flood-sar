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


def test_student_commands_use_a_clear_byod_setup_then_one_workshop_runner() -> None:
    text = README.read_text(encoding="utf-8")

    assert "python3 setup_workshop.py" in text
    assert "source .venv/bin/activate" in text
    assert "py setup_workshop.py" in text
    assert ".\\.venv\\Scripts\\Activate.ps1" in text
    assert ".venv\\Scripts\\activate.bat" in text
    assert text.count("python workshop.py") >= 12
    assert "TRACE_SMALL_SAR_CONTROLLER" not in text
    assert "trace-jepa-delta-small" not in text
    assert "labs/07_small_sar_codelab" not in text


def test_student_readme_teaches_terms_before_the_numbered_route() -> None:
    text = README.read_text(encoding="utf-8")
    normalized = " ".join(text.split())
    route = text.index("## Workshop Breakdown")
    required = (
        "Search and rescue (SAR)",
        "TRACE, the system's **decision notebook**",
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


def test_student_readme_makes_the_full_byod_setup_route_explicit() -> None:
    text = README.read_text(encoding="utf-8")

    required = (
        "## Before Step 1 — Set up this laptop",
        "You can complete this workshop on your own laptop.",
        "Python 3.11, 3.12, 3.13, or 3.14",
        "official Python download page",
        "A **virtual environment** is a private Python workspace",
        "they do not download packages",
        "Do not run `pip install` or download a model.",
        "If you later close it",
    )
    for phrase in required:
        assert phrase in text


def test_student_lesson_is_sequential_with_only_useful_progress_signals() -> None:
    text = README.read_text(encoding="utf-8")
    positions = [text.index(f"## Step {number}") for number in range(1, 8)]

    assert positions == sorted(positions)
    assert "**MOVE ON WHEN:**" not in text
    assert text.count("**READY SIGNAL:**") == 1
    assert text.count("**WHEN IT PASSES:**") == 2
    assert text.count("**WHEN ALL TESTS PASS:**") == 1


def test_preview_distinguishes_supplied_system_from_student_code() -> None:
    text = README.read_text(encoding="utf-8")

    assert "small simulated flood session included" in text
    assert "does not call the three unfinished functions" in text
    assert "four representative decisions" in text
    assert "an **allocation**, a **refusal**, or an appended **repair**" in text
    assert "1 allocated, 2 refused, 1 repaired" in text


def test_student_readme_uses_the_text_walkthrough_without_a_viewer() -> None:
    text = README.read_text(encoding="utf-8")

    assert "The command prints the supplied completed decisions in the terminal." in text
    assert "Mission Viewer" not in text
    assert "python workshop.py view" not in text


def test_student_readme_states_return_and_error_contracts() -> None:
    text = README.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    required = (
        "### What each function must return",
        "Return `()` when no unit is eligible.",
        "Raise `ValueError` only when the request and TRACE authorization",
        "A `HOLD` decision and a lack of capacity are normal controller outcomes.",
        "one `RescueDecision` in every normal case",
        "The test checks the exception type, not the exact wording",
        "If any requirement in this list fails, raise `ValueError`",
        "event type `REPAIR`",
        "selected_resource_id=None",
        "all twelve behavior tests",
    )
    for phrase in required:
        assert phrase in normalized


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
