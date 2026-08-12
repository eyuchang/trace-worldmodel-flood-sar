"""Bounded public-only indices over immutable Reference scenario artifacts."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

from trace_reference.domain.physical import (
    ReferenceCrossingStateSample,
    ReferenceGaugeContextRegistry,
    ReferenceGaugeStageSample,
    ReferencePhysicalScenario,
    ReferenceWeatherSample,
)
from trace_reference.geography import ReferenceGeographyCatalog


@dataclass(frozen=True)
class ReferencePublicPhysicalView:
    """A physical sample projection that cannot expose hidden breach state."""

    at_s: int
    weather: ReferenceWeatherSample
    gauges: tuple[ReferenceGaugeStageSample, ...]
    crossings: tuple[ReferenceCrossingStateSample, ...]


class ReferenceScenarioIndex:
    """Precompute small immutable maps without retaining hidden truth interfaces."""

    def __init__(
        self,
        geography: ReferenceGeographyCatalog,
        gauge_context: ReferenceGaugeContextRegistry,
        public_physical: tuple[ReferencePublicPhysicalView, ...],
    ) -> None:
        if not public_physical:
            raise ValueError("Reference public physical index cannot be empty")
        times = tuple(item.at_s for item in public_physical)
        if times != tuple(sorted(set(times))):
            raise ValueError("Reference public physical samples must be unique and ordered")
        self.geography = geography
        self.gauge_context = gauge_context
        self.public_physical = public_physical
        self._times = times
        self.nodes = {item.node_id: item for item in geography.route_nodes}
        self.crossings = {item.crossing_id: item for item in geography.crossings}
        self.islands = {item.island_id: item for item in geography.islands}

    @classmethod
    def from_physical(
        cls,
        geography: ReferenceGeographyCatalog,
        gauge_context: ReferenceGaugeContextRegistry,
        physical: ReferencePhysicalScenario,
    ) -> ReferenceScenarioIndex:
        public = tuple(
            ReferencePublicPhysicalView(
                at_s=item.at_s,
                weather=item.weather,
                gauges=item.gauges,
                crossings=item.crossings,
            )
            for item in physical.samples
        )
        return cls(geography, gauge_context, public)

    def physical_at(self, at_s: int) -> ReferencePublicPhysicalView:
        """Return the latest controller-visible sample at or before simulation time."""

        index = bisect_right(self._times, at_s) - 1
        if index < 0:
            raise ValueError("Reference request precedes the public physical series")
        return self.public_physical[index]
