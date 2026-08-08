"""Typed outputs of the Delta mission runtime and capacity evaluation."""

from __future__ import annotations

from pydantic import Field, model_validator

from trace_jepa.contracts import Commitment, TraceRecord, WorldModelEvidence
from trace_jepa.predictor import PredictorRequest
from trace_jepa.scenario.delta.domain import DeltaModel
from trace_jepa.scenario.delta.evaluation import ReconciliationEvaluation
from trace_jepa.scenario.delta.reconciliation import ReconciliationArtifact


class DeltaDecisionEvent(DeltaModel):
    sequence: int = Field(gt=0)
    call_id: str
    simulation_time_s: int = Field(ge=0)
    event_type: str
    resource_id: str
    reason: str
    visible_evidence_basis: tuple[str, ...] = ()
    belief_cluster_id: str
    trace_decision: str
    trace_record_id: str
    trace_record_version: int = Field(gt=0)
    commitment_id: str | None = None
    scheduled_completion_s: int | None = Field(default=None, ge=0)
    observed_completion_s: int | None = Field(default=None, ge=0)
    censoring_s: int | None = Field(default=None, ge=0)
    outcome_status: str | None = None

    @property
    def service_complete_s(self) -> int | None:
        """Deprecated source alias for the untruncated scheduled completion."""

        return self.scheduled_completion_s


class DemandWindow(DeltaModel):
    """One registered 15-minute capacity-accounting sample."""

    window_start_s: int = Field(ge=0)
    active_demand_units: int = Field(ge=0)
    strict_matched_capacity_units: int = Field(ge=0)
    strict_concurrent_load_ratio_milli: int | None = Field(default=None, ge=0)
    strict_unserviceable: bool
    uncapped_compatible_service_unit_capacity_units: int = Field(ge=0)
    uncapped_compatible_load_ratio_milli: int | None = Field(default=None, ge=0)
    historical_capped_coverable_capacity_units: int = Field(ge=0)
    registered_normalized_coverable_load_index_milli: int | None = Field(default=None, ge=0)
    commitment_covered_demand_units: int = Field(ge=0)
    residual_demand_units: int = Field(ge=0)
    free_strict_compatible_capacity_units: int = Field(ge=0)
    residual_strict_pressure_ratio_milli: int | None = Field(default=None, ge=0)
    residual_strict_unserviceable: bool

    @model_validator(mode="after")
    def validate_capacity_accounting(self) -> DemandWindow:
        if (
            self.commitment_covered_demand_units + self.residual_demand_units
            != self.active_demand_units
        ):
            raise ValueError("covered plus residual demand must equal active demand")
        if self.strict_unserviceable != (
            self.active_demand_units > 0 and self.strict_matched_capacity_units == 0
        ):
            raise ValueError("strict unserviceable status disagrees with demand and capacity")
        if self.residual_strict_unserviceable != (
            self.residual_demand_units > 0 and self.free_strict_compatible_capacity_units == 0
        ):
            raise ValueError("residual unserviceable status disagrees with demand and capacity")
        if self.active_demand_units == 0 and any(
            ratio != 0
            for ratio in (
                self.strict_concurrent_load_ratio_milli,
                self.uncapped_compatible_load_ratio_milli,
                self.registered_normalized_coverable_load_index_milli,
            )
        ):
            raise ValueError("all intrinsic load measures must be zero when demand is zero")
        return self

    @property
    def active_demand_service_units(self) -> int:
        return self.active_demand_units

    @property
    def gross_compatible_capacity_units(self) -> int:
        return self.historical_capped_coverable_capacity_units

    @property
    def gross_load_ratio_milli(self) -> int | None:
        return self.registered_normalized_coverable_load_index_milli

    @property
    def gross_unserviceable(self) -> bool:
        return self.active_demand_units > 0 and self.historical_capped_coverable_capacity_units == 0

    @property
    def residual_unassigned_demand_units(self) -> int:
        return self.residual_demand_units

    @property
    def free_compatible_capacity_units(self) -> int:
        return self.free_strict_compatible_capacity_units

    @property
    def residual_pressure_ratio_milli(self) -> int | None:
        return self.residual_strict_pressure_ratio_milli

    @property
    def residual_unserviceable(self) -> bool:
        return self.residual_strict_unserviceable


