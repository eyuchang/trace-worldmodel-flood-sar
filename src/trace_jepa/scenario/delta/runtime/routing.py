"""Indexed route, crossing, weather, gauge, and resource access."""

from __future__ import annotations

from dataclasses import dataclass

from trace_jepa.scenario.delta.domain import (
    CallRecord,
    CrossingState,
    GaugeSample,
    GeneratedScenario,
    IncidentTruth,
    ResourceUnit,
    WeatherSample,
)


@dataclass(frozen=True)
class ScenarioIndex:
    """Precomputed deterministic lookup tables for one generated scenario."""

    scenario: GeneratedScenario
    crossing_by_key: dict[tuple[str, int], CrossingState]
    weather_by_time: dict[int, WeatherSample]
    gauge_by_key: dict[tuple[str, int], GaugeSample]
    crossing_nominal_s: dict[str, int]

    @classmethod
    def build(cls, scenario: GeneratedScenario) -> ScenarioIndex:
        return cls(
            scenario=scenario,
            crossing_by_key={
                (item.crossing_id, item.simulation_time_s): item
                for item in scenario.crossing_states
            },
            weather_by_time={item.simulation_time_s: item for item in scenario.weather},
            gauge_by_key={
                (item.gauge_id, item.simulation_time_s): item for item in scenario.gauges
            },
            crossing_nominal_s={
                item.crossing_id: item.nominal_travel_s for item in scenario.geography.crossings
            },
        )

    def nearest_tick(self, simulation_time_s: int) -> int:
        timeline = self.scenario.config.timeline
        return min(timeline.duration_s, simulation_time_s // timeline.tick_s * timeline.tick_s)

    def crossing_state(self, route_id: str, simulation_time_s: int) -> CrossingState:
        return self.crossing_by_key[(route_id, self.nearest_tick(simulation_time_s))]

    def weather(self, simulation_time_s: int) -> WeatherSample:
        return self.weather_by_time[self.nearest_tick(simulation_time_s)]

    def route_for_call(self, call: CallRecord) -> str:
        centroids = {
            island.island_id: island.centroid for island in self.scenario.geography.islands
        }
        nearest = min(
            centroids,
            key=lambda island_id: (
                (call.location.easting_mm - centroids[island_id].easting_mm) ** 2
                + (call.location.northing_mm - centroids[island_id].northing_mm) ** 2
            ),
        )
        return "XNG-03" if nearest == "ISL-02" else "XNG-04"

    def travel_seconds(
        self,
        unit: ResourceUnit,
        simulation_time_s: int,
        route_id: str | None = None,
    ) -> int | None:
        selected_route = route_id or unit.route_id
        state = self.crossing_state(selected_route, simulation_time_s)
        if state.status != "open":
            return None
        friction = state.travel_time_s / self.crossing_nominal_s[selected_route]
        return round(unit.nominal_travel_time_s * friction)

    def incident_route(self, incident: IncidentTruth) -> str:
        structure = next(
            item
            for item in self.scenario.truth.structures
            if item.structure_id == incident.structure_id
        )
        return "XNG-03" if structure.island_id == "ISL-02" else "XNG-04"

    def candidate_resource(
        self,
        capability: str,
        simulation_time_s: int,
        route_id: str,
        busy_until: dict[str, int],
    ) -> tuple[ResourceUnit, int] | None:
        for unit in sorted(self.scenario.resources.units, key=lambda item: item.resource_id):
            if capability not in unit.capabilities:
                continue
            if not unit.is_available or unit.available_from_s > simulation_time_s:
                continue
            if busy_until[unit.resource_id] > simulation_time_s:
                continue
            travel_s = self.travel_seconds(unit, simulation_time_s, route_id)
            if travel_s is not None:
                return unit, travel_s
        return None
