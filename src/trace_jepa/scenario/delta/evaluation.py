"""One-release compatibility facade for Delta evaluation."""

from trace_jepa.scenario.delta.reconciliation.evaluation import (
    ReconciliationEvaluation,
    evaluate_partitions,
    evaluate_reconciliation,
)

__all__ = [
    "ReconciliationEvaluation",
    "evaluate_partitions",
    "evaluate_reconciliation",
]
