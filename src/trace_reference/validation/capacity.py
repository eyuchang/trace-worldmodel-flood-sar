"""Offline capability-, activation-, crew-, and route-aware capacity evaluation."""

from __future__ import annotations

import hashlib
import heapq
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from trace_jepa.support import canonical_json_bytes
from trace_reference.domain import (
    ReferenceResourceActivationPhase,
    ReferenceScenarioArtifacts,
    ReferenceTruthIncident,
)
from trace_reference.domain.resources import (
    ReferencePublicResourceDefinition,
    ReferenceResourceClass,
    ReferenceResourceState,
    ReferenceResourceStateSample,
)
from trace_reference.runtime.mission_state import (
    ReferenceMissionRun,
    reference_scenario_input_digest,
)

from .capacity_models import ReferenceCapacityEvaluation, ReferenceCapacityWindow

_AIR_CLASSES = frozenset(
    {
        ReferenceResourceClass.ROTARY_HOIST,
        ReferenceResourceClass.ROTARY_RECON,
        ReferenceResourceClass.SMALL_UAS,
    }
)
_WATER_CLASSES = frozenset({ReferenceResourceClass.RESCUE_BOAT, ReferenceResourceClass.AIRBOAT})


def _ratio_milli(demand: int, capacity: int) -> int | None:
    if demand == 0:
        return 0
    if capacity == 0:
        return None
    return round(1_000 * demand / capacity)


def maximum_strict_matched_units(
    demand_units: Mapping[str, int],
    compatible_resources: Mapping[str, tuple[str, ...]],
) -> int:
    """Return the exact maximum weighted match for one-sided incident weights.

    Matchable incident sets form a transversal matroid. Greedily considering
    incidents by descending service units and using an augmenting path therefore
    returns a maximum-weight independent set, without exponential bitmasks.
    """

    matched_resource: dict[str, str] = {}

    def augment(incident_id: str, seen_resources: set[str]) -> bool:
        for resource_id in compatible_resources.get(incident_id, ()):
            if resource_id in seen_resources:
                continue
            seen_resources.add(resource_id)
            previous = matched_resource.get(resource_id)
            if previous is None or augment(previous, seen_resources):
                matched_resource[resource_id] = incident_id
                return True
        return False

    selected: set[str] = set()
    for incident_id in sorted(demand_units, key=lambda item: (-demand_units[item], item)):
        if augment(incident_id, set()):
            selected.add(incident_id)
    matched_incidents = set(matched_resource.values())
    if matched_incidents != selected:
        raise RuntimeError("Reference strict matching lost a selected incident")
    return sum(demand_units[item] for item in matched_incidents)


def maximum_divisible_capped_units(
    demand_by_bucket: Mapping[tuple[str, str], int],
    compatible_buckets_by_resource: Mapping[str, tuple[tuple[str, str], ...]],
    resource_units: Mapping[str, int],
) -> int:
    """Historical normalized sensitivity with divisible analytical service units."""

    tokens = tuple(
        (resource_id, unit_index)
        for resource_id in sorted(resource_units)
        for unit_index in range(resource_units[resource_id])
    )
    resources_by_bucket: dict[tuple[str, str], set[str]] = defaultdict(set)
    for resource_id, buckets in compatible_buckets_by_resource.items():
        for bucket in buckets:
            resources_by_bucket[bucket].add(resource_id)
    slots = tuple(
        (bucket, unit_index)
        for bucket in sorted(demand_by_bucket)
        for unit_index in range(
            min(
                demand_by_bucket[bucket],
                sum(resource_units[item] for item in resources_by_bucket.get(bucket, ())),
            )
        )
    )
    compatible_slots = {
        token: tuple(
            slot for slot in slots if slot[0] in compatible_buckets_by_resource.get(token[0], ())
        )
        for token in tokens
    }
    matched_slot: dict[tuple[tuple[str, str], int], tuple[str, int]] = {}

    def augment(
        token: tuple[str, int],
        seen_slots: set[tuple[tuple[str, str], int]],
    ) -> bool:
        for slot in compatible_slots[token]:
            if slot in seen_slots:
                continue
            seen_slots.add(slot)
            previous = matched_slot.get(slot)
            if previous is None or augment(previous, seen_slots):
                matched_slot[slot] = token
                return True
        return False

    return sum(augment(token, set()) for token in tokens)


