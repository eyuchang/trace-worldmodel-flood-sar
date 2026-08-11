"""Development-only companion contracts for WF-DFLD-01-REFERENCE.

The top-level companion package is deliberately outside the delivered Small
scientific-input inventory. It may import stable public TRACE contracts during
design and development, but it exposes no confirmatory seed surface and does not
modify or silently re-freeze Small artifacts.
"""

from .baseline import verify_small_baseline
from .loading import (
    load_reference_config,
    load_reference_gauge_research,
    load_reference_governance,
    load_reference_source_requirements,
    load_reference_source_research,
    load_reference_topology_design,
)
from .models import ReferenceScenarioConfig
from .protocol import REFERENCE_PROTOCOL
from .seeds import derive_study_seed

__all__ = [
    "REFERENCE_PROTOCOL",
    "ReferenceScenarioConfig",
    "derive_study_seed",
    "load_reference_config",
    "load_reference_gauge_research",
    "load_reference_governance",
    "load_reference_source_requirements",
    "load_reference_source_research",
    "load_reference_topology_design",
    "verify_small_baseline",
]
