from __future__ import annotations

from trace_jepa.contracts import ActionInstance, PlanCandidate


class FloodPlanner:
    """Candidate generator inside the Mission Controller.

    It proposes structurally possible actions. It does not predict consequences
    and does not authorize execution.
    """

    version = "flood-planner-v2"

    def propose(self, observation: dict) -> list[PlanCandidate]:
        mission = observation["mission"]
        candidates: list[PlanCandidate] = []

        for route_id, route in observation["routes"].items():
            report = route["report"]
            label = route["label"]

            if report != "blocked":
                action = ActionInstance(
                    action_type="dispatch_rescue_boat",
                    actor_id="rescue_boat_1",
                    origin=mission["origin_id"],
                    destination=mission["destination_id"],
                    route_id=route_id,
                    parameters={
                        "people_count": int(mission["people_to_rescue"]),
                        "deadline_s": int(mission["deadline_s"]),
                    },
                )
                travel_s = float(route["nominal_travel_s"])
                utility = max(0.0, 1.0 - 0.35 * travel_s / float(mission["deadline_s"]))
                plan_id = "north-direct" if route_id == "north_channel" else "south-detour"
                candidates.append(
                    PlanCandidate(
                        plan_id=plan_id,
                        name=(
                            f"Dispatch rescue_boat_1 from {mission['origin_id']} "
                            f"to {mission['destination_id']} via {label}"
                        ),
                        actions=(action,),
                        utility=utility,
                        reversible_first_action=False,
                        requires_authority=True,
                        metadata={
                            "route_id": route_id,
                            "route_report": report,
                            "mission_destination": mission["destination_id"],
                        },
                    )
                )

            if report == "unknown":
                action = ActionInstance(
                    action_type="verify_route",
                    actor_id="survey_drone_1",
                    origin="drone_pad",
                    destination=route_id,
                    route_id=route_id,
                    parameters={"purpose": "resolve_route_access"},
                )
                candidates.append(
                    PlanCandidate(
                        plan_id="verify-north" if route_id == "north_channel" else f"verify-{route_id}",
                        name=f"Send survey_drone_1 to verify {label}",
                        actions=(action,),
                        utility=0.90,
                        reversible_first_action=True,
                        requires_authority=False,
                        metadata={
                            "route_id": route_id,
                            "information_gathering": True,
                        },
                    )
                )

        return candidates

    @staticmethod
    def choose(candidates: list[tuple[PlanCandidate, str]]) -> PlanCandidate | None:
        admissible = [
            plan for plan, decision in candidates if decision in {"clear", "qualify"}
        ]
        return max(admissible, key=lambda plan: plan.utility, default=None)
