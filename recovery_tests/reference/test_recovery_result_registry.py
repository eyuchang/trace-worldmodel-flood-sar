"""Verification tests for the committed Reference recovery result."""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from pathlib import Path

import pytest

from trace_jepa.support import sha256_file
from trace_reference_recovery.manifest import verify_recovery_governance_manifest
from trace_reference_recovery.models import RecoveryOriginalReport
from trace_reference_recovery.result_registry import (
    REGISTRY_PATH,
    REPORT_PATH,
    SEED_PLAN_PATH,
    SHARD_ROOT,
    build_original_result_registry,
    verify_original_result_registry,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RESULT_DOCUMENT_PATH = Path(
    "docs/delta/reference/validation/REFERENCE_BASE_VALIDATION_V2_RECOVERY_RESULT.md"
)
README_PATH = Path("README.md")


def _surface_paths() -> Iterable[Path]:
    yield REGISTRY_PATH
    yield REPORT_PATH
    yield SEED_PLAN_PATH
    yield from (SHARD_ROOT / f"shard-{index:02d}.json" for index in range(20))


def _copy_surface(repository_root: Path, target_root: Path) -> None:
    for relative_path in _surface_paths():
        target = target_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repository_root / relative_path, target)


def test_committed_recovery_result_registry_is_exact() -> None:
    registry = verify_original_result_registry(REPOSITORY_ROOT)

    assert registry == build_original_result_registry(REPOSITORY_ROOT)
    assert registry.mission_count == 100
    assert registry.result_status == "complete-all-exact-gates-pass"
    assert len(registry.shard_receipts) == 20
    verify_recovery_governance_manifest(REPOSITORY_ROOT)


def test_recovery_result_registry_rejects_report_tampering(
    tmp_path: Path,
) -> None:
    _copy_surface(REPOSITORY_ROOT, tmp_path)
    report_path = tmp_path / REPORT_PATH
    report_path.write_bytes(report_path.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="not current"):
        verify_original_result_registry(tmp_path)


def test_recovery_result_registry_rejects_symlinked_shard(
    tmp_path: Path,
) -> None:
    _copy_surface(REPOSITORY_ROOT, tmp_path)
    shard_path = tmp_path / SHARD_ROOT / "shard-00.json"
    outside = tmp_path / "outside-shard.json"
    shutil.copyfile(shard_path, outside)
    shard_path.unlink()
    shard_path.symlink_to(outside)

    with pytest.raises(ValueError, match="symlink"):
        verify_original_result_registry(tmp_path)


def test_documented_recovery_results_match_report() -> None:
    registry = verify_original_result_registry(REPOSITORY_ROOT)
    report = RecoveryOriginalReport.model_validate_json(
        (REPOSITORY_ROOT / REPORT_PATH).read_text("utf-8")
    )
    document = (REPOSITORY_ROOT / RESULT_DOCUMENT_PATH).read_text("utf-8")
    intervals = {item.metric_name: item for item in report.descriptive_intervals}
    rows = (
        ("Evaluation reports", "evaluation_report_count", 2),
        ("Evaluation truth incidents", "evaluation_truth_incident_count", 2),
        ("Evidence-acquisition requests", "acquisition_request_count", 2),
        ("Allocations", "allocation_count", 2),
        ("Refusals", "refusal_count", 2),
        ("Nominal-path compensations", "compensation_count", 2),
        ("Nominal-path consistency debts", "consistency_debt_count", 2),
        ("Peak finite strict concurrent load ratio", "strict_peak_finite_load_ratio", 3),
        ("Strict-unserviceable windows", "strict_unserviceable_window_count", 2),
        (
            "`kappa=0.5` scarcity peak finite strict load ratio",
            "scarcity_peak_finite_strict_load_ratio",
            3,
        ),
        (
            "`kappa=0.5` scarcity strict-unserviceable windows",
            "scarcity_strict_unserviceable_window_count",
            2,
        ),
    )
    for label, metric_name, decimals in rows:
        interval = intervals[metric_name]
        interval_separator = chr(0x2013)
        expected = (
            f"| {label} | {interval.point_micros / 1_000_000:,.{decimals}f} | "
            f"{interval.lower_micros / 1_000_000:,.{decimals}f}{interval_separator}"
            f"{interval.upper_micros / 1_000_000:,.{decimals}f} |"
        )
        assert expected in document
    assert sha256_file(REPOSITORY_ROOT / REPORT_PATH) in document
    assert report.report_digest in document
    assert sha256_file(REPOSITORY_ROOT / SEED_PLAN_PATH) in document
    assert report.seed_list_sha256 in document
    assert registry.registry_digest in document
    assert sha256_file(REPOSITORY_ROOT / REGISTRY_PATH) in document
    assert registry.recovery_governance_aggregate_sha256 in document
    assert report.scientific_input_aggregate_sha256 in document
    assert report.base_freeze_digest in document


def test_readme_reference_summary_matches_report() -> None:
    report = RecoveryOriginalReport.model_validate_json(
        (REPOSITORY_ROOT / REPORT_PATH).read_text("utf-8")
    )
    readme = (REPOSITORY_ROOT / README_PATH).read_text("utf-8")
    intervals = {item.metric_name: item for item in report.descriptive_intervals}
    expected_fragments = (
        f"{intervals['evaluation_report_count'].point_micros / 1_000_000:,.2f} public reports",
        f"{intervals['evaluation_truth_incident_count'].point_micros / 1_000_000:,.2f} latent",
        f"{intervals['allocation_count'].point_micros / 1_000_000:,.2f} allocations",
        f"{intervals['refusal_count'].point_micros / 1_000_000:,.2f} refusals",
        f"ratio was {intervals['strict_peak_finite_load_ratio'].point_micros / 1_000_000:,.3f}",
        f"with {intervals['strict_unserviceable_window_count'].point_micros / 1_000_000:,.2f} strict-unserviceable",
        f"values were {intervals['scarcity_peak_finite_strict_load_ratio'].point_micros / 1_000_000:,.3f} and",
        f"{intervals['scarcity_strict_unserviceable_window_count'].point_micros / 1_000_000:,.2f}",
    )
    for fragment in expected_fragments:
        assert fragment in readme
    assert str(report.execution.workflow_run_id) in readme
    assert "The validation is the frozen **non-LEAP baseline**" in readme
