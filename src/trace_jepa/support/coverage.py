"""Coverage accounting for the reviewed high-consequence Task 1/2 surface."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast


class CoverageSummary(TypedDict):
    num_statements: int
    missing_lines: int
    num_branches: int
    missing_branches: int


class CoverageFile(TypedDict):
    summary: CoverageSummary


@dataclass(frozen=True)
class CoverageTotals:
    """Aggregate statement and branch totals from one coverage.py report."""

    statements: int
    missing_lines: int
    branches: int
    missing_branches: int

    @property
    def line_percent(self) -> float:
        return (
            100.0
            if self.statements == 0
            else 100 * (self.statements - self.missing_lines) / self.statements
        )

    @property
    def branch_percent(self) -> float:
        return (
            100.0
            if self.branches == 0
            else 100 * (self.branches - self.missing_branches) / self.branches
        )


HIGH_CONSEQUENCE_PREFIXES = (
    "src/trace_jepa/predictor/",
    "src/trace_jepa/support/",
    "src/trace_jepa/scenario/delta/generation/",
    "src/trace_jepa/scenario/delta/reconciliation/",
    "src/trace_jepa/scenario/delta/runtime/",
)


def _canonical_name(path: str) -> str:
    marker = "src/trace_jepa/"
    normalized = path.replace("\\", "/")
    index = normalized.find(marker)
    return normalized[index:] if index >= 0 else normalized


def _is_high_consequence(path: str) -> bool:
    canonical = _canonical_name(path)
    return canonical.endswith("experimental/revalidation.py") or (
        canonical.startswith(HIGH_CONSEQUENCE_PREFIXES)
        and not canonical.endswith("/__init__.py")
        and not canonical.endswith("support/coverage.py")
        and "/legacy/" not in canonical
    )


def _totals(files: list[CoverageFile]) -> CoverageTotals:
    summaries = [item["summary"] for item in files]
    return CoverageTotals(
        statements=sum(int(summary["num_statements"]) for summary in summaries),
        missing_lines=sum(int(summary["missing_lines"]) for summary in summaries),
        branches=sum(summary["num_branches"] for summary in summaries),
        missing_branches=sum(summary["missing_branches"] for summary in summaries),
    )


def evaluate_coverage(report_path: Path) -> tuple[CoverageTotals, CoverageTotals]:
    """Return registered high-consequence and complete measured totals."""

    report = cast(dict[str, dict[str, CoverageFile]], json.loads(report_path.read_text("utf-8")))
    measured = list(report["files"].values())
    selected = [payload for path, payload in report["files"].items() if _is_high_consequence(path)]
    if not selected:
        raise ValueError("coverage report contains no high-consequence Delta modules")
    return _totals(selected), _totals(measured)
