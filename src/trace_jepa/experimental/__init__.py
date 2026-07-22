"""Experimental-profile extensions, RQ protocol registration, and formal checks."""

from trace_jepa.experimental.formal import (
    FormalRegimeReport,
    run_synthetic_regime_tests,
)
from trace_jepa.experimental.profile import (
    AdequacyStatus,
    ExperimentalProfileExtension,
    PredictorVersionReplacement,
    build_experimental_profile,
)
from trace_jepa.experimental.protocols import (
    HeldOutGateError,
    ProtocolRegistry,
    RQ5Protocol,
    load_rq5_protocol,
    require_protocol_before_held_out,
)
from trace_jepa.experimental.revalidation import (
    CalibrationAdequacyTable,
    RevalidationGuard,
    RevalidationSnapshot,
)

__all__ = [
    "AdequacyStatus",
    "HeldOutGateError",
    "CalibrationAdequacyTable",
    "ExperimentalProfileExtension",
    "FormalRegimeReport",
    "PredictorVersionReplacement",
    "ProtocolRegistry",
    "RQ5Protocol",
    "RevalidationGuard",
    "RevalidationSnapshot",
    "build_experimental_profile",
    "load_rq5_protocol",
    "require_protocol_before_held_out",
    "run_synthetic_regime_tests",
]
