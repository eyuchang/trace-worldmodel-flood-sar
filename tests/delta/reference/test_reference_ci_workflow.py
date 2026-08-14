from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
MINIMUM_COMPLETE_QUALITY_TIMEOUT_MINUTES = 45


def test_reference_ci_quality_job_allows_complete_coverage_execution() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    quality = workflow["jobs"]["quality"]

    assert quality["timeout-minutes"] >= MINIMUM_COMPLETE_QUALITY_TIMEOUT_MINUTES
    steps = {step.get("name"): step for step in quality["steps"] if "name" in step}
    coverage = steps["Test with registered branch coverage"]
    assert "--cov-branch" in coverage["run"]
    assert not coverage.get("continue-on-error", False)
