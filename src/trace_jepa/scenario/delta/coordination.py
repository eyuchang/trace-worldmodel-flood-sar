from __future__ import annotations

from trace_jepa.scenario.delta.models import (
    CoordinationArtifact,
    CoordinationDelivery,
    DeltaScenarioConfig,
    ObservationArtifact,
)
from trace_jepa.scenario.delta.randomness import KeyedRandom


def _source_authority(channel: str) -> str:
    if channel == "text-to-911":
        return "AUTH-SAC-TEXT"
    if channel == "non-emergency-transfer":
        return "AUTH-ISLETON-NONEMERGENCY"
    if channel in {"911-callback", "911-transfer"}:
        return "AUTH-SAC-FOLLOWUP"
    return "AUTH-SAC-PSAP"


def generate_coordination(
    config: DeltaScenarioConfig,
    observations: ObservationArtifact,
    keyed: KeyedRandom,
) -> CoordinationArtifact:
    if config.axes.phi == 1:
        authorities = ["AUTH-UNIFIED-SMALL"]
        deliveries = [
            CoordinationDelivery(
                call_id=call.call_id,
                source_authority_id="AUTH-UNIFIED-SMALL",
                controller_authority_id="AUTH-UNIFIED-SMALL",
                available_to_controller_s=call.received_s,
                sharing_latency_s=0,
            )
            for call in observations.calls
        ]
        semantics = "single-logical-authority-immediate-controller-visible-evidence"
    else:
        controller_authority = "AUTH-DELTA-MISSION-CONTROLLER"
        sources = sorted({_source_authority(call.channel) for call in observations.calls})
        authorities = [controller_authority, *sources]
        deliveries = []
        for call in observations.calls:
            source = _source_authority(call.channel)
            base_latency = 30 * (config.axes.phi - 1)
            jitter = keyed.randint(
                0,
                90 * (config.axes.phi - 1),
                "coordination-latency",
                call.call_id,
            )
            latency = base_latency + jitter
            available_to_controller_s = min(
                config.timeline.duration_s - 1,
                call.received_s + latency,
            )
            deliveries.append(
                CoordinationDelivery(
                    call_id=call.call_id,
                    source_authority_id=source,
                    controller_authority_id=controller_authority,
                    available_to_controller_s=available_to_controller_s,
                    sharing_latency_s=available_to_controller_s - call.received_s,
                )
            )
        semantics = (
            "source-partitioned-logical-authorities-with-deterministic-evidence-sharing-latency"
        )
    return CoordinationArtifact(
        schema_version="delta-coordination-v1",
        phi=config.axes.phi,
        logical_authority_ids=authorities,
        semantics=semantics,
        deliveries=sorted(deliveries, key=lambda item: item.call_id),
    )
