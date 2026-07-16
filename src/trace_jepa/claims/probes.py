from __future__ import annotations

from trace_jepa.contracts import Claim, ClaimLayer, PlanCandidate, PlanPrediction


class FloodClaimProbe:
    version = "flood-probe-v2"

    def build_claim(self, plan: PlanCandidate, prediction: PlanPrediction) -> Claim:
        action = plan.first_action

        if action.action_type == "verify_route":
            text = (
                f"{action.actor_id} can verify {action.route_id} within the admitted horizon."
            )
            grounding = {
                "actor_id": action.actor_id,
                "route_id": action.route_id,
                "horizon_steps": prediction.rollout_horizon,
                "action_id": action.action_id,
            }
        elif action.action_type == "dispatch_rescue_boat":
            text = (
                f"{action.route_id} is traversable and {action.actor_id} can reach "
                f"{action.destination} before the deadline."
            )
            grounding = {
                "actor_id": action.actor_id,
                "origin": action.origin,
                "destination": action.destination,
                "route_id": action.route_id,
                "people_count": action.parameters["people_count"],
                "deadline_s": action.parameters["deadline_s"],
                "horizon_steps": prediction.rollout_horizon,
                "action_id": action.action_id,
            }
        else:
            raise KeyError(action.action_type)

        return Claim(
            layer=ClaimLayer.PREDICTIVE,
            text=text,
            grounding=grounding,
            confidence=prediction.success_probability,
            confidence_semantics=(
                "Teaching proxy copied from plan success probability; not a "
                "separately calibrated claim probability."
            ),
        )