@dataclass(frozen=True)
class _CommitmentInterval:
    resource_id: str
    truth_incident_id: str | None
    start_s: int
    end_s: int
    valid_truth_cover: bool


class ReferenceCapacityEvaluator:
    """Evaluate completed runtime output against hidden truth after execution."""

    metric_version = "delta-reference-demand-capacity-v1"

    def __init__(self, scenario: ReferenceScenarioArtifacts) -> None:
        seeds = {
            scenario.exposure.seed,
            scenario.truth.seed,
            scenario.observations.raw.seed,
            scenario.observations.delivery.seed,
            scenario.resources.hidden.seed,
            scenario.coordination.public.seed,
            scenario.coordination.activations.seed,
        }
        if len(seeds) != 1:
            raise ValueError("Reference capacity inputs do not share one scenario seed")
        self.scenario = scenario
        self._resources = {
            item.resource_id: item for item in scenario.resources.public_catalog.resources
        }
        self._state_by_resource: dict[str, tuple[ReferenceResourceStateSample, ...]] = {
            resource_id: tuple(
                item
                for item in scenario.resources.hidden.state_samples
                if item.resource_id == resource_id
            )
            for resource_id in self._resources
        }
        self._state_times = {
            resource_id: tuple(item.at_s for item in values)
            for resource_id, values in self._state_by_resource.items()
        }
        self._activation_time = {
            (item.resource_id, item.phase): item.observed_at_s
            for item in scenario.coordination.activations.events
        }
        self._physical_by_time = {item.at_s: item for item in scenario.physical.samples}
        self._physical_times = tuple(sorted(self._physical_by_time))
        self._edge_by_mode = {
            mode: tuple(item for item in scenario.geography.route_edges if item.mode == mode)
            for mode in ("road-crossing", "water-transfer")
        }
        self._lineage_by_call = {
            item.call_id: item.truth_incident_id for item in scenario.observations.hidden.entries
        }
        self._route_cache: dict[tuple[str, str, int], bool] = {}
        self._path_cache: dict[tuple[str, str, str], tuple[str, ...] | None] = {}

    def evaluate(self, run: ReferenceMissionRun) -> ReferenceCapacityEvaluation:
        if not run.complete:
            raise ValueError("Reference capacity evaluation requires a completed runtime")
        intervals = self._commitment_intervals(run)
        windows = tuple(
            self._window(at_s, intervals)
            for at_s in range(0, 345_600, self.scenario.config.timeline.capacity_evaluation_tick_s)
        )
        body = {
            "scenario_id": "WF-DFLD-01-REFERENCE",
            "schema_version": "delta-reference-capacity-evaluation-v1",
            "metric_version": self.metric_version,
            "scientific_status": "development-report-only-no-numerical-load-gate",
            "seed": self.scenario.truth.seed,
            "scenario_input_digest": reference_scenario_input_digest(self.scenario),
            "runtime_event_prefix_digest": run.event_prefix_digest,
            "trace_prefix_digest": run.trace_prefix_digest,
            "evidence_prefix_digest": run.evidence_prefix_digest,
            "commitment_prefix_digest": run.commitment_prefix_digest,
            "fault_profile_id": run.fault_profile_id,
            "evaluation_tick_s": 900,
            "window_count": 384,
            "windows": [item.model_dump(mode="json") for item in windows],
            "peak_finite_strict_concurrent_load_ratio_milli": self._peak(
                windows, "strict_concurrent_load_ratio_milli"
            ),
            "strict_unserviceable_window_count": sum(item.strict_unserviceable for item in windows),
            "peak_finite_uncapped_compatible_load_ratio_milli": self._peak(
                windows, "uncapped_compatible_load_ratio_milli"
            ),
            "uncapped_unserviceable_window_count": sum(
                item.active_demand_units > 0
                and item.uncapped_compatible_service_unit_capacity_units == 0
                for item in windows
            ),
            "peak_finite_historical_normalized_coverable_load_index_milli": self._peak(
                windows, "historical_normalized_coverable_load_index_milli"
            ),
            "historical_unserviceable_window_count": sum(
                item.active_demand_units > 0
                and item.historical_divisible_capped_capacity_units == 0
                for item in windows
            ),
            "peak_finite_residual_strict_pressure_ratio_milli": self._peak(
                windows, "residual_strict_pressure_ratio_milli"
            ),
            "residual_unserviceable_window_count": sum(
                item.residual_strict_unserviceable for item in windows
            ),
        }
        return ReferenceCapacityEvaluation(
            **body,
            evaluation_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
        )

    @staticmethod
    def _peak(windows: Sequence[ReferenceCapacityWindow], field: str) -> int:
        values = (getattr(item, field) for item in windows)
        return max((item for item in values if item is not None), default=0)

    def _window(
        self,
        at_s: int,
        intervals: tuple[_CommitmentInterval, ...],
    ) -> ReferenceCapacityWindow:
        active = tuple(
            item
            for item in self.scenario.truth.incidents
            if item.onset_s <= at_s < item.scheduled_resolution_s
        )
        compatible = self._compatible_resources(active, at_s, excluded=())
        demand = {item.truth_incident_id: item.service_requirement.service_units for item in active}
        strict = maximum_strict_matched_units(demand, compatible)
        uncapped = self._uncapped_units(active, compatible)
        historical = self._historical_units(active, compatible)
        active_intervals = tuple(item for item in intervals if item.start_s <= at_s < item.end_s)
        covered_ids = {
            item.truth_incident_id
            for item in active_intervals
            if item.valid_truth_cover and item.truth_incident_id is not None
        }
        residual = tuple(item for item in active if item.truth_incident_id not in covered_ids)
        busy_resources = {item.resource_id for item in active_intervals}
        residual_compatible = self._compatible_resources(
            residual,
            at_s,
            excluded=busy_resources,
        )
        residual_demand = {
            item.truth_incident_id: item.service_requirement.service_units for item in residual
        }
        free_strict = maximum_strict_matched_units(residual_demand, residual_compatible)
        demand_units = sum(demand.values())
        residual_units = sum(residual_demand.values())
        counts = self._inventory_counts(at_s)
        return ReferenceCapacityWindow(
            schema_version="delta-reference-capacity-window-v1",
            at_s=at_s,
            active_incident_count=len(active),
            active_demand_units=demand_units,
            strict_matched_capacity_units=strict,
            strict_concurrent_load_ratio_milli=_ratio_milli(demand_units, strict),
            strict_unserviceable=demand_units > 0 and strict == 0,
            uncapped_compatible_service_unit_capacity_units=uncapped,
            uncapped_compatible_load_ratio_milli=_ratio_milli(demand_units, uncapped),
            historical_divisible_capped_capacity_units=historical,
            historical_normalized_coverable_load_index_milli=_ratio_milli(demand_units, historical),
            commitment_covered_demand_units=demand_units - residual_units,
            residual_demand_units=residual_units,
            free_strict_compatible_capacity_units=free_strict,
            residual_strict_pressure_ratio_milli=_ratio_milli(residual_units, free_strict),
            residual_strict_unserviceable=residual_units > 0 and free_strict == 0,
            inventory_count=counts[0],
            crewed_inventory_count=counts[1],
            mobilized_inventory_count=counts[2],
            arrived_inventory_count=counts[3],
        )

    def _compatible_resources(
        self,
        incidents: Sequence[ReferenceTruthIncident],
        at_s: int,
        *,
        excluded: Collection[str],
    ) -> dict[str, tuple[str, ...]]:
        excluded_ids = frozenset(excluded)
        return {
            incident.truth_incident_id: tuple(
                resource.resource_id
                for resource in sorted(self._resources.values(), key=lambda item: item.resource_id)
                if resource.resource_id not in excluded_ids
                and self._can_cover(resource, incident, at_s)
            )
            for incident in incidents
        }

    def _can_cover(
        self,
        resource: ReferencePublicResourceDefinition,
        incident: ReferenceTruthIncident,
        at_s: int,
    ) -> bool:
        requirement = incident.service_requirement
        if requirement.capability not in {item.value for item in resource.capabilities}:
            return False
        if resource.service_units < requirement.service_units:
            return False
        if not self._resource_available(resource.resource_id, at_s):
            return False
        if (
            requirement.capability == "hazard-control"
            and "material-supply-required" in resource.constraints
        ):
            return False
        if "compatible-watercraft-or-access-required" in resource.constraints:
            return False
        return self._route_reachable(resource, incident.island_id, at_s)

    def _resource_available(self, resource_id: str, at_s: int) -> bool:
        available_at = self._activation_time.get(
            (resource_id, ReferenceResourceActivationPhase.AVAILABLE)
        )
        if available_at is None or at_s < available_at:
            return False
        state = self._state_at(resource_id, at_s)
        return (
            state.crew_on_duty
            and state.state
            not in {ReferenceResourceState.INITIAL_OUTAGE, ReferenceResourceState.CREW_REST}
            and state.fuel_or_charge_micros > 0
        )

    def _state_at(self, resource_id: str, at_s: int) -> ReferenceResourceStateSample:
        index = bisect_right(self._state_times[resource_id], at_s) - 1
        if index < 0:
            raise ValueError("Reference capacity time precedes resource state history")
        return self._state_by_resource[resource_id][index]

    def _route_reachable(
        self,
        resource: ReferencePublicResourceDefinition,
        destination_node_id: str,
        at_s: int,
    ) -> bool:
        key = (resource.resource_id, destination_node_id, at_s)
        cached = self._route_cache.get(key)
        if cached is not None:
            return cached
        physical_index = bisect_right(self._physical_times, at_s) - 1
        if physical_index < 0:
            raise ValueError("Reference route time precedes physical state history")
        physical = self._physical_by_time[self._physical_times[physical_index]]
        if resource.resource_class in _AIR_CLASSES:
            if physical.weather.air_operability != "normal":
                reachable = False
            elif "maximum-wind-25-kt" in resource.constraints:
                reachable = physical.weather.wind_milli_knots <= 25_000
            elif "maximum-wind-45-kt" in resource.constraints:
                reachable = physical.weather.wind_milli_knots <= 45_000
            else:
                reachable = True
        else:
            mode = (
                "water-transfer" if resource.resource_class in _WATER_CLASSES else "road-crossing"
            )
            path = self._shortest_path(resource.staged_node_id, destination_node_id, mode)
            if path is None:
                reachable = False
            elif mode == "water-transfer":
                reachable = True
            else:
                status = {item.crossing_id: item.status for item in physical.crossings}
                reachable = all(status[edge_id] == "open" for edge_id in path)
        self._route_cache[key] = reachable
        return reachable

    def _shortest_path(
        self,
        start: str,
        target: str,
        mode: str,
    ) -> tuple[str, ...] | None:
        cache_key = (start, target, mode)
        if cache_key in self._path_cache:
            return self._path_cache[cache_key]
        if start == target:
            self._path_cache[cache_key] = ()
            return ()
        adjacency: dict[str, list[tuple[str, str, int]]] = defaultdict(list)
        for edge in self._edge_by_mode[mode]:
            adjacency[edge.from_node_id].append((edge.to_node_id, edge.edge_id, edge.length_m))
            adjacency[edge.to_node_id].append((edge.from_node_id, edge.edge_id, edge.length_m))
        frontier: list[tuple[int, tuple[str, ...], str]] = [(0, (), start)]
        best: dict[str, tuple[int, tuple[str, ...]]] = {start: (0, ())}
        while frontier:
            length, edge_ids, node = heapq.heappop(frontier)
            if best.get(node) != (length, edge_ids):
                continue
            if node == target:
                self._path_cache[cache_key] = edge_ids
                return edge_ids
            for next_node, edge_id, edge_length in sorted(adjacency.get(node, ())):
                candidate = (length + edge_length, (*edge_ids, edge_id))
                if next_node not in best or candidate < best[next_node]:
                    best[next_node] = candidate
                    heapq.heappush(frontier, (*candidate, next_node))
        self._path_cache[cache_key] = None
        return None

    def _uncapped_units(
        self,
        active: Sequence[ReferenceTruthIncident],
        compatible: Mapping[str, tuple[str, ...]],
    ) -> int:
        compatible_ids = {resource_id for values in compatible.values() for resource_id in values}
        return sum(self._resources[item].service_units for item in compatible_ids) if active else 0

    def _historical_units(
        self,
        active: Sequence[ReferenceTruthIncident],
        compatible: Mapping[str, tuple[str, ...]],
    ) -> int:
        demand_by_bucket: dict[tuple[str, str], int] = defaultdict(int)
        buckets_by_resource: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for incident in active:
            bucket = (incident.service_requirement.capability, incident.island_id)
            demand_by_bucket[bucket] += incident.service_requirement.service_units
            for resource_id in compatible[incident.truth_incident_id]:
                buckets_by_resource[resource_id].add(bucket)
        units = {item: self._resources[item].service_units for item in buckets_by_resource}
        return maximum_divisible_capped_units(
            demand_by_bucket,
            {item: tuple(sorted(values)) for item, values in buckets_by_resource.items()},
            units,
        )

    def _inventory_counts(self, at_s: int) -> tuple[int, int, int, int]:
        resource_ids = tuple(self._resources)
        crewed = sum(
            self._state_at(item, at_s).crew_on_duty
            and self._state_at(item, at_s).state != ReferenceResourceState.INITIAL_OUTAGE
            for item in resource_ids
        )
        mobilized = sum(
            at_s >= self._activation_time[(item, ReferenceResourceActivationPhase.MOBILIZED)]
            for item in resource_ids
        )
        arrived = sum(
            at_s >= self._activation_time[(item, ReferenceResourceActivationPhase.ARRIVED)]
            for item in resource_ids
        )
        return len(resource_ids), crewed, mobilized, arrived

    def _commitment_intervals(
        self,
        run: ReferenceMissionRun,
    ) -> tuple[_CommitmentInterval, ...]:
        outcome_by_commitment = {item.commitment_id: item for item in run.outcomes}
        compensated_at = {
            item.invalidated_commitment_id: item.attempted_at_s
            for item in run.compensations
            if item.status == "completed"
        }
        incidents = {item.truth_incident_id: item for item in self.scenario.truth.incidents}
        values = []
        for decision in run.decisions:
            if decision.disposition != "allocated":
                continue
            if decision.commitment_id is None or decision.selected_resource_id is None:
                raise RuntimeError("Reference allocation lacks exact commitment/resource identity")
            outcome = outcome_by_commitment[decision.commitment_id]
            end_s = min(
                outcome.scheduled_completion_s,
                compensated_at.get(decision.commitment_id, outcome.scheduled_completion_s),
            )
            truth_id = self._lineage_by_call.get(decision.call_id)
            incident = incidents.get(truth_id or "")
            resource = self._resources[decision.selected_resource_id]
            valid = incident is not None and self._can_cover(
                resource, incident, decision.decided_at_s
            )
            values.append(
                _CommitmentInterval(
                    resource_id=decision.selected_resource_id,
                    truth_incident_id=truth_id,
                    start_s=decision.decided_at_s,
                    end_s=end_s,
                    valid_truth_cover=valid,
                )
            )
        return tuple(sorted(values, key=lambda item: (item.start_s, item.resource_id)))


def evaluate_reference_capacity(
    scenario: ReferenceScenarioArtifacts,
    run: ReferenceMissionRun,
) -> ReferenceCapacityEvaluation:
    """Public facade for aggregate-only post-runtime capacity evaluation."""

    return ReferenceCapacityEvaluator(scenario).evaluate(run)
