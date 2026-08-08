"""Capability-aware intrinsic and residual capacity accounting."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from trace_jepa.scenario.delta.domain import GeneratedScenario, IncidentTruth, ResourceUnit

from .models import DeltaDecisionEvent, DemandWindow
from .routing import ScenarioIndex


def ratio_milli(demand: int, capacity: int) -> int | None:
    if demand == 0:
        return 0
    if capacity == 0:
        return None
    return round(1_000 * demand / capacity)


class CapacityEvaluator:
    """Evaluate Small's bounded one-resource/one-incident matching problem."""

    def __init__(self, scenario: GeneratedScenario) -> None:
        self.scenario = scenario
        self.index = ScenarioIndex.build(scenario)

    def _unit_is_eligible(
        self,
        unit: ResourceUnit,
        simulation_time_s: int,
        route_id: str,
        busy_intervals: Sequence[tuple[str, int, int | None]],
    ) -> bool:
        committed = any(
            resource_id == unit.resource_id
            and interval_start <= simulation_time_s < int(interval_end)
            for resource_id, interval_start, interval_end in busy_intervals
            if interval_end is not None
        )
        return (
            unit.is_available
            and unit.available_from_s <= simulation_time_s
            and not committed
            and self.index.travel_seconds(unit, simulation_time_s, route_id) is not None
        )

    def strict_matched_units(
        self,
        active: Sequence[IncidentTruth],
        simulation_time_s: int,
        busy_intervals: Sequence[tuple[str, int, int | None]],
    ) -> int:
        """Maximize covered units with one physical resource per incident."""

        incidents = sorted(active, key=lambda item: item.incident_id)
        if not incidents:
            return 0
        routes = [self.index.incident_route(incident) for incident in incidents]
        states: set[int] = {0}
        for unit in sorted(self.scenario.resources.units, key=lambda item: item.resource_id):
            compatible = [
                incident_index
                for incident_index, incident in enumerate(incidents)
                if incident.required_capability in unit.capabilities
                and unit.service_units >= incident.service_units
                and self._unit_is_eligible(
                    unit,
                    simulation_time_s,
                    routes[incident_index],
                    busy_intervals,
                )
            ]
            next_states = set(states)
            for state in states:
                for incident_index in compatible:
                    bit = 1 << incident_index
                    if state & bit == 0:
                        next_states.add(state | bit)
            states = next_states
        return max(
            (
                sum(
                    incident.service_units
                    for incident_index, incident in enumerate(incidents)
                    if state & (1 << incident_index)
                )
                for state in states
            ),
            default=0,
        )

    def uncapped_units(
        self,
        active: Sequence[IncidentTruth],
        simulation_time_s: int,
        busy_intervals: Sequence[tuple[str, int, int | None]],
    ) -> int:
        if not active:
            return 0
        routes = {incident.incident_id: self.index.incident_route(incident) for incident in active}
        return sum(
            unit.service_units
            for unit in sorted(self.scenario.resources.units, key=lambda item: item.resource_id)
            if any(
                incident.required_capability in unit.capabilities
                and self._unit_is_eligible(
                    unit,
                    simulation_time_s,
                    routes[incident.incident_id],
                    busy_intervals,
                )
                for incident in active
            )
        )

    def historical_capped_units(
        self,
        active: Sequence[IncidentTruth],
        simulation_time_s: int,
        busy_intervals: Sequence[tuple[str, int, int | None]],
    ) -> int:
        demand_by_key: dict[tuple[str, str], int] = defaultdict(int)
        for incident in active:
            route_id = self.index.incident_route(incident)
            demand_by_key[(incident.required_capability, route_id)] += incident.service_units
        keys = sorted(demand_by_key)
        if not keys:
            return 0
        states: set[tuple[int, ...]] = {(0,) * len(keys)}
        for unit in sorted(self.scenario.resources.units, key=lambda item: item.resource_id):
            compatible_indexes = [
                key_index
                for key_index, (capability, route_id) in enumerate(keys)
                if capability in unit.capabilities
                and self._unit_is_eligible(unit, simulation_time_s, route_id, busy_intervals)
            ]
            next_states = set(states)
            for state in states:
                for key_index in compatible_indexes:
                    updated = list(state)
                    updated[key_index] = min(
                        demand_by_key[keys[key_index]],
                        updated[key_index] + unit.service_units,
                    )
                    next_states.add(tuple(updated))
            states = next_states
        return max((sum(state) for state in states), default=0)

    def _covered_incidents(
        self,
        active: Sequence[IncidentTruth],
        simulation_time_s: int,
        allocations: Sequence[DeltaDecisionEvent],
        lineage_by_call: dict[str, str],
    ) -> set[str]:
        active_by_id = {incident.incident_id: incident for incident in active}
        unit_by_id = {unit.resource_id: unit for unit in self.scenario.resources.units}
        covered: set[str] = set()
        for event in allocations:
            if (
                event.service_complete_s is None
                or not event.simulation_time_s <= simulation_time_s < event.service_complete_s
            ):
                continue
            incident = active_by_id.get(lineage_by_call.get(event.call_id, ""))
            unit = unit_by_id.get(event.resource_id)
            if incident is None or unit is None:
                continue
            route_id = self.index.incident_route(incident)
            if (
                incident.required_capability in unit.capabilities
                and unit.service_units >= incident.service_units
                and unit.is_available
                and unit.available_from_s <= event.simulation_time_s
                and self.index.travel_seconds(unit, event.simulation_time_s, route_id) is not None
            ):
                covered.add(incident.incident_id)
        return covered

    def evaluate(self, decisions: list[DeltaDecisionEvent]) -> list[DemandWindow]:
        """Compute intrinsic metrics and post-runtime residual pressure."""

        lineage_by_call = {
            item.call_id: item.truth_incident_id
            for item in self.scenario.observations.lineage
            if item.truth_incident_id is not None
        }
        allocations = [
            event
            for event in decisions
            if event.event_type == "allocation"
            and event.call_id in lineage_by_call
            and event.service_complete_s is not None
        ]
        busy_intervals = [
            (event.resource_id, event.simulation_time_s, event.service_complete_s)
            for event in decisions
            if event.event_type == "allocation" and event.service_complete_s is not None
        ]
        return [
            self._window(start, allocations, busy_intervals, lineage_by_call)
            for start in range(
                0,
                self.scenario.config.timeline.duration_s,
                self.scenario.config.demand_capacity.window_s,
            )
        ]

    def _window(
        self,
        start: int,
        allocations: Sequence[DeltaDecisionEvent],
        busy_intervals: Sequence[tuple[str, int, int | None]],
        lineage_by_call: dict[str, str],
    ) -> DemandWindow:
        active = [
            incident
            for incident in self.scenario.truth.incidents
            if incident.onset_s <= start < incident.onset_s + incident.service_duration_s
        ]
        active_demand = sum(incident.service_units for incident in active)
        strict_capacity = self.strict_matched_units(active, start, ())
        uncapped_capacity = self.uncapped_units(active, start, ())
        historical_capacity = self.historical_capped_units(active, start, ())
        covered_ids = self._covered_incidents(active, start, allocations, lineage_by_call)
        residual = [incident for incident in active if incident.incident_id not in covered_ids]
        residual_demand = sum(incident.service_units for incident in residual)
        commitment_covered = active_demand - residual_demand
        free_strict_capacity = self.strict_matched_units(residual, start, busy_intervals)
        return DemandWindow(
            window_start_s=start,
            active_demand_units=active_demand,
            strict_matched_capacity_units=strict_capacity,
            strict_concurrent_load_ratio_milli=ratio_milli(active_demand, strict_capacity),
            strict_unserviceable=active_demand > 0 and strict_capacity == 0,
            uncapped_compatible_service_unit_capacity_units=uncapped_capacity,
            uncapped_compatible_load_ratio_milli=ratio_milli(active_demand, uncapped_capacity),
            historical_capped_coverable_capacity_units=historical_capacity,
            registered_normalized_coverable_load_index_milli=ratio_milli(
                active_demand, historical_capacity
            ),
            commitment_covered_demand_units=commitment_covered,
            residual_demand_units=residual_demand,
            free_strict_compatible_capacity_units=free_strict_capacity,
            residual_strict_pressure_ratio_milli=ratio_milli(residual_demand, free_strict_capacity),
            residual_strict_unserviceable=(residual_demand > 0 and free_strict_capacity == 0),
        )


def evaluate_capacity_windows(
    scenario: GeneratedScenario,
    decisions: list[DeltaDecisionEvent],
) -> list[DemandWindow]:
    """Compatibility facade for the canonical capacity evaluator."""

    return CapacityEvaluator(scenario).evaluate(decisions)
