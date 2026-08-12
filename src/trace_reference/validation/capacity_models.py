"""Typed aggregate-only outputs for offline Reference capacity evaluation."""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel
from trace_jepa.support import canonical_json_bytes


def _ratio_milli(demand: int, capacity: int) -> int | None:
    if demand == 0:
        return 0
    if capacity == 0:
        return None
    return round(1_000 * demand / capacity)


def _finite_peak(windows: tuple[ReferenceCapacityWindow, ...], field: str) -> int:
    values = (getattr(item, field) for item in windows)
    return max((item for item in values if item is not None), default=0)


def _validate_window_ratios(window: ReferenceCapacityWindow) -> None:
    ratio_pairs = (
        (
            window.active_demand_units,
            window.strict_matched_capacity_units,
            window.strict_concurrent_load_ratio_milli,
        ),
        (
            window.active_demand_units,
            window.uncapped_compatible_service_unit_capacity_units,
            window.uncapped_compatible_load_ratio_milli,
        ),
        (
            window.active_demand_units,
            window.historical_divisible_capped_capacity_units,
            window.historical_normalized_coverable_load_index_milli,
        ),
        (
            window.residual_demand_units,
            window.free_strict_compatible_capacity_units,
            window.residual_strict_pressure_ratio_milli,
        ),
    )
    if any(value != _ratio_milli(demand, capacity) for demand, capacity, value in ratio_pairs):
        raise ValueError("Reference capacity ratio is inconsistent with its numerator/denominator")


def _validate_window_bounds(window: ReferenceCapacityWindow) -> None:
    if (window.active_incident_count == 0) != (window.active_demand_units == 0):
        raise ValueError("Reference active incident count and demand disagree")
    if window.commitment_covered_demand_units + window.residual_demand_units != (
        window.active_demand_units
    ):
        raise ValueError("Reference covered plus residual demand must equal active demand")
    if window.strict_matched_capacity_units > window.active_demand_units:
        raise ValueError("Reference strict matched capacity exceeds demand")
    if window.historical_divisible_capped_capacity_units > window.active_demand_units:
        raise ValueError("Reference historical capped capacity exceeds demand")
    if window.free_strict_compatible_capacity_units > window.residual_demand_units:
        raise ValueError("Reference free strict capacity exceeds residual demand")
    if not (
        window.strict_matched_capacity_units
        <= window.historical_divisible_capped_capacity_units
        <= window.uncapped_compatible_service_unit_capacity_units
    ):
        raise ValueError("Reference intrinsic capacity sensitivities are not nested")


class ReferenceCapacityWindow(DeltaModel):
    """One 15-minute offline sample; no hidden entity identifier is serialized."""

    schema_version: Literal["delta-reference-capacity-window-v1"]
    at_s: int = Field(ge=0, lt=345_600)
    active_incident_count: int = Field(ge=0)
    active_demand_units: int = Field(ge=0)
    strict_matched_capacity_units: int = Field(ge=0)
    strict_concurrent_load_ratio_milli: int | None = Field(default=None, ge=0)
    strict_unserviceable: bool
    uncapped_compatible_service_unit_capacity_units: int = Field(ge=0)
    uncapped_compatible_load_ratio_milli: int | None = Field(default=None, ge=0)
    historical_divisible_capped_capacity_units: int = Field(ge=0)
    historical_normalized_coverable_load_index_milli: int | None = Field(default=None, ge=0)
    commitment_covered_demand_units: int = Field(ge=0)
    residual_demand_units: int = Field(ge=0)
    free_strict_compatible_capacity_units: int = Field(ge=0)
    residual_strict_pressure_ratio_milli: int | None = Field(default=None, ge=0)
    residual_strict_unserviceable: bool
    inventory_count: int = Field(ge=0)
    crewed_inventory_count: int = Field(ge=0)
    mobilized_inventory_count: int = Field(ge=0)
    arrived_inventory_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_accounting(self) -> ReferenceCapacityWindow:
        _validate_window_bounds(self)
        if self.strict_unserviceable != (
            self.active_demand_units > 0 and self.strict_matched_capacity_units == 0
        ):
            raise ValueError("Reference strict unserviceable flag is inconsistent")
        if self.residual_strict_unserviceable != (
            self.residual_demand_units > 0 and self.free_strict_compatible_capacity_units == 0
        ):
            raise ValueError("Reference residual unserviceable flag is inconsistent")
        if self.active_demand_units == 0 and any(
            value != 0
            for value in (
                self.strict_concurrent_load_ratio_milli,
                self.uncapped_compatible_load_ratio_milli,
                self.historical_normalized_coverable_load_index_milli,
            )
        ):
            raise ValueError("Reference intrinsic ratios must be zero at zero demand")
        if self.residual_demand_units == 0 and self.residual_strict_pressure_ratio_milli != 0:
            raise ValueError("Reference residual pressure must be zero at zero residual demand")
        _validate_window_ratios(self)
        if not (
            self.arrived_inventory_count <= self.mobilized_inventory_count <= self.inventory_count
        ):
            raise ValueError("Reference activation inventory counts are not nested")
        if self.crewed_inventory_count > self.inventory_count:
            raise ValueError("Reference crewed inventory exceeds physical inventory")
        return self


