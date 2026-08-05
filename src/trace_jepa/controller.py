from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trace_jepa.claims import FloodClaimProbe
from trace_jepa.contracts import (
    ActionInstance,
    Claim,
    PlanCandidate,
    PlanPrediction,
    RealizedOutcome,
    TraceRecord,
    TraceStatus,
    WorldModelEvidence,
)
from trace_jepa.experimental import build_experimental_profile
from trace_jepa.fusion import fuse_state
from trace_jepa.perception import MockVideoEncoder
from trace_jepa.planning import FloodPlanner
from trace_jepa.predictor import (
    ActionPrefixPredictor,
    PredictorObservation,
    PredictorRequest,
    PredictorRouteObservation,
    ToyActionPrefixPredictor,
)
from trace_jepa.runtime import TraceRuntime
from trace_jepa.scenario import FloodEnvironment
from trace_jepa.util import sha256_value, write_json


@dataclass(frozen=True)
class IncidentCommander:
    """Teaching stand-in for an external human authority boundary."""

    role_id: str = "incident_commander_1"
    approved_action_types: tuple[str, ...] = ("dispatch_rescue_boat",)

    def authorizes(self, action: ActionInstance) -> bool:
        return action.action_type in self.approved_action_types


class MissionController:
    """One central command-post program coordinating the demonstration.

    The Planner, World Model, TRACE Gate, and Action Dispatcher are modules
    inside this controller. The drone and rescue boat are physical agents in
    the Flood Environment, not additional reasoning systems.
    """

    version = "mission-controller-v2"

    def __init__(
        self,
        *,
        environment: FloodEnvironment,
        runtime: TraceRuntime,
        incident_commander: IncidentCommander | None = None,
        encoder: MockVideoEncoder | None = None,
        planner: FloodPlanner | None = None,
        predictor: ActionPrefixPredictor | None = None,
        probe: FloodClaimProbe | None = None,
    ) -> None:
        self.environment = environment
        self.runtime = runtime
        self.incident_commander = incident_commander or IncidentCommander()
        self.encoder = encoder or MockVideoEncoder()
        self.planner = planner or FloodPlanner()
        self.predictor = predictor or ToyActionPrefixPredictor()
        self.probe = probe or FloodClaimProbe()

    def _make_evidence(
        self,
        *,
        plan: PlanCandidate,
        prediction: PlanPrediction,
        claim: Claim,
        state_hash: str,
        observation_hash: str,
        outcome: RealizedOutcome | None = None,
        contradicted: bool = False,
    ) -> WorldModelEvidence:
        residual = None
        outcome_payload = None
        if outcome is not None:
            outcome_payload = outcome.model_dump(mode="json")
            residual = {
                "predicted_plan_success_probability": prediction.success_probability,
                "realized_success": outcome.success,
            }

        return WorldModelEvidence(
            encoder_version="mock-video-v1",
            fusion_version="flood-fusion-v1",
            predictor_version=self.predictor.predictor_version,
            semantic_probe_versions=(self.probe.version,),
            training_snapshot=self.predictor.training_snapshot,
            observation_window_hash=observation_hash,
            fleet_state_hash=state_hash,
            candidate_plan_id=plan.plan_id,
            action_schema_version="flood-actions-v1",
            rollout_horizon=prediction.rollout_horizon,
            predicted_claims=(claim.text,),
            uncertainty=prediction.uncertainty,
            model_support=prediction.model_support,
            out_of_distribution_score=prediction.out_of_distribution_score,
            rollout_consistency=1.0 - prediction.uncertainty,
            reachability_evidence={
                "grounded_action": plan.first_action.model_dump(mode="json"),
                "predicted_plan_success_probability": prediction.success_probability,
                "claim_confidence": claim.confidence,
                "claim_confidence_semantics": claim.confidence_semantics,
                "arrival_time_s": prediction.arrival_time_s,
                "hazard_score": prediction.hazard_score,
                "resource_margin": prediction.resource_margin,
            },
            calibration_version=self.predictor.calibration_version,
            assumptions=prediction.assumptions,
            observation_age_s=10.0,
            decisively_contradicted=contradicted,
            realized_outcome=outcome_payload,
            prediction_residual=residual,
            experimental_profile=build_experimental_profile(
                predictor_version=self.predictor.predictor_version,
                calibration_version=self.predictor.calibration_version,
                claim_family=plan.first_action.action_type,
                adequacy_status=self.predictor.adequacy_status,
                model_hash=self.predictor.model_hash,
                calibration_hash=self.predictor.calibration_hash,
            ),
        )

    def _assess_observation(
        self,
        observation: dict,
        *,
        replanned: bool,
    ) -> tuple[
        list[dict],
        dict[str, TraceRecord],
        dict[str, PlanPrediction],
        dict[str, PlanCandidate],
    ]:
        visual_payload = json.dumps(observation, sort_keys=True).encode("utf-8")
        embedding = self.encoder.encode(visual_payload)
        state = fuse_state(embedding, observation)
        observation_hash = sha256_value(observation)

        assessed: list[dict] = []
        records: dict[str, TraceRecord] = {}
        predictions: dict[str, PlanPrediction] = {}
        plans: dict[str, PlanCandidate] = {}

        predictor_observation = PredictorObservation(
            routes=[
                PredictorRouteObservation(
                    route_id=route_id,
                    report=str(route["report"]),
                    nominal_travel_s=float(route["nominal_travel_s"]),
                )
                for route_id, route in observation["routes"].items()
            ]
        )
        for plan in self.planner.propose(observation):
            prediction = self.predictor.predict(
                PredictorRequest(plan=plan, observation=predictor_observation)
            )
            claim = self.probe.build_claim(plan, prediction)
            evidence = self._make_evidence(
                plan=plan,
                prediction=prediction,
                claim=claim,
                state_hash=state.state_hash,
                observation_hash=observation_hash,
            )
            action = plan.first_action
            authority_present = self.incident_commander.authorizes(action)
            repair_hint = None
            if (
                action.action_type == "dispatch_rescue_boat"
                and action.route_id is not None
                and observation["routes"][action.route_id]["report"] == "unknown"
            ):
                repair_hint = (
                    f"Send survey_drone_1 to verify {action.route_id} before "
                    f"dispatching {action.actor_id}."
                )

            record, evaluation = self.runtime.assess(
                claim=claim,
                evidence=evidence,
                action_name=action.action_type,
                reversible=plan.reversible_first_action,
                authority_present=authority_present,
                repair_hint=repair_hint,
                metadata={
                    "plan_id": plan.plan_id,
                    "planner_version": self.planner.version,
                    "mission_controller_version": self.version,
                    "incident_commander_role": self.incident_commander.role_id,
                    "authority_present": authority_present,
                    "replanned": replanned,
                    "grounded_action": action.model_dump(mode="json"),
                },
            )
            consumed = self.runtime.consume(
                record,
                evaluation,
                consumer="mission-controller",
            )
            records[plan.plan_id] = consumed
            predictions[plan.plan_id] = prediction
            plans[plan.plan_id] = plan
            assessed.append(
                {
                    "plan_id": plan.plan_id,
                    "plan_name": plan.name,
                    "grounded_action": action.model_dump(mode="json"),
                    "utility": plan.utility,
                    "predicted_plan_success_probability": prediction.success_probability,
                    "claim_confidence": claim.confidence,
                    "claim_confidence_semantics": claim.confidence_semantics,
                    "model_support": prediction.model_support,
                    "out_of_distribution_score": prediction.out_of_distribution_score,
                    "uncertainty": prediction.uncertainty,
                    "trace_status": evaluation.status.value,
                    "decision": evaluation.decision.value,
                    "failed_gates": list(evaluation.failed_gates),
                    "missing_items": list(evaluation.missing_items),
                    "repair": evaluation.repair,
                    "authority_present": authority_present,
                    "record_id": consumed.record_id,
                    "record_version": consumed.record_version,
                }
            )

        return assessed, records, predictions, plans

    def run_episode(
        self,
        output: Path | None = None,
        *,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict:
        """Run one incident from mission state to realized rescue outcome.

        ``event_sink`` receives a human-readable event immediately after each
        operational step. The same events are persisted in ``summary.json``.
        """

        timeline: list[dict[str, Any]] = []

        def emit(event_type: str, message: str, **details: Any) -> None:
            event = {
                "sequence": len(timeline) + 1,
                "event_type": event_type,
                "message": message,
                "details": details,
            }
            timeline.append(event)
            if event_sink is not None:
                event_sink(event)

        active_call = self.environment.active_call
        if active_call is not None:
            location_label = self.environment.scenario["locations"][
                active_call.normalized_location_id
            ]["label"]
            emit(
                "call_received",
                f"Emergency call reports {active_call.people_count} people at {location_label}.",
                call_id=active_call.call_id,
                normalized_location_id=active_call.normalized_location_id,
                people_count=active_call.people_count,
            )
        else:
            emit(
                "mission_loaded",
                "Loaded the preconfigured Riverside flood-rescue mission.",
            )

        # This snapshot is retained only for after-the-fact teaching and scoring.
        # It is never passed into _assess_observation or any controller module.
        initial_simulation_ground_truth = self.environment.simulation_ground_truth()
        initial_observation = self.environment.observe()
        mission = initial_observation["mission"]
        destination_label = initial_observation["locations"][mission["destination_id"]]["label"]
        emit(
            "mission_state",
            f"Mission Controller grounds the incident at {destination_label}; "
            f"North Channel is {initial_observation['routes']['north_channel']['report']}.",
            destination_id=mission["destination_id"],
            deadline_s=mission["deadline_s"],
        )

        assessed, record_by_plan, prediction_by_plan, plan_by_id = self._assess_observation(
            initial_observation,
            replanned=False,
        )
        for item in assessed:
            emit(
                "plan_assessed",
                f"{item['plan_name']} -> {item['decision'].upper()} "
                f"(support={item['model_support']:.2f}, "
                f"OOD={item['out_of_distribution_score']:.2f}).",
                plan_id=item["plan_id"],
                decision=item["decision"],
                trace_status=item["trace_status"],
                record_id=item["record_id"],
            )

        chosen = self.planner.choose(
            [(plan_by_id[item["plan_id"]], item["decision"]) for item in assessed]
        )
        if chosen is None:
            raise RuntimeError("no admissible initial action")

        emit(
            "action_selected",
            f"Mission Controller selects: {chosen.first_action.short_label}.",
            plan_id=chosen.plan_id,
            action=chosen.first_action.model_dump(mode="json"),
        )
        chosen_record = record_by_plan[chosen.plan_id]
        first_commitment = self.runtime.commit(
            record=chosen_record,
            action=chosen.first_action,
        )
        emit(
            "action_dispatched",
            f"Authorized command sent to {chosen.first_action.actor_id}.",
            commitment_id=first_commitment.commitment_id,
            authorizing_record_id=chosen_record.record_id,
            authorizing_record_version=chosen_record.record_version,
        )
        first_outcome = self.environment.execute(chosen.first_action)
        if chosen.first_action.action_type == "verify_route":
            emit(
                "observation_received",
                f"{chosen.first_action.actor_id} reports "
                f"{first_outcome.observations['route_id']} is "
                f"{first_outcome.observations['route_status']}.",
                outcome_id=first_outcome.outcome_id,
                observations=first_outcome.observations,
            )
        else:
            emit(
                "outcome_received",
                f"The first action completed with success={first_outcome.success}.",
                outcome_id=first_outcome.outcome_id,
            )

        revisions: list[dict] = []
        if (
            chosen.first_action.action_type == "verify_route"
            and first_outcome.observations.get("route_status") == "blocked"
        ):
            route_id = chosen.first_action.route_id
            dispatch_plan_id = (
                "north-direct" if route_id == "north_channel" else f"dispatch-{route_id}"
            )
            failed_record = record_by_plan[dispatch_plan_id]
            failed_plan = plan_by_id[dispatch_plan_id]
            failed_prediction = prediction_by_plan[dispatch_plan_id]
            failed_claim = self.probe.build_claim(failed_plan, failed_prediction)

            visual_payload = json.dumps(initial_observation, sort_keys=True).encode("utf-8")
            state = fuse_state(self.encoder.encode(visual_payload), initial_observation)
            realized_evidence = self._make_evidence(
                plan=failed_plan,
                prediction=failed_prediction,
                claim=failed_claim,
                state_hash=state.state_hash,
                observation_hash=sha256_value(initial_observation),
                outcome=first_outcome,
                contradicted=True,
            )
            revised = self.runtime.revise_with_outcome(
                failed_record,
                realized_evidence,
                new_status=TraceStatus.REJECT,
                reason=(f"{chosen.first_action.actor_id} observed that {route_id} is blocked."),
                repair=(
                    "Preserve the completed verification action and replan only "
                    "the rescue-route branch that depended on the failed claim."
                ),
            )
            revisions.append(
                {
                    "record_id": revised.record_id,
                    "record_version": revised.record_version,
                    "status": revised.final_status.value,
                    "reason": revised.metadata["revision_reason"],
                }
            )
            emit(
                "trace_revised",
                "TRACE rejects the northern-route claim and preserves the "
                "completed verification action.",
                record_id=revised.record_id,
                record_version=revised.record_version,
            )

        second_observation = self.environment.observe()
        emit(
            "replanning",
            "Planner repairs only the route-dependent rescue branch.",
        )
        second_assessed, second_records, _, second_plans = self._assess_observation(
            second_observation,
            replanned=True,
        )
        for item in second_assessed:
            emit(
                "plan_reassessed",
                f"{item['plan_name']} -> {item['decision'].upper()}.",
                plan_id=item["plan_id"],
                decision=item["decision"],
                record_id=item["record_id"],
            )

        final_plan = self.planner.choose(
            [(second_plans[item["plan_id"]], item["decision"]) for item in second_assessed]
        )
        if final_plan is None:
            raise RuntimeError("no admissible rescue plan after verification")

        emit(
            "final_action_selected",
            f"Mission Controller selects: {final_plan.first_action.short_label}.",
            plan_id=final_plan.plan_id,
            action=final_plan.first_action.model_dump(mode="json"),
        )
        final_record = second_records[final_plan.plan_id]
        final_commitment = self.runtime.commit(
            record=final_record,
            action=final_plan.first_action,
        )
        emit(
            "final_action_dispatched",
            f"Incident Commander approval and TRACE clearance authorize "
            f"{final_plan.first_action.actor_id}.",
            commitment_id=final_commitment.commitment_id,
            authorizing_record_id=final_record.record_id,
            authorizing_record_version=final_record.record_version,
        )
        final_outcome = self.environment.execute(final_plan.first_action)
        emit(
            "rescue_outcome",
            f"Rescue completed: success={final_outcome.success}, "
            f"people_reached={final_outcome.observations.get('people_reached', 0)}.",
            outcome_id=final_outcome.outcome_id,
            observations=final_outcome.observations,
        )

        summary = {
            "scenario": self.environment.scenario_id,
            "emergency_call": (
                active_call.model_dump(mode="json") if active_call is not None else None
            ),
            "entities": {
                "environment": "FloodEnvironment",
                "fleet": ["survey_drone_1", "rescue_boat_1"],
                "mission_controller": self.version,
                "incident_commander": self.incident_commander.role_id,
                "offline_scorer_in_control_loop": False,
            },
            "timeline": timeline,
            "initial_mission_controller_knowledge": initial_observation,
            "initial_controller_knowledge": initial_observation,
            "simulation_ground_truth_at_time_zero": initial_simulation_ground_truth,
            "simulation_ground_truth_after_run": self.environment.simulation_ground_truth(),
            "initial_assessments": assessed,
            "first_selected_plan": chosen.plan_id,
            "first_commitment_id": first_commitment.commitment_id,
            "first_commitment": first_commitment.model_dump(mode="json"),
            "first_action": chosen.first_action.model_dump(mode="json"),
            "first_outcome": first_outcome.model_dump(mode="json"),
            "revisions": revisions,
            "replanned_mission_controller_knowledge": second_observation,
            "replanned_assessments": second_assessed,
            "final_selected_plan": final_plan.plan_id,
            "final_commitment_id": final_commitment.commitment_id,
            "final_commitment": final_commitment.model_dump(mode="json"),
            "final_action": final_plan.first_action.model_dump(mode="json"),
            "final_outcome": final_outcome.model_dump(mode="json"),
            "rescued": self.environment.rescued,
            "record_chain_valid": self.runtime.repository.verify_chain(),
        }

        if output is not None:
            output = Path(output)
            output.mkdir(parents=True, exist_ok=True)
            write_json(output / "summary.json", summary)

        return summary
