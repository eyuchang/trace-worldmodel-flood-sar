"""Non-operative contracts for inspecting staged Reference source files."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.domain.base import DeltaModel


class ReferenceArchiveMemberSpec(DeltaModel):
    """Exact archive member allowed to inform a later derived fixture."""

    relative_name: str = Field(min_length=1, max_length=500)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    maximum_bytes: int = Field(gt=0, le=2_000_000_000)


class ReferenceSourceArtifactSpec(DeltaModel):
    """Caller-rooted expectations for one already-staged, offline source."""

    source_id: str = Field(pattern=r"^(REF-SRC-[0-9]{2}|TEST-SRC-[0-9]{2})$")
    relative_name: str = Field(min_length=1, max_length=500)
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    maximum_bytes: int = Field(gt=0, le=2_000_000_000)
    media_type: Literal[
        "application/json",
        "application/geo+json",
        "application/zip",
        "image/tiff",
        "text/html",
    ]
    approval_status: Literal[
        "security-test-fixture",
        "approved-development-source-after-license-review",
    ]
    runtime_inclusion: Literal["none"]
    archive_member: ReferenceArchiveMemberSpec | None = None
    maximum_archive_members: int = Field(default=10_000, gt=0, le=100_000)
    maximum_total_uncompressed_bytes: int = Field(default=2_000_000_000, gt=0, le=4_000_000_000)
    maximum_compression_ratio: int = Field(default=200, gt=0, le=1_000)

    @model_validator(mode="after")
    def validate_archive_contract(self) -> ReferenceSourceArtifactSpec:
        if (self.media_type == "application/zip") != (self.archive_member is not None):
            raise ValueError("zip sources require exactly one declared archive member")
        return self


class ReferenceSourceInspectionReceipt(DeltaModel):
    """Deterministic inspection result; it authorizes no runtime use."""

    receipt_schema: Literal["delta-reference-source-inspection-receipt-v1"]
    source_id: str
    relative_name: str
    media_type: str
    byte_length: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_member_name: str | None = None
    archive_member_byte_length: int | None = Field(default=None, ge=0)
    archive_member_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    approval_status: str
    runtime_inclusion: Literal["none"]

    @model_validator(mode="after")
    def validate_member_fields(self) -> ReferenceSourceInspectionReceipt:
        values = (
            self.archive_member_name,
            self.archive_member_byte_length,
            self.archive_member_sha256,
        )
        if any(value is not None for value in values) and not all(
            value is not None for value in values
        ):
            raise ValueError("archive-member receipt fields must be all present or all absent")
        return self