class ReferenceCapacityEvaluation(DeltaModel):
    """Development-only report of strict and sensitivity load definitions."""

    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    schema_version: Literal["delta-reference-capacity-evaluation-v1"]
    metric_version: Literal["delta-reference-demand-capacity-v1"]
    scientific_status: Literal["development-report-only-no-numerical-load-gate"]
    seed: int = Field(ge=0)
    scenario_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_event_prefix_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    trace_prefix_digest: str = Field(pattern=r"^(GENESIS|[0-9a-f]{64})$")
    evidence_prefix_digest: str = Field(pattern=r"^(GENESIS|[0-9a-f]{64})$")
    commitment_prefix_digest: str = Field(pattern=r"^(GENESIS|[0-9a-f]{64})$")
    fault_profile_id: str = Field(min_length=8)
    evaluation_tick_s: Literal[900]
    window_count: Literal[384]
    windows: tuple[ReferenceCapacityWindow, ...] = Field(min_length=384, max_length=384)
    peak_finite_strict_concurrent_load_ratio_milli: int = Field(ge=0)
    strict_unserviceable_window_count: int = Field(ge=0, le=384)
    peak_finite_uncapped_compatible_load_ratio_milli: int = Field(ge=0)
    uncapped_unserviceable_window_count: int = Field(ge=0, le=384)
    peak_finite_historical_normalized_coverable_load_index_milli: int = Field(ge=0)
    historical_unserviceable_window_count: int = Field(ge=0, le=384)
    peak_finite_residual_strict_pressure_ratio_milli: int = Field(ge=0)
    residual_unserviceable_window_count: int = Field(ge=0, le=384)
    evaluation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_windows(self) -> ReferenceCapacityEvaluation:
        expected_times = tuple(range(0, 345_600, self.evaluation_tick_s))
        if tuple(item.at_s for item in self.windows) != expected_times:
            raise ValueError("Reference capacity windows do not cover the registered grid")
        expected_summary = (
            _finite_peak(self.windows, "strict_concurrent_load_ratio_milli"),
            sum(item.strict_unserviceable for item in self.windows),
            _finite_peak(self.windows, "uncapped_compatible_load_ratio_milli"),
            sum(
                item.active_demand_units > 0
                and item.uncapped_compatible_service_unit_capacity_units == 0
                for item in self.windows
            ),
            _finite_peak(self.windows, "historical_normalized_coverable_load_index_milli"),
            sum(
                item.active_demand_units > 0
                and item.historical_divisible_capped_capacity_units == 0
                for item in self.windows
            ),
            _finite_peak(self.windows, "residual_strict_pressure_ratio_milli"),
            sum(item.residual_strict_unserviceable for item in self.windows),
        )
        actual_summary = (
            self.peak_finite_strict_concurrent_load_ratio_milli,
            self.strict_unserviceable_window_count,
            self.peak_finite_uncapped_compatible_load_ratio_milli,
            self.uncapped_unserviceable_window_count,
            self.peak_finite_historical_normalized_coverable_load_index_milli,
            self.historical_unserviceable_window_count,
            self.peak_finite_residual_strict_pressure_ratio_milli,
            self.residual_unserviceable_window_count,
        )
        if actual_summary != expected_summary:
            raise ValueError("Reference capacity summary disagrees with its windows")
        body = self.model_dump(mode="json", exclude={"evaluation_digest"})
        if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != self.evaluation_digest:
            raise ValueError("Reference capacity evaluation digest is invalid")
        return self
