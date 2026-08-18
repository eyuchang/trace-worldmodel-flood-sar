"""End-to-end checks for the public-only teaching runtime."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _support import runtime


def test_public_book_walkthrough_needs_no_student_or_solution_code() -> None:
    report = runtime.run_lab("book", "all")

    assert report["controller"] == "public-book-records"
    assert report["scenario_files_modified"] is False
    assert [item["case_id"] for item in report["results"]] == [
        "allocation",
        "evidence_hold",
        "capacity_refusal",
        "visible_repair",
    ]


def test_solution_runs_all_four_public_cases() -> None:
    report = runtime.run_lab("solution", "all")

    assert report["scenario_files_modified"] is False
    assert [item["case_id"] for item in report["results"]] == [
        "allocation",
        "evidence_hold",
        "capacity_refusal",
        "visible_repair",
    ]
    assert report["results"][0]["public_observed_outcome"] == "completed_within_window"
    assert report["results"][3]["new_commitment_created"] is False


def test_teaching_variants_change_capacity_not_trace() -> None:
    no_capacity = runtime.run_lab("solution", "allocation", "no-capacity")
    restored = runtime.run_lab("solution", "capacity_refusal", "restore-capacity")

    first = no_capacity["results"][0]["student_decision"]
    second = restored["results"][0]["student_decision"]
    assert first["trace_decision"] == "clear"
    assert first["event_type"] == "refusal"
    assert first["reason_code"] == "no_compatible_capacity"
    assert second["trace_decision"] == "clear"
    assert second["event_type"] == "allocation"
    assert no_capacity["results"][0]["scope"] == "what-if resource copy"


def test_runtime_output_is_deterministic() -> None:
    first = runtime.run_lab("solution", "all")
    second = runtime.run_lab("solution", "all")

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert runtime.format_report(first) == runtime.format_report(second)


def test_human_output_teaches_the_decision_path_in_plain_language() -> None:
    text = runtime.format_report(runtime.run_lab("solution", "all"))

    assert "1. Welfare check" in text
    assert "TRACE: CLEAR - continue to the resource check" in text
    assert "2. Levee inspection" in text
    assert "TRACE: HOLD - stop before checking resources" in text
    assert "3. Medical response" in text
    assert "Why: no suitable unit is currently available" in text
    assert "keep allocation v2, then append repair v4" in text
    assert "CLEAR lets the controller check resources; it does not dispatch one" in text


def test_write_report_creates_once_and_refuses_overwrite(tmp_path: Path) -> None:
    report = runtime.run_lab("solution", "allocation")
    output = tmp_path / "teaching-run.json"

    runtime.write_report(report, output)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    with pytest.raises(ValueError, match="overwrite"):
        runtime.write_report(report, output)
    assert not list(tmp_path.glob(".*.tmp"))


def test_write_report_cleans_temporary_file_when_publish_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = runtime.run_lab("solution", "allocation")

    def fail_publish(_source: Path, _destination: Path) -> None:
        raise OSError("simulated publish failure")

    monkeypatch.setattr("_support.runtime.os.link", fail_publish)
    with pytest.raises(OSError, match="simulated publish failure"):
        runtime.write_report(report, tmp_path / "teaching-run.json")

    assert list(tmp_path.iterdir()) == []


def test_invalid_variant_pair_is_rejected() -> None:
    with pytest.raises(ValueError, match="not defined"):
        runtime.run_lab("solution", "evidence_hold", "no-capacity")
