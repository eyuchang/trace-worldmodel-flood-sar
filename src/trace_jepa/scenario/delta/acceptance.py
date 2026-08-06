from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import Field, model_validator

from trace_jepa.scenario.delta.models import DeltaModel


class AcceptanceEnsemble(DeltaModel):
    first_seed: int = Field(ge=0)
    seed_count: int = Field(gt=0)


class AcceptanceConfirmatoryEnsemble(DeltaModel):
    derivation: str
    protocol_role: str
    seeds: list[int] = Field(min_length=100, max_length=100)

    @model_validator(mode="after")
    def validate_preregistered_seeds(self) -> AcceptanceConfirmatoryEnsemble:
        prefix = "sha256-u31:WF-DFLD-01-SMALL|confirmatory-"
        if not self.derivation.startswith(prefix) or not self.derivation.endswith("|index"):
            raise ValueError("unknown confirmatory seed derivation")
        version = self.derivation.removeprefix(prefix).removesuffix("|index")
        if version not in {"v1", "v2", "v3", "v4", "v5"}:
            raise ValueError("unsupported confirmatory protocol version")
        expected = [
            int.from_bytes(
                hashlib.sha256(
                    f"WF-DFLD-01-SMALL|confirmatory-{version}|{index}".encode()
                ).digest()[:4],
                "big",
            )
            & 0x7FFFFFFF
            for index in range(100)
        ]
        if self.seeds != expected:
            raise ValueError("confirmatory seeds disagree with the preregistered derivation")
        return self


class AcceptanceCallProcess(DeltaModel):
    expected_total_mean: float = Field(gt=0.0)
    total_mean_absolute_tolerance: float = Field(gt=0.0)
    configured_peak_intensity_per_hour: float = Field(gt=0.0)


class AcceptanceObservationChannel(DeltaModel):
    small_information_quality: float = Field(ge=0.3, le=1.0)
    expected_duplicate_fraction: float = Field(ge=0.0, le=1.0)
    expected_callback_failure_fraction: float = Field(ge=0.0, le=1.0)
    expected_false_levee_fraction: float = Field(ge=0.0, le=1.0)
    expected_multi_channel_fraction: float = Field(ge=0.0, le=1.0)
    expected_nonreporting_fraction: float = Field(ge=0.0, le=1.0)
    expected_revision_fraction: float = Field(ge=0.0, le=1.0)
    fraction_absolute_tolerance: float = Field(gt=0.0, le=1.0)


class AcceptanceDemandCapacity(DeltaModel):
    target_peak_ratio: float = Field(gt=0.0)
    book_seed_minimum: float = Field(gt=0.0)
    book_seed_maximum: float = Field(gt=0.0)
    confirmatory_median_minimum: float = Field(gt=0.0)
    confirmatory_median_maximum: float = Field(gt=0.0)
    book_allocation_share_minimum: float = Field(default=0.25, ge=0.0, le=1.0)
    book_allocation_share_maximum: float = Field(default=0.75, ge=0.0, le=1.0)


class AcceptancePerformance(DeltaModel):
    maximum_generate_run_replay_s: float = Field(gt=0.0)


class DeltaSmallAcceptanceConfig(DeltaModel):
    schema_version: str
    registered_utc: datetime
    book_seed: int = Field(ge=0)
    book_seed_role: str
    development_ensemble: AcceptanceEnsemble
    confirmatory_ensemble: AcceptanceConfirmatoryEnsemble | None = None
    amended_confirmatory_ensemble: AcceptanceConfirmatoryEnsemble | None = None
    final_confirmatory_registered_utc: datetime | None = None
    final_confirmatory_ensemble: AcceptanceConfirmatoryEnsemble | None = None
    spatial_confirmatory_registered_utc: datetime | None = None
    spatial_confirmatory_ensemble: AcceptanceConfirmatoryEnsemble | None = None
    balanced_confirmatory_registered_utc: datetime | None = None
    balanced_confirmatory_ensemble: AcceptanceConfirmatoryEnsemble | None = None
    protocol_amendment: str
    call_process: AcceptanceCallProcess
    observation_channel: AcceptanceObservationChannel
    demand_capacity: AcceptanceDemandCapacity
    performance: AcceptancePerformance

    @model_validator(mode="after")
    def validate_protocol_generation(self) -> DeltaSmallAcceptanceConfig:
        if self.schema_version == "delta-small-acceptance-v6":
            if self.balanced_confirmatory_registered_utc is None:
                raise ValueError("acceptance v6 requires a registration timestamp")
            if self.balanced_confirmatory_ensemble is None:
                raise ValueError("acceptance v6 requires confirmatory-v5 seeds")
            if "confirmatory-v5" not in self.balanced_confirmatory_ensemble.derivation:
                raise ValueError("acceptance v6 must use the untouched confirmatory-v5 ensemble")
        elif self.schema_version == "delta-small-acceptance-v5":
            historical = (
                self.confirmatory_ensemble,
                self.amended_confirmatory_ensemble,
                self.final_confirmatory_ensemble,
                self.spatial_confirmatory_ensemble,
            )
            if any(item is None for item in historical):
                raise ValueError("acceptance v5 requires all four historical ensembles")
        else:
            raise ValueError("unsupported Delta Small acceptance schema")
        return self
