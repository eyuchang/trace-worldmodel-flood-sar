from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from trace_jepa.contracts import EmergencyCall


class EmergencyCallIntakeError(ValueError):
    """Raised when an emergency call cannot be grounded to the scenario."""


_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _incident_locations(scenario: dict[str, Any]) -> dict[str, dict[str, Any]]:
    locations = scenario.get("locations", {})
    return {
        location_id: spec
        for location_id, spec in locations.items()
        if str(spec.get("kind", "incident_site")) == "incident_site"
    }


def known_incident_locations(scenario: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(spec.get("label", location_id))
        for location_id, spec in _incident_locations(scenario).items()
    )


def resolve_location(
    scenario: dict[str, Any],
    *,
    raw_text: str,
    explicit_location: str | None = None,
) -> tuple[str, str]:
    """Return ``(location_id, human label)`` for a call.

    The first teaching scenario intentionally uses a closed location registry.
    Real deployments would replace this resolver with address validation and a
    geospatial service, but the normalized location remains an auditable field.
    """

    locations = _incident_locations(scenario)
    if not locations:
        raise EmergencyCallIntakeError("scenario defines no incident-site locations")

    haystack = _normalize(explicit_location or raw_text)
    matches: list[tuple[int, str, str]] = []

    for location_id, spec in locations.items():
        label = str(spec.get("label", location_id))
        aliases = [location_id, label, *[str(item) for item in spec.get("aliases", [])]]
        for alias in aliases:
            normalized_alias = _normalize(alias)
            if normalized_alias and normalized_alias in haystack:
                matches.append((len(normalized_alias), location_id, label))

    if not matches:
        available = ", ".join(known_incident_locations(scenario))
        raise EmergencyCallIntakeError(
            "could not match an incident location. "
            f"Known locations for this teaching scenario: {available}. "
            "Use --location with one of those labels."
        )

    _, location_id, label = max(matches)
    return location_id, label


def parse_people_count(raw_text: str, explicit_people: int | None = None) -> int:
    if explicit_people is not None:
        if explicit_people < 1:
            raise EmergencyCallIntakeError("people count must be at least 1")
        return explicit_people

    normalized = _normalize(raw_text)
    digit_match = re.search(
        r"\b(\d{1,3})\s+(?:people|persons|residents|adults|children|victims|stranded)\b",
        normalized,
    )
    if digit_match:
        count = int(digit_match.group(1))
        if count >= 1:
            return count

    for word, count in _NUMBER_WORDS.items():
        if re.search(
            rf"\b{word}\s+(?:people|persons|residents|adults|children|victims|stranded)\b",
            normalized,
        ):
            return count

    raise EmergencyCallIntakeError(
        "could not determine how many people need rescue. "
        "Include wording such as 'four residents' or pass --people 4."
    )


@dataclass(frozen=True)
class EmergencyCallIntake:
    """Deterministic teaching intake for one emergency phone call."""

    scenario: dict[str, Any]

    def parse(
        self,
        raw_text: str,
        *,
        location: str | None = None,
        people: int | None = None,
        deadline_minutes: int | None = None,
        caller_name: str | None = None,
        caller_contact: str | None = None,
    ) -> EmergencyCall:
        if not raw_text.strip():
            raise EmergencyCallIntakeError("emergency call text cannot be empty")

        location_id, label = resolve_location(
            self.scenario,
            raw_text=raw_text,
            explicit_location=location,
        )
        people_count = parse_people_count(raw_text, explicit_people=people)

        default_deadline_s = int(self.scenario.get("mission", {}).get("deadline_s", 1200))
        deadline_s = (
            int(deadline_minutes) * 60
            if deadline_minutes is not None
            else default_deadline_s
        )
        if deadline_s < 60:
            raise EmergencyCallIntakeError("deadline must be at least one minute")

        return EmergencyCall(
            raw_text=raw_text.strip(),
            reported_location=location or label,
            normalized_location_id=location_id,
            people_count=people_count,
            deadline_s=deadline_s,
            caller_name=caller_name,
            caller_contact=caller_contact,
        )
