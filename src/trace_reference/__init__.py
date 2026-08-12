"""Development-only companion contracts for WF-DFLD-01-REFERENCE.

The top-level companion package is deliberately outside the delivered Small
scientific-input inventory. It may import stable public TRACE contracts during
design and development, but it exposes no confirmatory seed surface and does not
modify or silently re-freeze Small artifacts.
"""

from .baseline import verify_small_baseline
from .exposure_loading import load_reference_exposure_parameters
from .loading import (
    load_reference_config,
    load_reference_entity_source_crosswalk,
    load_reference_gauge_research,
    load_reference_governance,
    load_reference_source_requirements,
    load_reference_source_research,
    load_reference_topology_design,
)
from .models import ReferenceScenarioConfig
from .physical_loading import load_reference_physical_parameters
from .protocol import REFERENCE_PROTOCOL
from .resource_loading import load_reference_resource_parameters
from .seeds import derive_study_seed

__all__ = [
    "REFERENCE_PROTOCOL",
    "ReferenceScenarioConfig",
    "derive_study_seed",
    "load_reference_config",
    "load_reference_entity_source_crosswalk",
    "load_reference_exposure_parameters",
    "load_reference_gauge_research",
    "load_reference_governance",
    "load_reference_physical_parameters",
    "load_reference_resource_parameters",
    "load_reference_source_requirements",
    "load_reference_source_research",
    "load_reference_topology_design",
    "verify_small_baseline",
]
