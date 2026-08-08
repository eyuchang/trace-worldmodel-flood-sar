"""Revalidation guard state for Section 5.5 model-version currency checks."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import Field

from trace_jepa.contracts.models import FrozenModel
from trace_jepa.experimental.profile import (
    AdequacyStatus,
    ExperimentalProfileExtension,
    PredictorVersionReplacement,
)
from trace_jepa.util import sha256_value, utc_now


class CalibrationIdentity(FrozenModel):
    calibration_version: str
    calibration_hash: str


class CalibrationAdequacyTable(FrozenModel):
    """Maps claim families to calibration versions that are adequate for them."""

    # claim_family -> calibration versions marked adequate for that class
    adequate_by_family: dict[str, tuple[CalibrationIdentity, ...]] = Field(default_factory=dict)

    def is_adequate(
        self,
        *,
        claim_family: str,
        calibration_version: str,
        calibration_hash: str,
    ) -> bool:
        allowed = self.adequate_by_family.get(claim_family, ())
        identity = CalibrationIdentity(
            calibration_version=calibration_version,
            calibration_hash=calibration_hash,
        )
        return identity in allowed

    def with_qualification(
        self,
        *,
        claim_family: str,
        calibration_version: str,
        calibration_hash: str,
    ) -> CalibrationAdequacyTable:
        current = list(self.adequate_by_family.get(claim_family, ()))
        identity = CalibrationIdentity(
            calibration_version=calibration_version,
            calibration_hash=calibration_hash,
        )
        if identity not in current:
            current.append(identity)
        updated = dict(self.adequate_by_family)
        updated[claim_family] = tuple(current)
        return CalibrationAdequacyTable(adequate_by_family=updated)


class RevalidationSnapshot(FrozenModel):
    """Immutable view of the guard's current version currency state."""

    current_predictor_version: str
    current_model_hash: str
    current_calibration_version: str
    current_calibration_hash: str
    adequacy: CalibrationAdequacyTable
    superseded_versions: tuple[str, ...] = ()
    last_replacement: PredictorVersionReplacement | None = None
    updated_at: datetime = Field(default_factory=utc_now)