class DeltaResourceOutcome(DeltaModel):
    outcome_id: str
    call_id: str
    resource_id: str
    status: str
    scheduled_completion_s: int = Field(ge=0)
    observed_completion_s: int | None = Field(default=None, ge=0)
    censoring_s: int = Field(ge=0)
    authorizing_commitment_id: str
    authorizing_trace_record_id: str
    authorizing_trace_record_version: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_censoring(self) -> DeltaResourceOutcome:
        if self.status == "completed_within_window":
            if self.observed_completion_s != self.scheduled_completion_s:
                raise ValueError("within-window completion must be observed at its scheduled time")
            if self.scheduled_completion_s > self.censoring_s:
                raise ValueError("within-window completion cannot follow censoring")
        elif self.status == "active_at_scenario_censoring":
            if self.observed_completion_s is not None:
                raise ValueError("censored active service has no observed completion")
            if self.scheduled_completion_s <= self.censoring_s:
                raise ValueError("censored active service must complete after censoring")
        else:
            raise ValueError("unknown Delta resource outcome status")
        return self


class DeltaRunResult(DeltaModel):
    """Complete controller-visible runtime result plus offline aggregate scores."""

    schema_version: str
    scenario_id: str
    predictor_version: str
    calibration_version: str
    decisions: list[DeltaDecisionEvent]
    demand_windows: list[DemandWindow]
    trace_records: list[TraceRecord]
    evidence: list[WorldModelEvidence]
    predictor_requests: list[PredictorRequest] = Field(default_factory=list)
    commitments: list[Commitment]
    outcomes: list[DeltaResourceOutcome]
    reconciliation_artifact: ReconciliationArtifact | None = None
    reconciliation_evaluation: ReconciliationEvaluation
    trace_chain_verified: bool
    peak_finite_strict_concurrent_load_ratio_milli: int = Field(ge=0)
    strict_unserviceable_windows: int = Field(ge=0)
    peak_finite_uncapped_compatible_load_ratio_milli: int = Field(ge=0)
    uncapped_unserviceable_windows: int = Field(ge=0)
    peak_finite_registered_normalized_coverable_load_index_milli: int = Field(ge=0)
    historical_capped_unserviceable_windows: int = Field(ge=0)
    peak_finite_residual_strict_pressure_ratio_milli: int = Field(ge=0)
    residual_strict_unserviceable_windows: int = Field(ge=0)
    allocated: int = Field(ge=0)
    refused: int = Field(ge=0)
    repaired: int = Field(ge=0)

    @property
    def peak_demand_capacity_ratio_milli(self) -> int:
        return self.peak_finite_strict_concurrent_load_ratio_milli

    @property
    def peak_strict_concurrent_load_ratio_milli(self) -> int:
        """Deprecated read-only alias for one release."""

        return self.peak_finite_strict_concurrent_load_ratio_milli

    @property
    def peak_uncapped_compatible_load_ratio_milli(self) -> int:
        """Deprecated read-only alias for one release."""

        return self.peak_finite_uncapped_compatible_load_ratio_milli

    @property
    def peak_registered_normalized_coverable_load_index_milli(self) -> int:
        """Deprecated read-only alias for one release."""

        return self.peak_finite_registered_normalized_coverable_load_index_milli

    @property
    def peak_gross_load_ratio_milli(self) -> int:
        return self.peak_finite_registered_normalized_coverable_load_index_milli

    @property
    def gross_unserviceable_windows(self) -> int:
        return self.historical_capped_unserviceable_windows

    @property
    def peak_finite_residual_pressure_ratio_milli(self) -> int:
        return self.peak_finite_residual_strict_pressure_ratio_milli

    @property
    def residual_unserviceable_windows(self) -> int:
        return self.residual_strict_unserviceable_windows

    @property
    def unserviceable_windows(self) -> int:
        return self.residual_strict_unserviceable_windows
