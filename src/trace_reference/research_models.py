"""Typed, non-operative research records for Reference source reconciliation."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel


class ReferenceResearchPoint(DeltaModel):
    """An agency-published point retained only for identity research."""

    latitude_e6: int = Field(ge=-90_000_000, le=90_000_000)
    longitude_e6: int = Field(ge=-180_000_000, le=180_000_000)
    precision_status: Literal["inventory-point-not-survey-control"]


class ReferenceEntitySourceCrosswalkEntry(DeltaModel):
    """One design entity reconciled against official records without runtime binding."""

    entity_id: str = Field(pattern=r"^(ISL|TWN|XNG)-[0-9]{2}$")
    design_name: str = Field(min_length=3)
    research_status: Literal[
        "official-record-supports-design",
        "official-record-corrects-design",
        "official-record-raises-current-status-question",
        "multiple-official-records-require-spatial-crosswalk",
        "source-identified-binding-pending",
    ]
    source_requirement_ids: tuple[str, ...] = Field(min_length=1)
    official_identifiers: tuple[str, ...]
    official_point: ReferenceResearchPoint | None = None
    evidence_locators: tuple[str, ...] = Field(min_length=1)
    binding_status: Literal["unbound"]
    runtime_inclusion: Literal["none"]
    redistribution_disposition: Literal["factual-metadata-only-no-source-bytes-committed"]
    findings: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_research_disposition(self) -> ReferenceEntitySourceCrosswalkEntry:
        if any(not value.startswith("REF-SRC-") for value in self.source_requirement_ids):
            raise ValueError("crosswalk source references must use Reference source IDs")
        if any(not locator.startswith("https://") for locator in self.evidence_locators):
            raise ValueError("crosswalk evidence must use HTTPS official locators")
        if self.research_status == "source-identified-binding-pending" and (
            self.official_identifiers
        ):
            raise ValueError("unretrieved source candidates cannot assert official identifiers")
        return self


class ReferenceEntitySourceCrosswalk(DeltaModel):
    """Complete 22-entity research ledger; all topology remains non-operative."""

    registry_version: Literal["delta-reference-entity-source-crosswalk-v1"]
    scientific_status: Literal["research-draft-no-runtime-bindings"]
    verified_date: str = Field(pattern=r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}$")
    entries: tuple[ReferenceEntitySourceCrosswalkEntry, ...] = Field(min_length=22, max_length=22)

    @model_validator(mode="after")
    def validate_complete_nonoperative_inventory(self) -> ReferenceEntitySourceCrosswalk:
        expected = (
            *(f"ISL-{index:02d}" for index in range(1, 9)),
            *(f"TWN-{index:02d}" for index in range(1, 5)),
            *(f"XNG-{index:02d}" for index in range(1, 11)),
        )
        if tuple(entry.entity_id for entry in self.entries) != expected:
            raise ValueError("entity/source crosswalk is incomplete or unordered")
        if any(entry.binding_status != "unbound" for entry in self.entries):
            raise ValueError("research crosswalk cannot bind operational topology")
        if any(entry.runtime_inclusion != "none" for entry in self.entries):
            raise ValueError("research crosswalk cannot become an implicit runtime input")
        return self
