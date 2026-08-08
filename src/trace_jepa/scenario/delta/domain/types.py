"""Closed string vocabularies used by canonical Delta domain contracts."""

from typing import Literal

CallTaxonomy = Literal["C-STR", "C-VEH", "C-LEV", "C-MED", "C-WEL", "C-MIS"]
Capability = Literal[
    "water_rescue",
    "road_rescue",
    "levee_inspection",
    "medical_first_response",
    "welfare_check",
    "missing_person_search",
]
DecisionEventType = Literal["allocation", "refusal", "repair"]
OutcomeStatus = Literal["completed_within_window", "active_at_scenario_censoring"]
ReconciliationLinkStatus = Literal["confirmed", "suspected", "rejected", "superseded"]
AvailabilityMode = Literal[
    "local-from-scenario-start",
    "preauthorized-automatic-aid-fixed-staging",
]
RouteStatus = Literal["open", "blocked", "unknown"]

__all__ = [
    "AvailabilityMode",
    "CallTaxonomy",
    "Capability",
    "DecisionEventType",
    "OutcomeStatus",
    "ReconciliationLinkStatus",
    "RouteStatus",
]
