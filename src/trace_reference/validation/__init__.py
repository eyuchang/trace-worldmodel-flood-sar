"""Development-only evaluation for the non-LEAP Reference runtime."""

from .capacity import (
    ReferenceCapacityEvaluator,
    evaluate_reference_capacity,
    maximum_divisible_capped_units,
    maximum_strict_matched_units,
)
from .capacity_models import ReferenceCapacityEvaluation, ReferenceCapacityWindow
from .g3_characterization import run_reference_g3_characterization
from .g3_characterization_models import (
    ReferenceG3ArtifactFamilyDigest,
    ReferenceG3CharacterizationBenchmarkReceipt,
    ReferenceG3CharacterizationFixtureManifest,
    ReferenceG3CharacterizationIndex,
)
from .g3_execution import run_reference_g3_integrity
from .g3_handoff import (
    build_reference_g3_acceptance_receipt,
    build_reference_g3_handoff_manifest,
    write_reference_g3_acceptance_receipt,
    write_reference_g3_handoff_manifest,
    write_reference_scientific_input_manifest,
)
from .g3_handoff_models import (
    REFERENCE_G3_GATE_IDS,
    ReferenceG3AcceptanceReceipt,
    ReferenceG3AcceptanceRegistry,
    ReferenceG3HandoffManifest,
)
from .g3_integrity import ReferenceG3IntegrityInput, build_reference_g3_integrity_report
from .models import ReferenceG3IntegrityReport, ReferenceRuntimeCounts
from .statistics import (
    ReferenceClusterInterval,
    ReferenceSeedMetric,
    cluster_bootstrap_mean_interval,
    exact_median_interval,
)

__all__ = [
    "REFERENCE_G3_GATE_IDS",
    "ReferenceCapacityEvaluation",
    "ReferenceCapacityEvaluator",
    "ReferenceCapacityWindow",
    "ReferenceClusterInterval",
    "ReferenceG3AcceptanceReceipt",
    "ReferenceG3AcceptanceRegistry",
    "ReferenceG3ArtifactFamilyDigest",
    "ReferenceG3CharacterizationBenchmarkReceipt",
    "ReferenceG3CharacterizationFixtureManifest",
    "ReferenceG3CharacterizationIndex",
    "ReferenceG3HandoffManifest",
    "ReferenceG3IntegrityInput",
    "ReferenceG3IntegrityReport",
    "ReferenceRuntimeCounts",
    "ReferenceSeedMetric",
    "build_reference_g3_acceptance_receipt",
    "build_reference_g3_handoff_manifest",
    "build_reference_g3_integrity_report",
    "cluster_bootstrap_mean_interval",
    "evaluate_reference_capacity",
    "exact_median_interval",
    "maximum_divisible_capped_units",
    "maximum_strict_matched_units",
    "run_reference_g3_characterization",
    "run_reference_g3_integrity",
    "write_reference_g3_acceptance_receipt",
    "write_reference_g3_handoff_manifest",
    "write_reference_scientific_input_manifest",
]
