from __future__ import annotations

from trace_jepa.contracts import PlanCandidate, PlanPrediction


class ToyActionPrefixPredictor:
    """Transparent fixture used before a learned flood-domain predictor.

    The outputs are deliberately deterministic so students can test the
    accountability path. They are not experimental results. Unlike the first
    version, behavior is keyed to the grounded action and observed route state,
    not to opaque plan identifiers.
    """

    version = "toy-action-prefix-v2"
    training_snapshot = "synthetic-flood-v1"

    def predict(self, plan: PlanCandidate, observation: dict) -> PlanPrediction:
        action = plan.first_action
        route = observation["routes"].get(action.route_id or "")

        if action.action_type == "verify_route":
            return PlanPrediction(
                plan_id=plan.plan_id,
                success_probability=0.98,
                arrival_time_s=180.0,
                hazard_score=0.08,
                resource_margin=0.74,
                model_support=0.97,
                out_of_distribution_score=0.04,
                uncertainty=0.04,
                rollout_horizon=2,
                assumptions=("weather_below_drone_limit",),
            )

        if action.action_type != "dispatch_rescue_boat" or route is None:
            raise KeyError(plan.plan_id)

        report = route["report"]
        nominal_travel_s = float(route["nominal_travel_s"])

        if report == "unknown":
            # Teaching case: a high numerical success estimate produced outside
            # the predictor's declared support. TRACE must hold the dispatch.
            return PlanPrediction(
                plan_id=plan.plan_id,
                success_probability=0.92,
                arrival_time_s=nominal_travel_s,
                hazard_score=0.12,
                resource_margin=0.35,
                model_support=0.28,
                out_of_distribution_score=0.82,
                uncertainty=0.08,
                rollout_horizon=6,
                assumptions=("map_is_current", "debris_distribution_matches_training"),
            )

        if report == "blocked":
            return PlanPrediction(
                plan_id=plan.plan_id,
                success_probability=0.03,
                arrival_time_s=max(nominal_travel_s, 1800.0),
                hazard_score=0.95,
                resource_margin=-0.20,
                model_support=0.95,
                out_of_distribution_score=0.05,
                uncertainty=0.05,
                rollout_horizon=6,
                assumptions=("verified_route_status",),
            )

        if report == "open":
            return PlanPrediction(
                plan_id=plan.plan_id,
                success_probability=0.82,
                arrival_time_s=nominal_travel_s,
                hazard_score=0.18,
                resource_margin=0.20,
                model_support=0.93,
                out_of_distribution_score=0.08,
                uncertainty=0.14,
                rollout_horizon=7,
                assumptions=("route_report_is_fresh",),
            )

        raise ValueError(f"unsupported route report: {report}")
