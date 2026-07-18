from __future__ import annotations

from enum import Enum
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from trace_jepa.workbench.models import EventType, SimulationEvent, WorkbenchState
from trace_jepa.workbench.reducer import apply_event


class FailureCode(str, Enum):
    INJECTED_DISRUPTION = "injected_disruption"
    STORAGE_INTEGRITY = "storage_integrity"
    CONTRACT_VIOLATION = "contract_violation"
    HARNESS_BUG = "harness_bug"
    MODEL_TRANSIENT = "model_transient"
    SCENARIO_OUTCOME = "scenario_outcome"


class AttributionStatus(str, Enum):
    VERIFIED = "verified"
    QUALIFIED = "qualified"
    UNATTRIBUTABLE = "unattributable"


class RunDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    completed_successfully: bool = False
    registered_disruption_matches: bool = False
    storage_chain_valid: bool = True
    schema_contract_valid: bool = True
    harness_exception: bool = False
    timed_out: bool = False
    model_transient: bool = False
    model_retry_count: int = Field(default=0, ge=0, le=1)
    scenario_failed: bool = False
    attribution_status: AttributionStatus = AttributionStatus.VERIFIED


class FailureClassification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: FailureCode
    attribution_status: AttributionStatus
    retry_model_once: bool = False
    rationale: str


class ExecutionTruthLabel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "trace-execution-truth-v1"
    execution_sequence: int = Field(ge=1)
    action_class: str
    route_id: str | None = None
    truth_safe: bool
    executed_stale: bool
    oracle: str


def adjudicate_execution_truth(
    initial_state: WorkbenchState,
    events: Iterable[SimulationEvent],
) -> dict[int, ExecutionTruthLabel]:
    """Label claim truth from an independent replay immediately before execution."""

    state = initial_state.model_copy(deep=True)
    labels: dict[int, ExecutionTruthLabel] = {}
    eligible_actions = {
        "dispatch_rescue_boat",
        "dispatch_helicopter",
        "deploy_ground_team",
        "evacuate_to_safety",
        "select_dock",
        "rendezvous",
    }
    for event in events:
        if event.event_type == EventType.ACTION_STARTED:
            action_class = str(event.payload["action_type"])
            if action_class not in eligible_actions:
                apply_event(state, event)
                continue
            route_id = event.payload.get("route_id")
            if route_id is not None:
                route_key = str(route_id)
                if route_key not in state.truth.routes:
                    raise ValueError(
                        f"execution {event.sequence} references unknown route {route_key}"
                    )
                truth_safe = state.truth.routes[route_key].open
                oracle = "route_traversability_at_execution_v1"
            elif action_class == "dispatch_helicopter":
                asset_id = str(event.payload["asset_id"])
                asset = state.truth.assets[asset_id]
                truth_safe = state.truth.weather_severity <= asset.weather_tolerance
                oracle = "weather_tolerance_at_execution_v1"
            else:
                # Current G2 eligibility is route/helicopter grounded. Treating
                # an unmodelled claim as true would bias staleness downward.
                raise ValueError(
                    f"no truth oracle is declared for executed action {action_class}"
                )
            labels[event.sequence] = ExecutionTruthLabel(
                execution_sequence=event.sequence,
                action_class=action_class,
                route_id=str(route_id) if route_id is not None else None,
                truth_safe=truth_safe,
                executed_stale=not truth_safe,
                oracle=oracle,
            )
        apply_event(state, event)
    return labels


def classify_failure(diagnostics: RunDiagnostics) -> FailureClassification | None:
    """Apply the paper's fixed-priority, registry-first six-code classifier."""

    if diagnostics.completed_successfully:
        return None
    if diagnostics.registered_disruption_matches:
        return FailureClassification(
            code=FailureCode.INJECTED_DISRUPTION,
            attribution_status=diagnostics.attribution_status,
            rationale="failure matches the predeclared shock registry",
        )
    if not diagnostics.storage_chain_valid:
        return FailureClassification(
            code=FailureCode.STORAGE_INTEGRITY,
            attribution_status=diagnostics.attribution_status,
            rationale="an event or sidecar hash chain failed verification",
        )
    if not diagnostics.schema_contract_valid:
        return FailureClassification(
            code=FailureCode.CONTRACT_VIOLATION,
            attribution_status=diagnostics.attribution_status,
            rationale="an artifact violated its declared schema or contract",
        )
    if diagnostics.harness_exception or diagnostics.timed_out:
        return FailureClassification(
            code=FailureCode.HARNESS_BUG,
            attribution_status=diagnostics.attribution_status,
            rationale=(
                "run timed out after contract checks"
                if diagnostics.timed_out
                else "experiment harness raised an infrastructure exception"
            ),
        )
    if diagnostics.model_transient:
        return FailureClassification(
            code=FailureCode.MODEL_TRANSIENT,
            attribution_status=diagnostics.attribution_status,
            retry_model_once=diagnostics.model_retry_count == 0,
            rationale="model service produced a declared transient failure",
        )
    return FailureClassification(
        code=FailureCode.SCENARIO_OUTCOME,
        attribution_status=diagnostics.attribution_status,
        rationale=(
            "mission failed through the simulated scenario"
            if diagnostics.scenario_failed
            else "no higher-priority infrastructure or registry code applies"
        ),
    )
