"""Controller-visible predictor request and TRACE evidence construction."""

from __future__ import annotations

from datetime import timedelta

from trace_jepa.contracts import ActionInstance, PlanCandidate, WorldModelEvidence
from trace_jepa.experimental import build_experimental_profile
from trace_jepa.predictor import (
    ActionPrefixPredictor,
    PredictorContext,
    PredictorObservation,
    PredictorPriorProfile,
    PredictorRequest,
    PredictorResourceTelemetry,
    PredictorRouteObservation,
    PredictorVisualFeatureRef,
)
from trace_jepa.scenario.delta.domain import CallRecord, GeneratedScenario
from trace_jepa.scenario.delta.geography import Gauge
from trace_jepa.support import canonical_json_bytes, sha256_bytes

from .routing import ScenarioIndex


class PredictorEvidenceBuilder:
    """Build one fully bound predictor request and its TRACE evidence record."""

    def __init__(
        self,
        scenario: GeneratedScenario,
        predictor: ActionPrefixPredictor,
        busy_until: dict[str, int],
        scenario_index: ScenarioIndex,
    ) -> None:
        self.scenario = scenario
        self.predictor = predictor
        self.busy_until = busy_until
        self.index = scenario_index

    def _nearest_gauge(self, route_id: str) -> Gauge:
        crossing = next(
            item for item in self.scenario.geography.crossings if item.crossing_id == route_id
        )
        return min(
            self.scenario.geography.gauges,
            key=lambda gauge: (
                (gauge.location.easting_mm - crossing.location.easting_mm) ** 2
                + (gauge.location.northing_mm - crossing.location.northing_mm) ** 2,
                gauge.gauge_id,
            ),
        )

    def _resource_telemetry(
        self,
        capability: str,
        route_id: str,
        controller_time_s: int,
    ) -> tuple[PredictorResourceTelemetry, ...]:
        telemetry: list[PredictorResourceTelemetry] = []
        for unit in sorted(self.scenario.resources.units, key=lambda item: item.resource_id):
            if capability not in unit.capabilities:
                continue
            travel_s = self.index.travel_seconds(unit, controller_time_s, route_id)
            telemetry.append(
                PredictorResourceTelemetry(
                    resource_id=unit.resource_id,
                    resource_class=unit.resource_class,
                    capabilities=unit.capabilities,
                    service_units=unit.service_units,
                    availability_mode=unit.availability_mode,
                    origin_base_id=unit.origin_base_id,
                    staged_base_id=unit.base_id,
                    route_id=route_id,
                    scheduled_available_s=unit.available_from_s,
                    busy_until_s=self.busy_until[unit.resource_id],
                    currently_available=(
                        unit.is_available
                        and unit.available_from_s <= controller_time_s
                        and self.busy_until[unit.resource_id] <= controller_time_s
                        and travel_s is not None
                    ),
                    route_reachable=travel_s is not None,
                    routed_travel_s=travel_s,
                )
            )
        return tuple(telemetry)

    def build(
        self,
        call: CallRecord,
        action: ActionInstance,
        controller_time_s: int,
        visual_feature: PredictorVisualFeatureRef | None = None,
    ) -> tuple[WorldModelEvidence, PredictorRequest]:
        route_id = action.route_id
        if route_id is None:
            raise ValueError("Delta actions require an explicit route")
        route_state = self.index.crossing_state(route_id, controller_time_s)
        weather = self.index.weather(controller_time_s)
        tick = self.index.nearest_tick(controller_time_s)
        nearest_gauge = self._nearest_gauge(route_id)
        gauge_sample = self.index.gauge_by_key[(nearest_gauge.gauge_id, tick)]
        call_age_s = float(controller_time_s - call.received_s)
        crossing_age_s = float(controller_time_s - route_state.simulation_time_s)
        gauge_age_s = float(controller_time_s - gauge_sample.simulation_time_s)
        observation_age_s = max(call_age_s, crossing_age_s, gauge_age_s)
        capability = str(action.parameters["required_capability"])
        compatible_resources = self._resource_telemetry(capability, route_id, controller_time_s)
        available_units = sum(
            item.service_units for item in compatible_resources if item.currently_available
        )
        plan = PlanCandidate(
            plan_id=f"plan-{call.call_id}",
            name=f"Respond to {call.call_id}",
            actions=(action,),
            utility=1.0,
            reversible_first_action=False,
            requires_authority=True,
            metadata={"call_type": call.reported.call_type},
        )
        request = PredictorRequest(
            plan=plan,
            observation=PredictorObservation(
                routes=[
                    PredictorRouteObservation(
                        route_id=route_id,
                        report=("unknown" if call.quality.call_dropped else route_state.status),
                        nominal_travel_s=float(route_state.travel_time_s),
                        confidence=route_state.confidence_milli / 1_000.0,
                        observation_age_s=crossing_age_s,
                        stage_millifeet=gauge_sample.stage_millifeet,
                        crossing_sample_time_s=route_state.simulation_time_s,
                        gauge_id=nearest_gauge.gauge_id,
                        gauge_sample_time_s=gauge_sample.simulation_time_s,
                        gauge_threshold_status=nearest_gauge.threshold_status,
                    )
                ],
                context=PredictorContext(
                    simulation_time_s=controller_time_s,
                    rain_milli_inches_per_hour=weather.rain_milli_inches_per_hour,
                    wind_milli_knots=weather.wind_milli_knots,
                    available_resource_units=available_units,
                    call_observation_age_s=call_age_s,
                    coordination_latency_s=call_age_s,
                    compatible_resources=compatible_resources,
                    source_call_sha256=sha256_bytes(
                        canonical_json_bytes(call.model_dump(mode="json"))
                    ),
                    prior_profile=PredictorPriorProfile(
                        profile_id=self.scenario.prior_profile.profile_id,
                        calibration_version=self.scenario.prior_profile.calibration_version,
                        prior_accuracy_milli=self.scenario.prior_profile.prior_accuracy_milli,
                    ),
                    visual_feature=visual_feature,
                ),
            ),
        )
        prediction = self.predictor.predict(request)
        stamp = self.scenario.config.timeline.epoch_utc + timedelta(seconds=controller_time_s)
        provenance = self.predictor.provenance()
        profile = build_experimental_profile(
            predictor_version=provenance.predictor_version,
            calibration_version=provenance.calibration_version,
            claim_family=action.action_type,
            adequacy_status=provenance.adequacy_status,
            prediction_timestamp=stamp,
            model_hash=provenance.model_hash,
            calibration_hash=provenance.calibration_hash,
            notes=(f"prior_profile={self.scenario.prior_profile.profile_id}",),
        ).model_copy(update={"profile_id": f"profile-{call.call_id}"})
        evidence = WorldModelEvidence(
            evidence_id=f"evidence-{call.call_id}",
            rollout_id=f"rollout-{call.call_id}",
            encoder_version=provenance.encoder_version or "delta-symbolic-observation-v2",
            fusion_version=(
                "delta-small-controller-context-v4"
                if self.scenario.config.generator_version == "delta-small-generator-v8"
                else (
                    "delta-small-controller-context-v3"
                    if self.scenario.config.generator_version == "delta-small-generator-v7"
                    else "delta-small-controller-context-v2"
                )
            ),
            predictor_version=provenance.predictor_version,
            semantic_probe_versions=("delta-route-and-resource-probe-v2",),
            training_snapshot=provenance.training_snapshot,
            observation_window_hash=sha256_bytes(
                canonical_json_bytes(request.model_dump(mode="json"))
            ),
            fleet_state_hash=sha256_bytes(
                canonical_json_bytes(
                    {
                        "available_compatible_units": available_units,
                        "resource_schema": self.scenario.resources.schema_version,
                    }
                )
            ),
            candidate_plan_id=plan.plan_id,
            action_schema_version=provenance.action_schema_version,
            rollout_horizon=prediction.rollout_horizon,
            predicted_claims=(
                f"{route_id} and registered compatible capacity support the proposed response",
            ),
            uncertainty=prediction.uncertainty,
            model_support=prediction.model_support,
            out_of_distribution_score=prediction.out_of_distribution_score,
            rollout_consistency=1.0 - prediction.uncertainty,
            reachability_evidence={
                "arrival_time_s": prediction.arrival_time_s,
                "hazard_score": prediction.hazard_score,
                "route_status": route_state.status,
                "route_confidence_milli": route_state.confidence_milli,
                "gauge_id": nearest_gauge.gauge_id,
                "gauge_stage_millifeet": gauge_sample.stage_millifeet,
                "gauge_threshold_status": nearest_gauge.threshold_status,
                "crossing_sample_time_s": route_state.simulation_time_s,
                "gauge_sample_time_s": gauge_sample.simulation_time_s,
            },
            calibration_version=provenance.calibration_version,
            assumptions=prediction.assumptions,
            observation_age_s=observation_age_s,
            created_at=stamp,
            experimental_profile=profile,
        )
        return evidence, request
