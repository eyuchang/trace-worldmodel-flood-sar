"""Generate the five bounded feature-off G3 characterization manifests."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from trace_jepa.support import atomic_write_bytes, canonical_json_bytes, safe_directory
from trace_reference import load_reference_fault_schedule
from trace_reference.decision import (
    AcquisitionOutcomeReceipt,
    ProviderReceipt,
    ReferencePhysicalEvidence,
)
from trace_reference.decision.canonical import decision_digest
from trace_reference.domain import (
    ReferenceDecisionHandoffArtifact,
    ReferenceEvent,
    ReferenceEventType,
    ReferenceEventVisibility,
    ReferencePublicArtifactEnvelope,
)
from trace_reference.generation import generate_reference_scenario
from trace_reference.runtime import ReferenceRuntimeBundle, build_reference_runtime
from trace_reference.runtime.mission_state import reference_scenario_input_digest

from .g3_characterization_models import (
    ReferenceG3AcquisitionOutcomeStatus,
    ReferenceG3ArtifactFamily,
    ReferenceG3ArtifactFamilyDigest,
    ReferenceG3CharacterizationFixtureManifest,
    ReferenceG3CharacterizationIndex,
    ReferenceG3FallbackDisposition,
    ReferenceG3FixtureId,
    ReferenceG3RuntimeProfileId,
)
from .g3_integrity import ReferenceG3IntegrityInput, build_reference_g3_integrity_report

_FAULT_SCHEDULE = Path("data/scenario/delta/reference_protocol/reference_fault_schedule_v1.json")
_CRASH_AT_S = 187_200


@dataclass(frozen=True)
class _FixtureSpec:
    fixture_id: ReferenceG3FixtureId
    seed: int
    runtime_profile_id: ReferenceG3RuntimeProfileId
    families: tuple[ReferenceG3ArtifactFamilyDigest, ...]
    acquisition_outcome_status: ReferenceG3AcquisitionOutcomeStatus | None = None
    physical_evidence_count: int = 0
    selected_catalog_bundle_count: int | None = None
    fallback_disposition: ReferenceG3FallbackDisposition | None = None
    restart_public_state_equivalent: bool | None = None
    restart_durable_state_equivalent: bool | None = None


def _canonical_value(value: object) -> object:
    return value.model_dump(mode="json") if isinstance(value, BaseModel) else value


def _family_digest(
    family: ReferenceG3ArtifactFamily,
    values: Iterable[object],
) -> ReferenceG3ArtifactFamilyDigest:
    digest = hashlib.sha256()
    total = 0
    count = 0
    digest.update(family.encode("utf-8"))
    digest.update(b"\0")
    for value in values:
        payload = canonical_json_bytes(_canonical_value(value))
        digest.update(str(len(payload)).encode("ascii"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
        total += len(payload)
        count += 1
    return ReferenceG3ArtifactFamilyDigest(
        family=family,
        member_count=count,
        canonical_byte_length=total,
        aggregate_sha256=digest.hexdigest(),
    )


def _artifact_value(event: ReferenceEvent) -> dict[str, object]:
    envelope = ReferencePublicArtifactEnvelope.model_validate_json(event.payload_json)
    value = json.loads(envelope.artifact_json)
    if not isinstance(value, dict):
        raise TypeError("Reference G3 public artifact root must be an object")
    return value


def _handoffs(events: Iterable[ReferenceEvent]) -> Iterator[ReferenceDecisionHandoffArtifact]:
    for event in events:
        if event.event_type == ReferenceEventType.DECISION_MANIFEST_RECORDED:
            yield ReferenceDecisionHandoffArtifact.model_validate(_artifact_value(event))


def _runtime_families(
    bundle: ReferenceRuntimeBundle,
    *,
    events: Sequence[ReferenceEvent] | None = None,
) -> tuple[ReferenceG3ArtifactFamilyDigest, ...]:
    selected_events = tuple(
        event
        for event in (bundle.event_log.events if events is None else events)
        if event.visibility == ReferenceEventVisibility.CONTROLLER_VISIBLE
    )
    families = (
        _family_digest("commitment-chain", bundle.commitment_log.chain_entries()),
        _family_digest(
            "decision-costs",
            (item.cost_delta for item in _handoffs(selected_events)),
        ),
        _family_digest("decision-handoffs", _handoffs(selected_events)),
        _family_digest("evidence-chain", bundle.evidence_ledger.chain_entries()),
        _family_digest("public-events", selected_events),
        _family_digest("trace-chain", bundle.trace_repository.chain_entries()),
    )
    return tuple(sorted(families, key=lambda item: item.family))


def _fixture(spec: _FixtureSpec) -> ReferenceG3CharacterizationFixtureManifest:
    body = {
        "schema_version": "delta-reference-g3-characterization-fixture-v1",
        "scientific_status": "development-characterization-not-validation-evidence",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "scenario_seed": spec.seed,
        "fixture_id": spec.fixture_id,
        "runtime_profile_id": spec.runtime_profile_id,
        "through_s": 345_600,
        "selector_id": "reference-base-selector-v1",
        "public_model_id": "reference-public-one-step-model-v1",
        "decision_extension_id": None,
        "artifact_families": [item.model_dump(mode="json") for item in spec.families],
        "acquisition_outcome_status": spec.acquisition_outcome_status,
        "physical_evidence_count": spec.physical_evidence_count,
        "selected_catalog_bundle_count": spec.selected_catalog_bundle_count,
        "fallback_disposition": spec.fallback_disposition,
        "restart_public_state_equivalent": spec.restart_public_state_equivalent,
        "restart_durable_state_equivalent": spec.restart_durable_state_equivalent,
        "leap_implementation_present": False,
        "effectiveness_evidence_present": False,
    }
    return ReferenceG3CharacterizationFixtureManifest(
        **body,
        fixture_digest=decision_digest(body),
    )


def _events_for_success(bundle: ReferenceRuntimeBundle) -> tuple[ReferenceEvent, ...]:
    events = bundle.event_log.events
    receipt_event = next(
        event
        for event in events
        if event.event_type == ReferenceEventType.PROVIDER_RECEIPT_RECORDED
        and ProviderReceipt.model_validate(_artifact_value(event)).status == "success"
    )
    receipt = ProviderReceipt.model_validate(_artifact_value(receipt_event))
    outcome_event = next(
        event
        for event in events
        if event.event_type == ReferenceEventType.ACQUISITION_OUTCOME_RECORDED
        and AcquisitionOutcomeReceipt.model_validate(_artifact_value(event)).provider_receipt_id
        == receipt.receipt_id
    )
    outcome = AcquisitionOutcomeReceipt.model_validate(_artifact_value(outcome_event))
    if outcome.outcome_status != "evidence-accepted":
        raise RuntimeError("Reference nominal acquisition did not accept physical evidence")
    evidence_event = next(
        event
        for event in events
        if event.event_type == ReferenceEventType.PHYSICAL_EVIDENCE_RECORDED
        and ReferencePhysicalEvidence.model_validate(_artifact_value(event)).provider_receipt_id
        == receipt.receipt_id
    )
    request_event = next(
        event
        for event in events
        if event.event_type == ReferenceEventType.ACQUISITION_REQUESTED
        and _artifact_value(event)["request_id"] == receipt.request_id
    )
    reassessment = next(
        event
        for event in events
        if event.event_type == ReferenceEventType.DECISION_MANIFEST_RECORDED
        and ReferenceDecisionHandoffArtifact.model_validate(
            _artifact_value(event)
        ).manifest.acquisition_outcome_digest
        == outcome.outcome_digest
    )
    return tuple(
        sorted(
            (request_event, receipt_event, outcome_event, evidence_event, reassessment),
            key=lambda event: event.sequence,
        )
    )


def _events_for_timeout(bundle: ReferenceRuntimeBundle) -> tuple[ReferenceEvent, ...]:
    events = bundle.event_log.events
    receipt_event = next(
        event
        for event in events
        if event.event_type == ReferenceEventType.PROVIDER_RECEIPT_RECORDED
        and ProviderReceipt.model_validate(_artifact_value(event)).status == "timeout"
    )
    receipt = ProviderReceipt.model_validate(_artifact_value(receipt_event))
    outcome_event = next(
        event
        for event in events
        if event.event_type == ReferenceEventType.ACQUISITION_OUTCOME_RECORDED
        and AcquisitionOutcomeReceipt.model_validate(_artifact_value(event)).provider_receipt_id
        == receipt.receipt_id
    )
    outcome = AcquisitionOutcomeReceipt.model_validate(_artifact_value(outcome_event))
    if outcome.outcome_status != "provider-timeout":
        raise RuntimeError("Reference timeout fixture has the wrong acquisition status")
    matching_evidence = tuple(
        event
        for event in events
        if event.event_type == ReferenceEventType.PHYSICAL_EVIDENCE_RECORDED
        and ReferencePhysicalEvidence.model_validate(_artifact_value(event)).provider_receipt_id
        == receipt.receipt_id
    )
    if matching_evidence:
        raise RuntimeError("Reference timeout fixture fabricated physical evidence")
    request_event = next(
        event
        for event in events
        if event.event_type == ReferenceEventType.ACQUISITION_REQUESTED
        and _artifact_value(event)["request_id"] == receipt.request_id
    )
    reassessment = next(
        event
        for event in events
        if event.event_type == ReferenceEventType.DECISION_MANIFEST_RECORDED
        and ReferenceDecisionHandoffArtifact.model_validate(
            _artifact_value(event)
        ).manifest.acquisition_outcome_digest
        == outcome.outcome_digest
    )
    return tuple(
        sorted(
            (request_event, receipt_event, outcome_event, reassessment),
            key=lambda event: event.sequence,
        )
    )


def _empty_catalog_event(
    bundle: ReferenceRuntimeBundle,
) -> tuple[ReferenceEvent, int, ReferenceG3FallbackDisposition]:
    for event in bundle.event_log.events:
        if event.event_type != ReferenceEventType.DECISION_MANIFEST_RECORDED:
            continue
        handoff = ReferenceDecisionHandoffArtifact.model_validate(_artifact_value(event))
        if handoff.catalog.bundles:
            continue
        fallback = handoff.selection.fallback_disposition
        if handoff.selection.selected_bundle_id is not None or fallback is None:
            raise RuntimeError("Reference empty catalog did not produce an explicit fallback")
        if fallback.value != "hold":
            raise RuntimeError("Reference empty catalog did not fail closed")
        return event, 0, "hold"
    raise RuntimeError("Reference nominal run did not exercise an empty catalog")


def run_reference_g3_characterization(
    repository_root: Path,
    output_root: Path,
    *,
    seed: int,
) -> ReferenceG3CharacterizationIndex:
    """Execute and record all five non-LEAP constructed fixtures sequentially."""

    # Deferred to runtime to keep validation package initialization acyclic.
    from trace_reference.provenance.scientific_inputs import (
        build_reference_scientific_input_manifest,
    )

    output = safe_directory(
        output_root,
        declared_root=output_root,
        label="Reference G3 characterization output",
    )
    if any(output.iterdir()):
        raise ValueError("Reference G3 characterization output must be empty")
    nominal_root = output / "nominal_store"
    faulted_root = output / "faulted_store"
    restarted_root = output / "restarted_store"
    for root in (nominal_root, faulted_root, restarted_root):
        root.mkdir()

    scenario = generate_reference_scenario(repository_root, seed=seed)
    nominal_bundle = build_reference_runtime(scenario, nominal_root)
    nominal_bundle.runtime.run()
    schedule = load_reference_fault_schedule(repository_root, _FAULT_SCHEDULE)
    faulted_bundle = build_reference_runtime(scenario, faulted_root, fault_schedule=schedule)
    faulted_run = faulted_bundle.runtime.run()
    before_crash = build_reference_runtime(scenario, restarted_root, fault_schedule=schedule)
    before_crash.runtime.run(through_s=_CRASH_AT_S)
    checkpoint = before_crash.runtime.checkpoint(register_crash=True)
    restarted_bundle = build_reference_runtime(
        scenario,
        restarted_root,
        events=before_crash.event_log.events,
        fault_schedule=schedule,
        restart_checkpoint=checkpoint,
    )
    restarted_run = restarted_bundle.runtime.run()
    integrity = build_reference_g3_integrity_report(
        ReferenceG3IntegrityInput(
            scenario_seed=seed,
            scientific_input_aggregate_sha256=(
                build_reference_scientific_input_manifest(repository_root).aggregate_sha256
            ),
            faulted_scenario_input_digest=reference_scenario_input_digest(scenario),
            restart_checkpoint_scenario_input_digest=checkpoint.scenario_input_digest,
            schedule=schedule,
            faulted_run=faulted_run,
            faulted_bundle=faulted_bundle,
            restarted_run=restarted_run,
            restarted_bundle=restarted_bundle,
        )
    )
    if not integrity.all_checks_pass:
        raise RuntimeError("Reference G3 characterization failed runtime integrity")

    success_events = _events_for_success(nominal_bundle)
    timeout_events = _events_for_timeout(restarted_bundle)
    empty_event, empty_count, fallback = _empty_catalog_event(nominal_bundle)
    fixtures = (
        _fixture(
            _FixtureSpec(
                fixture_id="acquisition-success",
                seed=seed,
                runtime_profile_id="reference-nominal-v1",
                families=_runtime_families(nominal_bundle, events=success_events),
                acquisition_outcome_status="evidence-accepted",
                physical_evidence_count=1,
            )
        ),
        _fixture(
            _FixtureSpec(
                fixture_id="acquisition-timeout",
                seed=seed,
                runtime_profile_id="reference-faulted-v1",
                families=_runtime_families(restarted_bundle, events=timeout_events),
                acquisition_outcome_status="provider-timeout",
                physical_evidence_count=0,
            )
        ),
        _fixture(
            _FixtureSpec(
                fixture_id="empty-catalog-fallback",
                seed=seed,
                runtime_profile_id="reference-nominal-v1",
                families=_runtime_families(nominal_bundle, events=(empty_event,)),
                selected_catalog_bundle_count=empty_count,
                fallback_disposition=fallback,
            )
        ),
        _fixture(
            _FixtureSpec(
                fixture_id="faulted-restart",
                seed=seed,
                runtime_profile_id="reference-faulted-v1",
                families=_runtime_families(restarted_bundle),
                restart_public_state_equivalent=integrity.restart_public_state_equivalent,
                restart_durable_state_equivalent=integrity.restart_durable_state_equivalent,
            )
        ),
        _fixture(
            _FixtureSpec(
                fixture_id="nominal",
                seed=seed,
                runtime_profile_id="reference-nominal-v1",
                families=_runtime_families(nominal_bundle),
            )
        ),
    )
    body = {
        "schema_version": "delta-reference-g3-characterization-index-v1",
        "scientific_status": "development-characterization-not-validation-evidence",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "scenario_seed": seed,
        "fixtures": [item.model_dump(mode="json") for item in fixtures],
        "integrity_report_digest": integrity.report_digest,
        "leap_implementation_present": False,
        "effectiveness_evidence_present": False,
    }
    index = ReferenceG3CharacterizationIndex(
        **body,
        index_digest=decision_digest(body),
    )
    for fixture in fixtures:
        atomic_write_bytes(
            output / f"{fixture.fixture_id}_fixture_manifest.json",
            canonical_json_bytes(fixture.model_dump(mode="json")),
            root=output,
            label=f"Reference G3 {fixture.fixture_id} fixture",
        )
    atomic_write_bytes(
        output / "g3_characterization_index.json",
        canonical_json_bytes(index.model_dump(mode="json")),
        root=output,
        label="Reference G3 characterization index",
    )
    atomic_write_bytes(
        output / "g3_integrity_report.json",
        canonical_json_bytes(integrity.model_dump(mode="json")),
        root=output,
        label="Reference G3 integrity report",
    )
    return index
