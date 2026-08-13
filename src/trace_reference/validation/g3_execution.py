"""Stable development execution of the non-LEAP G3 fault/restart integrity gate."""

from __future__ import annotations

from pathlib import Path

from trace_jepa.support import atomic_write_bytes, canonical_json_bytes, safe_directory
from trace_reference import load_reference_fault_schedule
from trace_reference.generation import generate_reference_scenario
from trace_reference.runtime import build_reference_runtime
from trace_reference.runtime.mission_state import reference_scenario_input_digest

from .g3_integrity import ReferenceG3IntegrityInput, build_reference_g3_integrity_report
from .models import ReferenceG3IntegrityReport

_FAULT_SCHEDULE = Path("data/scenario/delta/reference_protocol/reference_fault_schedule_v1.json")
_REGISTERED_CRASH_AT_S = 187_200


def run_reference_g3_integrity(
    repository_root: Path,
    output_root: Path,
    *,
    seed: int,
) -> ReferenceG3IntegrityReport:
    """Run the exact development fault path and restarted equivalent sequentially."""

    # Imported after package initialization to avoid coupling the provenance
    # writer's capacity-model imports back into validation initialization.
    from trace_reference.provenance.scientific_inputs import (
        build_reference_scientific_input_manifest,
    )

    output = safe_directory(
        output_root,
        declared_root=output_root,
        label="Reference G3 output root",
    )
    if any(output.iterdir()):
        raise ValueError("Reference G3 output root must be empty")
    uninterrupted_root = output / "uninterrupted_store"
    restarted_root = output / "restarted_store"
    uninterrupted_root.mkdir()
    restarted_root.mkdir()

    scenario = generate_reference_scenario(repository_root, seed=seed)
    schedule = load_reference_fault_schedule(repository_root, _FAULT_SCHEDULE)
    faulted_bundle = build_reference_runtime(
        scenario,
        uninterrupted_root,
        fault_schedule=schedule,
    )
    faulted_run = faulted_bundle.runtime.run()

    before_crash = build_reference_runtime(
        scenario,
        restarted_root,
        fault_schedule=schedule,
    )
    before_crash.runtime.run(through_s=_REGISTERED_CRASH_AT_S)
    checkpoint = before_crash.runtime.checkpoint(register_crash=True)
    restarted_bundle = build_reference_runtime(
        scenario,
        restarted_root,
        events=before_crash.event_log.events,
        fault_schedule=schedule,
        restart_checkpoint=checkpoint,
    )
    restarted_run = restarted_bundle.runtime.run()
    report = build_reference_g3_integrity_report(
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
    atomic_write_bytes(
        output / "g3_integrity_report.json",
        canonical_json_bytes(report.model_dump(mode="json")),
        root=output,
        label="Reference G3 integrity report",
    )
    return report
