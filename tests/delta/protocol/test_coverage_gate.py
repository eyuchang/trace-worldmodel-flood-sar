"""Tests for the reviewed Task 1/2 coverage gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trace_jepa.support.coverage import evaluate_coverage


def _write_report(path: Path, *, covered: bool) -> None:
    missing = 0 if covered else 50
    payload = {
        "files": {
            "src/trace_jepa/scenario/delta/runtime/example.py": {
                "summary": {
                    "num_statements": 100,
                    "missing_lines": missing,
                    "num_branches": 100,
                    "missing_branches": missing,
                }
            },
            "src/trace_jepa/scenario/delta/publication/example.py": {
                "summary": {
                    "num_statements": 100,
                    "missing_lines": 100,
                    "num_branches": 100,
                    "missing_branches": 100,
                }
            },
        }
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_coverage_gate_separates_registered_mechanics_from_complete_report(tmp_path: Path) -> None:
    report = tmp_path / "coverage.json"
    _write_report(report, covered=True)
    critical, complete = evaluate_coverage(report)
    assert critical.line_percent == 100.0
    assert critical.branch_percent == 100.0
    assert complete.line_percent == 50.0
    assert complete.branch_percent == 50.0


def test_coverage_gate_rejects_report_without_registered_modules(tmp_path: Path) -> None:
    report = tmp_path / "coverage.json"
    report.write_text(
        json.dumps(
            {
                "files": {
                    "unrelated.py": {
                        "summary": {
                            "num_statements": 1,
                            "missing_lines": 0,
                            "num_branches": 0,
                            "missing_branches": 0,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no high-consequence"):
        evaluate_coverage(report)
