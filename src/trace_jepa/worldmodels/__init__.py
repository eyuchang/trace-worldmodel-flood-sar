"""World-model integration contracts and conservative TRACE adapters.

The package deliberately separates frozen visual representation, flood-domain
prediction, calibration, and commitment guarding.  V-JEPA is an encoder here;
it is not relabeled as an action-conditioned flood predictor.
"""

from trace_jepa.worldmodels.adapters import (
    CachedRouteFeatureProvider,
    FeatureObservation,
    FrozenVJEPAFeatureProvider,
    LinearActionHead,
    VJEPARouteWorldModel,
)
from trace_jepa.worldmodels.contracts import (
    RouteWorldModel,
    RouteWorldModelRequest,
    WorldModelProvenance,
    WorldModelInputUnavailable,
)
from trace_jepa.worldmodels.encoding import (
    DeterministicSmokeEncoder,
    ObservationEncodingSummary,
    encode_simulator_observations,
)
from trace_jepa.worldmodels.factory import build_cached_vjepa_route_model
from trace_jepa.worldmodels.simulator_observations import (
    CapturedVisualObservation,
    SimulatorSensorSnapshot,
    SimulatorVisualObservationStore,
    validate_test_authorization,
)
from trace_jepa.worldmodels.versioning import (
    GuardedPolicyEngine,
    ModelQualification,
    ModelRegistry,
)

__all__ = [
    "FeatureObservation",
    "CachedRouteFeatureProvider",
    "FrozenVJEPAFeatureProvider",
    "GuardedPolicyEngine",
    "LinearActionHead",
    "ModelQualification",
    "ModelRegistry",
    "RouteWorldModel",
    "RouteWorldModelRequest",
    "VJEPARouteWorldModel",
    "WorldModelProvenance",
    "WorldModelInputUnavailable",
    "DeterministicSmokeEncoder",
    "ObservationEncodingSummary",
    "encode_simulator_observations",
    "build_cached_vjepa_route_model",
    "CapturedVisualObservation",
    "SimulatorSensorSnapshot",
    "SimulatorVisualObservationStore",
    "validate_test_authorization",
]
