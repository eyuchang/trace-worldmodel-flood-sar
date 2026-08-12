from __future__ import annotations

from pathlib import Path

from trace_reference.validation import ReferenceG3IntegrityReport, run_reference_g3_integrity

ROOT = Path(__file__).resolve().parents[3]


def test_reference_g3_execution_writes_complete_verified_report(tmp_path: Path) -> None:
    report = run_reference_g3_integrity(ROOT, tmp_path, seed=20260812)
    stored = ReferenceG3IntegrityReport.model_validate_json(
        (tmp_path / "g3_integrity_report.json").read_text(encoding="utf-8")
    )

    assert stored == report
    assert report.all_checks_pass
    assert len(report.observed_fault_families) == 11
    assert report.faulted_counts.compensations == 1
    assert report.faulted_counts.consistency_debts == 1
