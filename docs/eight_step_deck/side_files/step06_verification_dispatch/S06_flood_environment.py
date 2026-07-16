from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from trace_jepa.contracts import ActionInstance, EmergencyCall, RealizedOutcome


@dataclass
class FloodEnvironment:
    """The simulated flood world.

    The environment owns hidden ground truth. The Mission Controller receives
    only :meth:`observe`. Hidden route status is revealed only after a declared
    sensing action or through the consequence of an executed action.
    """

    scenario: dict[str, Any]
    north_route_verified: bool = False
    rescued: bool = False
    active_call: EmergencyCall | None = None

    @classmethod
    def from_yaml(cls, path: str | Path) -> "FloodEnvironment":
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(scenario=payload)

    @property
    def scenario_id(self) -> str:
        return str(self.scenario["scenario_version"])

    def _route_status(self, route_id: str) -> str:
        return str(self.scenario["routes"][route_id]["hidden_status"])

    def register_emergency_call(self, call: EmergencyCall) -> None:
        """Ground an emergency report into the active mission.

        The call may change the pickup location, number of residents, and
        deadline. It does not reveal hidden route truth.
        """

        if call.normalized_location_id not in self.scenario["locations"]:
            raise ValueError(
                f"unknown scenario location: {call.normalized_location_id}"
            )
        self.active_call = call
        self.scenario["mission"]["pickup_location"] = call.normalized_location_id
        self.scenario["mission"]["people_to_rescue"] = call.people_count
        self.scenario["mission"]["deadline_s"] = call.deadline_s

    def observe(self) -> dict[str, Any]:
        """Return only information legitimately available to Mission Control."""

        routes: dict[str, dict[str, Any]] = {}
        for route_id, route in self.scenario["routes"].items():
            verified = route_id != "north_channel" or self.north_route_verified
            report = self._route_status(route_id) if verified else str(route["initial_report"])
            routes[route_id] = {
                "label": route["label"],
                "report": report,
                "verified": verified,
                "nominal_travel_s": float(route["nominal_travel_s"]),
                "waypoints": route["waypoints"],
            }

        assets = {
            asset_id: dict(spec)
            for asset_id, spec in self.scenario["assets"].items()
        }
        mission = dict(self.scenario["mission"])

        return {
            "scenario_id": self.scenario_id,
            "mission": {
                "origin_id": mission["origin"],
                "destination_id": mission["pickup_location"],
                "people_to_rescue": int(mission["people_to_rescue"]),
                "deadline_s": int(mission["deadline_s"]),
                "deadline_minutes": int(mission["deadline_s"]) // 60,
            },
            "assets": assets,
            "routes": routes,
            "locations": dict(self.scenario["locations"]),
            "weather_severity": float(self.scenario["conditions"]["weather_severity"]),
            # Flat compatibility fields used by the first fusion model.
            "drone_battery": float(assets["survey_drone_1"]["battery"]),
            "boat_capacity": int(assets["rescue_boat_1"]["capacity"]),
            "north_route_verified": self.north_route_verified,
            "north_route_open": (
                self._route_status("north_channel") == "open"
                if self.north_route_verified
                else None
            ),
            "south_route_open": self._route_status("south_detour") == "open",
            "stranded_people": int(mission["people_to_rescue"]),
            "emergency_call": (
                {
                    "call_id": self.active_call.call_id,
                    "reported_location": self.active_call.reported_location,
                    "normalized_location_id": self.active_call.normalized_location_id,
                    "people_count": self.active_call.people_count,
                    "deadline_s": self.active_call.deadline_s,
                    "source": self.active_call.source,
                    "received_at": self.active_call.received_at.isoformat(),
                }
                if self.active_call is not None
                else None
            ),
        }

    def simulation_ground_truth(self) -> dict[str, Any]:
        """Return hidden truth for tests and after-the-fact evaluation only."""

        return {
            "scenario_id": self.scenario_id,
            "route_status": {
                route_id: route["hidden_status"]
                for route_id, route in self.scenario["routes"].items()
            },
            "stranded_people": int(self.scenario["mission"]["people_to_rescue"]),
            "rescued": self.rescued,
            "active_call_id": self.active_call.call_id if self.active_call else None,
        }

    def execute(self, action: ActionInstance) -> RealizedOutcome:
        """Apply one authorized action and return what the world reveals."""

        if action.action_type == "verify_route":
            if action.actor_id != "survey_drone_1":
                raise ValueError("only survey_drone_1 can execute verify_route")
            if action.route_id is None:
                raise ValueError("verify_route requires route_id")

            cost = float(self.scenario["conditions"]["verification_battery_cost"])
            current = float(self.scenario["assets"]["survey_drone_1"]["battery"])
            new_battery = max(0.0, current - cost)
            self.scenario["assets"]["survey_drone_1"]["battery"] = new_battery
            if action.route_id == "north_channel":
                self.north_route_verified = True

            return RealizedOutcome(
                action=action,
                success=True,
                observations={
                    "route_id": action.route_id,
                    "route_status": self._route_status(action.route_id),
                    "drone_battery": new_battery,
                    "source": action.actor_id,
                },
                reason="route_observed",
            )

        if action.action_type == "dispatch_rescue_boat":
            if action.actor_id != "rescue_boat_1":
                raise ValueError("only rescue_boat_1 can execute dispatch_rescue_boat")
            if action.route_id is None:
                raise ValueError("dispatch_rescue_boat requires route_id")

            route_open = self._route_status(action.route_id) == "open"
            capacity = int(self.scenario["assets"]["rescue_boat_1"]["capacity"])
            needed = int(action.parameters["people_count"])
            success = route_open and capacity >= needed
            self.rescued = bool(success)

            return RealizedOutcome(
                action=action,
                success=bool(success),
                observations={
                    "route_id": action.route_id,
                    "route_status": self._route_status(action.route_id),
                    "people_reached": needed if success else 0,
                    "destination": action.destination,
                },
                reason="rescue_completed" if success else "route_blocked_or_capacity_insufficient",
            )

        raise ValueError(f"unknown action type: {action.action_type}")
