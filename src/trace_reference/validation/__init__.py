"""Development-only evaluation for the non-LEAP Reference runtime."""

from .capacity import (
    ReferenceCapacityEvaluator,
    evaluate_reference_capacity,
    maximum_divisible_capped_units,
    maximum_strict_matched_units,
)
from .capacity_models import ReferenceCapacityEvaluation, ReferenceCapacityWindow
from .g3_execution import run_reference_g3_integrity
from .g3_integrity import ReferenceG3IntegrityInput, build_reference_g3_integrity_report
from .models import ReferenceG3IntegrityReport, ReferenceRuntimeCounts
from .statistics import (
    ReferenceClusterInterval,
    ReferenceSeedMetric,
    cluster_bootstrap_mean_interval,
    exact_median_interval,
)

__all__ = [
    "ReferenceCapacityEvaluation",
    "ReferenceCapacityEvaluator",
    "ReferenceCapacityWindow",
    "ReferenceClusterInterval",
    "ReferenceG3IntegrityInput",
    "ReferenceG3IntegrityReport",
    "ReferenceRuntimeCounts",
    "ReferenceSeedMetric",
    "build_reference_g3_integrity_report",
    "cluster_bootstrap_mean_interval",
    "evaluate_reference_capacity",
    "exact_median_interval",
    "maximum_divisible_capped_units",
    "maximum_strict_matched_units",
    "run_reference_g3_integrity",
]
