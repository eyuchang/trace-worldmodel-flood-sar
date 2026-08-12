"""Synthetic, privacy-preserving exposure contracts for Reference."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel
from trace_reference.geography.catalog_models import ReferenceMetricPoint


class ReferenceIslandExposureAllocation(DeltaModel):
    island_id: str = Field(pattern=r"^ISL-0[1-8]$")
    synthetic_people: int = Field(gt=0)
    synthetic_structures: int = Field(gt=0)


class ReferenceExposureParameters(DeltaModel):
    parameter_version: Literal["delta-reference-exposure-parameters-v1"]
    profile_id: Literal["reference-exposure-v1"]
    scientific_status: Literal["synthetic-teaching-cohort-not-demographic-reconstruction"]
    randomness_namespace: Literal["delta-reference-randomness-v1"]
    minimum_structure_separation_m: int = Field(ge=10, le=100)
    island_allocations: tuple[ReferenceIslandExposureAllocation, ...] = Field(
        min_length=8, max_length=8
    )
    limited_mobility_rate_micros: int = Field(ge=0, le=1_000_000)
    wheelchair_rate_micros: int = Field(ge=0, le=1_000_000)
    oxygen_dependency_rate_micros: int = Field(ge=0, le=1_000_000)
    dialysis_dependency_rate_micros: int = Field(ge=0, le=1_000_000)
    insulin_dependency_rate_micros: int = Field(ge=0, le=1_000_000)
    non_english_access_rate_micros: int = Field(ge=0, le=1_000_000)
    no_transport_rate_micros: int = Field(ge=0, le=1_000_000)
    daytime_away_rate_micros: int = Field(ge=0, le=1_000_000)
    nighttime_away_rate_micros: int = Field(ge=0, le=1_000_000)
    limitations: tuple[str, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_scale_and_order(self) -> ReferenceExposureParameters:
        if tuple(item.island_id for item in self.island_allocations) != tuple(
            f"ISL-{index:02d}" for index in range(1, 9)
        ):
            raise ValueError("Reference exposure allocations must cover the eight islands in order")
        if sum(item.synthetic_people for item in self.island_allocations) != 1_400:
            raise ValueError(
                "Reference exposure profile must contain exactly 1,400 synthetic people"
            )
        if sum(item.synthetic_structures for item in self.island_allocations) != 420:
            raise ValueError(
                "Reference exposure profile must contain exactly 420 synthetic structures"
            )
        if self.daytime_away_rate_micros + self.nighttime_away_rate_micros > 1_000_000:
            raise ValueError("Reference movement-pattern rates exceed one")
        return self


class ReferenceSyntheticStructure(DeltaModel):
    truth_structure_id: str = Field(pattern=r"^RS-[0-9a-f]{16}$")
    island_id: str = Field(pattern=r"^ISL-0[1-8]$")
    location: ReferenceMetricPoint
    synthetic_capacity: int = Field(ge=4, le=6)
    vulnerability_micros: int = Field(ge=0, le=1_000_000)
    utility_resilience_micros: int = Field(ge=0, le=1_000_000)
    animal_units: int = Field(ge=0, le=8)
    location_semantics: Literal["seeded-point-inside-simulation-footprint-not-a-real-address"]


class ReferenceTrajectoryChangePoint(DeltaModel):
    at_s: int = Field(ge=-172_800, le=345_600)
    state: Literal["home", "away-synthetic-activity"]
    synthetic_structure_id: str = Field(pattern=r"^RS-[0-9a-f]{16}$")
    location: ReferenceMetricPoint


class ReferenceSyntheticPerson(DeltaModel):
    truth_person_id: str = Field(pattern=r"^RP-[0-9a-f]{16}$")
    home_structure_id: str = Field(pattern=r"^RS-[0-9a-f]{16}$")
    island_id: str = Field(pattern=r"^ISL-0[1-8]$")
    mobility: Literal["standard", "limited", "wheelchair"]
    medical_dependency: Literal["none", "oxygen", "dialysis", "insulin"]
    language_access: Literal["english", "spanish", "tagalog", "chinese"]
    transport_access: Literal["available", "unavailable"]
    occupancy_pattern: Literal["home-static", "daytime-away", "nighttime-away"]
    vulnerability_micros: int = Field(ge=0, le=1_000_000)
    synthetic_callback_token: str = Field(pattern=r"^SYN-CB-[0-9a-f]{16}$")
    trajectory: tuple[ReferenceTrajectoryChangePoint, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_trajectory(self) -> ReferenceSyntheticPerson:
        if self.trajectory[0].at_s != -172_800:
            raise ValueError("every Reference person trajectory must begin at burn-in start")
        times = tuple(item.at_s for item in self.trajectory)
        if times != tuple(sorted(set(times))):
            raise ValueError("Reference trajectory change points must be unique and ordered")
        return self


class ReferenceExposureScenario(DeltaModel):
    scenario_id: Literal["WF-DFLD-01-REFERENCE"]
    schema_version: Literal["delta-reference-exposure-v1"]
    parameter_version: Literal["delta-reference-exposure-parameters-v1"]
    profile_id: Literal["reference-exposure-v1"]
    seed: int = Field(ge=0)
    epsilon_micros: int = Field(ge=300_000, le=2_000_000)
    structures: tuple[ReferenceSyntheticStructure, ...] = Field(min_length=420, max_length=420)
    people: tuple[ReferenceSyntheticPerson, ...] = Field(min_length=1_400, max_length=1_400)
    exposure_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_identifiers_and_membership(self) -> ReferenceExposureScenario:
        structure_ids = tuple(item.truth_structure_id for item in self.structures)
        person_ids = tuple(item.truth_person_id for item in self.people)
        callback_tokens = tuple(item.synthetic_callback_token for item in self.people)
        if len(set(structure_ids)) != len(structure_ids):
            raise ValueError("Reference truth structure identifiers must be unique")
        if len(set(person_ids)) != len(person_ids):
            raise ValueError("Reference truth person identifiers must be unique")
        if len(set(callback_tokens)) != len(callback_tokens):
            raise ValueError("Reference synthetic callback tokens must be unique")
        structure_by_id = {item.truth_structure_id: item for item in self.structures}
        occupants_by_structure = dict.fromkeys(structure_ids, 0)
        for person in self.people:
            home = structure_by_id.get(person.home_structure_id)
            if home is None or home.island_id != person.island_id:
                raise ValueError("Reference person home membership is invalid")
            if any(
                point.synthetic_structure_id not in structure_by_id
                or structure_by_id[point.synthetic_structure_id].island_id != person.island_id
                for point in person.trajectory
            ):
                raise ValueError("Reference trajectory must remain in the person's exposure island")
            occupants_by_structure[person.home_structure_id] += 1
        if any(
            occupants_by_structure[item.truth_structure_id] > item.synthetic_capacity
            for item in self.structures
        ):
            raise ValueError("Reference synthetic structure capacity is exceeded")
        return self