@dataclass
class RevalidationGuard:
    """Mutable mid-mission registry consulted by the TRACE gate.

    The guard records predictor replacements as structural events and exposes
    two named checks used by ``PolicyEngine``:

    - ``model_version_current``
    - ``calibration_adequate_for_class``
    """

    current_predictor_version: str
    current_model_hash: str
    current_calibration_version: str
    current_calibration_hash: str
    adequacy: CalibrationAdequacyTable = field(default_factory=CalibrationAdequacyTable)
    superseded_versions: set[str] = field(default_factory=set)
    replacements: list[PredictorVersionReplacement] = field(default_factory=list)
    transition_log: list[dict[str, Any]] = field(default_factory=list)
    restored_ordinary_operation_at: float | None = None
    replacement_simulation_time_s: float | None = None

    @classmethod
    def bootstrap(
        cls,
        *,
        predictor_version: str,
        calibration_version: str,
        model_hash: str | None = None,
        calibration_hash: str | None = None,
        qualified_families: Iterable[str] = (),
    ) -> RevalidationGuard:
        digest = model_hash or sha256_value(
            {
                "predictor_version": predictor_version,
                "calibration_version": calibration_version,
            }
        )
        calibration_digest = calibration_hash or sha256_value(
            {"calibration_version": calibration_version}
        )
        adequacy = CalibrationAdequacyTable(
            adequate_by_family={
                family: (
                    CalibrationIdentity(
                        calibration_version=calibration_version,
                        calibration_hash=calibration_digest,
                    ),
                )
                for family in qualified_families
            }
        )
        guard = cls(
            current_predictor_version=predictor_version,
            current_model_hash=digest,
            current_calibration_version=calibration_version,
            current_calibration_hash=calibration_digest,
            adequacy=adequacy,
        )
        guard._log_transition(
            "bootstrap",
            {
                "predictor_version": predictor_version,
                "model_hash": digest,
                "calibration_version": calibration_version,
                "calibration_hash": calibration_digest,
            },
        )
        return guard

    def snapshot(self) -> RevalidationSnapshot:
        return RevalidationSnapshot(
            current_predictor_version=self.current_predictor_version,
            current_model_hash=self.current_model_hash,
            current_calibration_version=self.current_calibration_version,
            current_calibration_hash=self.current_calibration_hash,
            adequacy=self.adequacy,
            superseded_versions=tuple(sorted(self.superseded_versions)),
            last_replacement=self.replacements[-1] if self.replacements else None,
        )

    def replace_predictor(
        self,
        *,
        new_predictor_version: str,
        new_calibration_version: str,
        new_model_hash: str | None = None,
        new_calibration_hash: str | None = None,
        simulation_time_s: float,
        initially_unqualified_families: Iterable[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> PredictorVersionReplacement:
        new_hash = new_model_hash or sha256_value(
            {
                "predictor_version": new_predictor_version,
                "calibration_version": new_calibration_version,
            }
        )
        new_calibration_digest = new_calibration_hash or sha256_value(
            {"calibration_version": new_calibration_version}
        )
        event = PredictorVersionReplacement(
            old_predictor_version=self.current_predictor_version,
            new_predictor_version=new_predictor_version,
            old_model_hash=self.current_model_hash,
            new_model_hash=new_hash,
            old_calibration_version=self.current_calibration_version,
            old_calibration_hash=self.current_calibration_hash,
            new_calibration_version=new_calibration_version,
            new_calibration_hash=new_calibration_digest,
            new_adequacy_status=AdequacyStatus.UNQUALIFIED,
            simulation_time_s=simulation_time_s,
            metadata=metadata or {},
        )
        self.superseded_versions.add(self.current_predictor_version)
        self.current_predictor_version = new_predictor_version
        self.current_model_hash = new_hash
        self.current_calibration_version = new_calibration_version
        self.current_calibration_hash = new_calibration_digest
        # Successor starts unqualified for the listed high-consequence families.
        updated = dict(self.adequacy.adequate_by_family)
        for family in initially_unqualified_families:
            allowed = [
                identity
                for identity in updated.get(family, ())
                if identity
                != CalibrationIdentity(
                    calibration_version=new_calibration_version,
                    calibration_hash=new_calibration_digest,
                )
            ]
            updated[family] = tuple(allowed)
        self.adequacy = CalibrationAdequacyTable(adequate_by_family=updated)
        self.replacements.append(event)
        self.replacement_simulation_time_s = simulation_time_s
        self.restored_ordinary_operation_at = None
        self._log_transition("predictor_version_replacement", event.to_store_payload())
        return event

    def qualify_calibration(
        self,
        *,
        claim_family: str,
        calibration_version: str | None = None,
        calibration_hash: str | None = None,
        simulation_time_s: float | None = None,
    ) -> None:
        version = calibration_version or self.current_calibration_version
        digest = calibration_hash or self.current_calibration_hash
        self.adequacy = self.adequacy.with_qualification(
            claim_family=claim_family,
            calibration_version=version,
            calibration_hash=digest,
        )
        if simulation_time_s is not None and self.restored_ordinary_operation_at is None:
            self.restored_ordinary_operation_at = simulation_time_s
        self._log_transition(
            "calibration_qualified",
            {
                "claim_family": claim_family,
                "calibration_version": version,
                "calibration_hash": digest,
                "simulation_time_s": simulation_time_s,
            },
        )

    def model_version_current(self, profile: ExperimentalProfileExtension) -> bool:
        if profile.predictor_version in self.superseded_versions:
            return False
        if profile.adequacy_status == AdequacyStatus.SUPERSEDED:
            return False
        if profile.predictor_version != self.current_predictor_version:
            return False
        return profile.model_hash is not None and profile.model_hash == self.current_model_hash

    def calibration_adequate_for_class(
        self,
        profile: ExperimentalProfileExtension,
    ) -> bool:
        if profile.adequacy_status in {
            AdequacyStatus.UNQUALIFIED,
            AdequacyStatus.PENDING_REVALIDATION,
            AdequacyStatus.SUPERSEDED,
        }:
            return False
        if profile.calibration_hash is None:
            return False
        if profile.calibration_version != self.current_calibration_version:
            return False
        if profile.calibration_hash != self.current_calibration_hash:
            return False
        return self.adequacy.is_adequate(
            claim_family=profile.claim_family,
            calibration_version=profile.calibration_version,
            calibration_hash=profile.calibration_hash,
        )

    def time_to_restored_ordinary_operation(self) -> float | None:
        if (
            self.replacement_simulation_time_s is None
            or self.restored_ordinary_operation_at is None
        ):
            return None
        return self.restored_ordinary_operation_at - self.replacement_simulation_time_s

    def _log_transition(self, event_type: str, payload: dict[str, Any]) -> None:
        self.transition_log.append(
            {
                "event_type": event_type,
                "recorded_at": utc_now().isoformat(),
                "payload": payload,
            }
        )
