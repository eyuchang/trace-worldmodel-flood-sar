"""End-to-end checks for the public-only teaching runtime."""

from __future__ import annotations

import json
from pathlib import Path

import lab_runtime
import pytest


def test_public_book_walkthrough_needs_no_student_or_solution_code() -> None:
    report = lab_runtime.run_lab("book", "all")

    assert report["controller"] == "public-book-records"
    assert report["registered_result_modified"] is False
    assert [item["case_id"] for item in report["results"]] == [
        "allocation",
        "evidence_hold",
        "capacity_refusal",
        "visible_repair",
    ]


def test_solution_runs_all_four_public_cases() -> None:
    report = lab_runtime.run_lab("solution", "all")

    assert report["registered_result_modified"] is False
    assert [item["case_id"] for item in report["results"]] == [
        "allocation",
        "evidence_hold",
        "capacity_refusal",
        "visible_repair",
    ]
    assert report["results"][0]["public_observed_outcome"] == "completed_within_window"
    assert report["results"][3]["new_commitment_created"] is False


def test_teaching_variants_change_capacity_not_trace() -> None:
    no_capacity = lab_runtime.run_lab("solution", "allocation", "no-capacity")
    restored = lab_runtime.run_lab("solution", "capacity_refusal", "restore-capacity")

    first = no_capacity["results"][0]["student_decision"]
    second = restored["results"][0]["student_decision"]
    assert first["trace_decision"] == "clear"
    assert first["event_type"] == "refusal"
    assert first["reason_code"] == "no_compatible_capacity"
    assert second["trace_decision"] == "clear"
    assert second["event_type"] == "allocation"
    assert no_capacity["results"][0]["scope"] == "teaching-only variant"


def test_runtime_output_is_deterministic() -> None:
    first = lab_runtime.run_lab("solution", "all")
    second = lab_runtime.run_lab("solution", "all")

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert lab_runtime.format_report(first) == lab_runtime.format_report(second)


def test_write_report_creates_once_and_refuses_overwrite(tmp_path: Path) -> None:
    report = lab_runtime.run_lab("solution", "allocation")
    output = tmp_path / "teaching-run.json"

    lab_runtime.write_report(report, output)

    assert json.loads(output.read_text(encoding="utf-8")) == report
    with pytest.raises(ValueError, match="overwrite"):
        lab_runtime.write_report(report, output)
    assert not list(tmp_path.glob(".*.tmp"))


def test_write_report_cleans_temporary_file_when_publish_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = lab_runtime.run_lab("solution", "allocation")

    def fail_publish(_source: Path, _destination: Path) -> None:
        raise OSError("simulated publish failure")

    monkeypatch.setattr("lab_runtime.os.link", fail_publish)
    with pytest.raises(OSError, match="simulated publish failure"):
        lab_runtime.write_report(report, tmp_path / "teaching-run.json")

    assert list(tmp_path.iterdir()) == []


def test_invalid_variant_pair_is_rejected() -> None:
    with pytest.raises(ValueError, match="not defined"):
        lab_runtime.run_lab("solution", "evidence_hold", "no-capacity")
