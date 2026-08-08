"""Controller-visible calls, hidden lineage, and coordination models."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .base import DeltaModel
from .types import CallTaxonomy


class CallLocation(DeltaModel):
    stated: str
    easting_mm: int
    northing_mm: int
    precision_m: int = Field(gt=0)
    method: str
    confidence_milli: int = Field(ge=0, le=1000)


class ReportedCall(DeltaModel):
    call_type: CallTaxonomy
    occupants: int = Field(ge=0)
    occupants_confidence: str
    medical: tuple[str, ...]
    description_token: str


class CallQuality(DeltaModel):
    call_dropped: bool
    callback_failed: bool
    revision_of_call_id: str | None = None


class CallRecord(DeltaModel):
    call_id: str
    received_s: int = Field(ge=0)
    received_ts: datetime
    psap: str
    channel: str
    callback_token: str
    on_scene: bool
    third_party: bool
    language: str
    location: CallLocation
    reported: ReportedCall
    quality: CallQuality


class CallLineage(DeltaModel):
    call_id: str
    truth_incident_id: str | None
    truth_person_ids: tuple[str, ...]
    relationship: str


class ObservationArtifact(DeltaModel):
    schema_version: str
    calls: tuple[CallRecord, ...]
    lineage: tuple[CallLineage, ...]
    expected_calls_total: float
    peak_expected_calls_per_hour: float
    coefficients_version: str | None = None
    location_method_target_milli: dict[str, int] | None = None
    location_error_scale_milli: int | None = Field(default=None, ge=0)


class CoordinationDelivery(DeltaModel):
    call_id: str
    source_authority_id: str
    controller_authority_id: str
    available_to_controller_s: int = Field(ge=0)
    sharing_latency_s: int = Field(ge=0)


class CoordinationArtifact(DeltaModel):
    schema_version: str
    phi: int = Field(ge=1, le=9)
    logical_authority_ids: tuple[str, ...] = Field(min_length=1)
    semantics: str
    deliveries: tuple[CoordinationDelivery, ...]
