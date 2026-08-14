from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
SHARD_REGISTRY = ROOT / "data/scenario/delta/reference_protocol/reference_ci_test_shards_v1.json"
TIMING_AUDIT = (
    ROOT / "data/scenario/delta/reference_protocol/reference_ci_shard_timing_risk_audit_v1.json"
)
MINIMUM_SHARD_TIMEOUT_MINUTES = 60
UPLOAD_ARTIFACT = "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
DOWNLOAD_ARTIFACT = "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093"


def _workflow() -> dict[str, Any]:
    value = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _steps(job: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {step["name"]: step for step in job["steps"] if "name" in step}


def test_reference_ci_runs_every_test_once_in_bounded_registered_shards() -> None:
    workflow = _workflow()
    jobs = workflow["jobs"]
    registry = json.loads(SHARD_REGISTRY.read_text(encoding="utf-8"))
    registered_ids = [item["shard_id"] for item in registry["shards"]]

    quality = jobs["quality"]
    assert quality["timeout-minutes"] >= 45
    assert "Verify complete disjoint test-shard registry" in _steps(quality)
    assert all("pytest" not in str(step.get("run", "")) for step in quality["steps"])

    shards = jobs["test-shards"]
    assert shards["needs"] == "quality"
    assert shards["timeout-minutes"] >= MINIMUM_SHARD_TIMEOUT_MINUTES
    assert shards["strategy"]["fail-fast"] is False
    assert shards["strategy"]["matrix"]["shard"] == registered_ids
    steps = _steps(shards)
    run = steps["Run registered test shard with branch coverage"]["run"]
    assert "scripts/run_ci_test_shard.py" in run
    assert '--shard "${{ matrix.shard }}"' in run
    upload = steps["Upload branch-coverage fragment"]
    assert upload["uses"] == UPLOAD_ARTIFACT
    assert upload["with"]["include-hidden-files"] is True
    assert upload["with"]["if-no-files-found"] == "error"


def test_reference_ci_merges_all_branch_coverage_before_post_test_gates() -> None:
    jobs = _workflow()["jobs"]
    coverage = jobs["coverage"]
    assert coverage["needs"] == "test-shards"
    steps = _steps(coverage)
    download = steps["Download every branch-coverage fragment"]
    assert download["uses"] == DOWNLOAD_ARTIFACT
    assert download["with"]["pattern"] == "delta-coverage-*"
    assert download["with"]["merge-multiple"] is True
    merge = steps["Merge and enforce high-consequence Task 1/2 coverage"]["run"]
    assert "coverage combine coverage-parts" in merge
    assert "coverage json -o coverage-delta.json" in merge
    assert "scripts/check_delta_coverage.py coverage-delta.json" in merge

    post_test = jobs["post-test"]
    assert set(post_test["needs"]) == {"quality", "coverage"}
    post_steps = _steps(post_test)
    assert "Verify immutable Small receipt and current Reference freeze" in post_steps
    freeze_command = post_steps["Verify immutable Small receipt and current Reference freeze"][
        "run"
    ]
    assert "verify_historical_small_scientific_manifest" in freeze_command
    assert "verify_reference_validation_freeze" in freeze_command
    assert "verify_scientific_input_manifest_receipt" not in freeze_command
    assert "Verify the complete Delta scientific input freeze" not in post_steps
    assert "Verify committed Delta book v6 when published" in post_steps
    assert "Reject whitespace errors across the complete branch diff" in post_steps


def test_reference_ci_shard_registry_is_an_exact_disjoint_suite_partition() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_ci_test_shard.py",
            "--repository-root",
            ".",
            "--registry",
            SHARD_REGISTRY.relative_to(ROOT).as_posix(),
            "--verify",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    summary = json.loads(result.stdout)

    assert summary["full_node_count"] == 525
    assert summary["test_file_count"] == 77
    assert sum(summary["shard_counts"].values()) == summary["full_node_count"]


def test_reference_ci_timing_audit_covers_every_registered_shard() -> None:
    registry = json.loads(SHARD_REGISTRY.read_text(encoding="utf-8"))
    audit = json.loads(TIMING_AUDIT.read_text(encoding="utf-8"))
    registered = [item["shard_id"] for item in registry["shards"]]
    audited = [item["shard_id"] for item in audit["shards"]]

    assert audit["schema_version"] == "delta-reference-ci-shard-timing-risk-audit-v1"
    assert audit["infrastructure_timeout_minutes"] == 60
    assert audit["scientific_performance_gate_seconds"] == 900
    assert audited == registered
    assert all(item["expected_within_infrastructure_timeout"] for item in audit["shards"])
    assert all(0 < item["conservative_upper_bound_minutes"] < 60 for item in audit["shards"])

    by_id = {item["shard_id"]: item for item in audit["shards"]}
    assert by_id["reference-g3-characterization"]["evidence_class"] == "observed-github"
    for shard_id in (
        "reference-capacity",
        "reference-publication",
        "reference-g3-characterization",
        "reference-g3-execution",
        "reference-g3-integrity",
        "reference-provenance-bundle",
        "reference-provenance-hidden",
        "reference-provenance-tamper",
        "reference-provenance-replay",
        "reference-phase6",
    ):
        assert by_id[shard_id]["isolated_heavy_fixture"]
