"""Bounded, staged Phase 6 development acceptance for base Reference."""

from __future__ import annotations

import gc
import gzip
import platform
import resource
import socket
import sys
import time
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from itertools import pairwise
from pathlib import Path
from typing import BinaryIO, TypeVar, cast
from unittest.mock import patch

from pydantic import BaseModel

from trace_jepa.predictor import ToyActionPrefixPredictor
from trace_jepa.support import (
    ArtifactLocator,
    atomic_write_bytes,
    canonical_json_bytes,
    safe_directory,
    sha256_file,
)
from trace_reference.decision.canonical import decision_digest
from trace_reference.generation import generate_reference_scenario
from trace_reference.provenance import (
    ReferenceExecutionInspection,
    ReferenceReplayManifest,
    execute_reference_scenario_with_inspection,
    verify_exact_reference_replay,
    verify_reference_artifacts,
)
from trace_reference.provenance.artifacts import ReferenceArtifactWriter
from trace_reference.provenance.scientific_inputs import (
    build_reference_scientific_input_manifest,
)
from trace_reference.provenance.specifications import (
    ReferenceArtifactWriteRequest,
    build_reference_artifact_specs,
)
from trace_reference.publication import publish_reference_bundle
from trace_reference.runtime import build_reference_runtime

from .acceptance_models import (
    REFERENCE_PHASE6_CHECK_IDS,
    ReferencePhase6AcceptanceReport,
    ReferencePhase6CheckId,
    ReferencePhase6CheckResult,
    ReferencePhase6CoreReceipt,
    ReferencePhase6FaultReceipt,
    ReferencePhase6FileBinding,
    ReferencePhase6IsolationReceipt,
    ReferencePhase6ResourceReceipt,
)
from .axis_invariants import build_reference_phase6_axis_results
from .capacity import evaluate_reference_capacity
from .g3_execution import run_reference_g3_integrity
from .g3_handoff_models import ReferenceG3HandoffManifest
from .g3_integrity import (
    reference_authorization_joins_valid,
    reference_correction_joins_valid,
)

_SEED = 20260812
_MAX_INPUT_BYTES = 256 * 1024 * 1024
_FORBIDDEN_PUBLIC_TOKENS = (
    b'"accepted_truth_incident_id"',
    b'"affected_truth_person_ids"',
    b'"candidate_digest"',
    b'"episode_key"',
    b'"hidden_lineage"',
    b'"truth_incident_id"',
    b'"truth_person_id"',
    b'"truth_person_ids"',
    b'"RI-',
    b'"RP-',
)
_SCAN_BYTES = 1024 * 1024
_PHASE6_PROTOCOL = Path("docs/delta/reference/REFERENCE_PHASE6_DEVELOPMENT_ACCEPTANCE_V1.md")
_ModelT = TypeVar("_ModelT", bound=BaseModel)


@dataclass(frozen=True)
class ReferencePhase6FinalizeInput:
    """Caller-rooted inputs required to finalize one development receipt."""

    repository_root: Path
    output_root: Path
    core_root: Path
    core_receipt_relative_path: Path
    isolation_root: Path
    isolation_receipt_relative_path: Path
    fault_root: Path
    fault_receipt_relative_path: Path
    g3_handoff_relative_path: Path


@contextmanager
def _network_disabled() -> Iterator[None]:
    """Fail closed if a Reference development surface attempts a socket."""

    def blocked_socket(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("Reference Phase 6 execution forbids network sockets")

    with patch.object(socket, "socket", blocked_socket):
        yield


def _output_root(output_root: Path, label: str) -> Path:
    output = safe_directory(output_root, declared_root=output_root, label=label)
    if any(output.iterdir()):
        raise ValueError(f"{label} must be empty")
    return output


def _load_model(
    root: Path,
    relative_path: Path,
    model_type: type[_ModelT],
    *,
    label: str,
) -> _ModelT:
    path = ArtifactLocator(
        root=root,
        relative_name=relative_path,
        maximum_bytes=_MAX_INPUT_BYTES,
        label=label,
    ).resolve()
    try:
        return model_type.model_validate_json(path.read_text("utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"{label} is invalid") from exc


def _repository_binding(
    repository_root: Path,
    relative_path: Path,
) -> ReferencePhase6FileBinding:
    path = ArtifactLocator(
        root=repository_root,
        relative_name=relative_path,
        maximum_bytes=_MAX_INPUT_BYTES,
        label=f"Reference Phase 6 input {relative_path}",
    ).resolve()
    return ReferencePhase6FileBinding(
        repository_relative_path=relative_path.as_posix(),
        byte_length=path.stat().st_size,
        sha256=sha256_file(path),
    )


def _directory_bytes(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Reference Phase 6 output contains a symlink")
        if path.is_file():
            total += path.stat().st_size
    return total


def _peak_resident_memory_bytes() -> int | None:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if value <= 0:
        return None
    return round(value if sys.platform == "darwin" else value * 1024)


def _resource_receipt(started: float, output_root: Path) -> ReferencePhase6ResourceReceipt:
    elapsed_ms = max(1, round((time.perf_counter() - started) * 1_000))
    peak_memory = _peak_resident_memory_bytes()
    output_bytes = _directory_bytes(output_root)
    body: dict[str, object] = {
        "schema_version": "delta-reference-phase6-resource-receipt-v1",
        "measurement_role": "local-preflight",
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "elapsed_milliseconds": elapsed_ms,
        "peak_resident_memory_bytes": peak_memory,
        "transient_output_bytes": output_bytes,
        "wall_time_limit_s": 900,
        "peak_memory_limit_bytes": 2_147_483_648,
        "transient_output_limit_bytes": 1_073_741_824,
        "wall_time_within_limit": elapsed_ms <= 900_000,
        "peak_memory_within_limit": (None if peak_memory is None else peak_memory <= 2_147_483_648),
        "transient_output_within_limit": output_bytes <= 1_073_741_824,
        "canonical_gate_status": "pending-canonical-environment",
    }
    return ReferencePhase6ResourceReceipt(
        **body,
        receipt_digest=decision_digest(body),
    )


def _files_equal(first: Path, second: Path) -> bool:
    if first.stat().st_size != second.stat().st_size:
        return False
    with first.open("rb") as left, second.open("rb") as right:
        while True:
            first_chunk = left.read(_SCAN_BYTES)
            second_chunk = right.read(_SCAN_BYTES)
            if first_chunk != second_chunk:
                return False
            if not first_chunk:
                return True


def _publication_equal(first: Path, second: Path) -> bool:
    first_files = tuple(sorted(path.name for path in first.iterdir()))
    second_files = tuple(sorted(path.name for path in second.iterdir()))
    return first_files == second_files and all(
        _files_equal(first / name, second / name) for name in first_files
    )


def _open_binary(path: Path) -> BinaryIO:
    if path.suffix == ".gz":
        return cast(BinaryIO, gzip.open(path, "rb"))
    return path.open("rb")


def _file_excludes_hidden_tokens(path: Path) -> bool:
    maximum_tail = max(len(item) for item in _FORBIDDEN_PUBLIC_TOKENS) - 1
    with _open_binary(path) as stream:
        tail = b""
        while chunk := stream.read(_SCAN_BYTES):
            searchable = tail + chunk
            if any(token in searchable for token in _FORBIDDEN_PUBLIC_TOKENS):
                return False
            tail = searchable[-maximum_tail:]
    return True


def _public_bundle_hidden_free(bundle_root: Path, manifest: ReferenceReplayManifest) -> bool:
    registered_public_hidden_free = all(
        descriptor.contains_hidden_truth
        or _file_excludes_hidden_tokens(bundle_root / descriptor.file_name)
        for descriptor in manifest.artifacts
    )
    runtime_store = bundle_root / "runtime_store"
    runtime_files = tuple(path for path in runtime_store.rglob("*") if path.is_file())
    runtime_hidden_free = all(
        not path.is_symlink() and _file_excludes_hidden_tokens(path) for path in runtime_files
    )
    return registered_public_hidden_free and runtime_hidden_free


def _resource_crew_conservation(execution: ReferenceExecutionInspection) -> bool:
    resources = execution.scenario.resources.hidden.resources
    crews = execution.scenario.resources.hidden.crews
    resource_by_crew = {item.crew_id: item for item in resources}
    return (
        len({item.resource_id for item in resources}) == len(resources)
        and len({item.crew_id for item in crews}) == len(crews)
        and set(resource_by_crew) == {item.crew_id for item in crews}
        and all(
            resource_by_crew[item.crew_id].resource_id == item.resource_id
            and resource_by_crew[item.crew_id].resource_class == item.qualification
            for item in crews
        )
    )


def _commitment_conservation(execution: ReferenceExecutionInspection) -> bool:
    run = execution.run
    commitments = {
        item.commitment_id: item for item in execution.runtime_bundle.commitment_log.all()
    }
    allocations = tuple(item for item in run.decisions if item.disposition == "allocated")
    outcomes = {item.commitment_id: item for item in run.outcomes}
    allocation_ids = tuple(item.commitment_id for item in allocations)
    if (
        None in allocation_ids
        or len(set(allocation_ids)) != len(allocation_ids)
        or set(allocation_ids) != set(commitments)
        or set(outcomes) != set(commitments)
    ):
        return False
    intervals: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    for decision in allocations:
        if decision.commitment_id is None or decision.selected_resource_id is None:
            return False
        outcome = outcomes[decision.commitment_id]
        intervals[decision.selected_resource_id].append(
            (decision.decided_at_s, outcome.scheduled_completion_s, decision.commitment_id)
        )
    for resource_intervals in intervals.values():
        ordered = sorted(resource_intervals)
        if any(right[0] < left[1] for left, right in pairwise(ordered)):
            return False
    return True


def _outcome_censoring_valid(execution: ReferenceExecutionInspection) -> bool:
    return all(
        (
            outcome.status == "active_at_scenario_censoring"
            and outcome.scheduled_completion_s > outcome.censoring_s
            and outcome.observed_at_s == outcome.censoring_s
            and outcome.observed_completion_s is None
            and outcome.realized_service_fraction_micros is None
        )
        or (
            outcome.status == "completed_within_window"
            and outcome.scheduled_completion_s <= outcome.censoring_s
            and outcome.observed_at_s == outcome.scheduled_completion_s
            and outcome.observed_completion_s == outcome.scheduled_completion_s
            and outcome.realized_service_fraction_micros == 1_000_000
        )
        or (
            outcome.status == "partial_service_within_window"
            and outcome.scheduled_completion_s <= outcome.censoring_s
            and outcome.observed_at_s == outcome.scheduled_completion_s
            and outcome.observed_completion_s is None
            and outcome.realized_service_fraction_micros is not None
            and 0 < outcome.realized_service_fraction_micros < 1_000_000
        )
        for outcome in execution.run.outcomes
    )


def _capacity_accounting_valid(execution: ReferenceExecutionInspection) -> bool:
    return all(
        window.commitment_covered_demand_units + window.residual_demand_units
        == window.active_demand_units
        and window.strict_unserviceable
        == (window.active_demand_units > 0 and window.strict_matched_capacity_units == 0)
        and window.residual_strict_unserviceable
        == (window.residual_demand_units > 0 and window.free_strict_compatible_capacity_units == 0)
        for window in execution.capacity.windows
    )


def run_reference_phase6_core(
    repository_root: Path,
    output_root: Path,
) -> ReferencePhase6CoreReceipt:
    """Run nominal generation/execution, clean replay, and publication sequentially."""

    output = _output_root(output_root, "Reference Phase 6 core output root")
    nominal = output / "nominal"
    replay = output / "replay"
    publication_first = output / "publication_first"
    publication_second = output / "publication_second"
    for path in (nominal, replay, publication_first, publication_second):
        path.mkdir()
    started = time.perf_counter()
    scientific = build_reference_scientific_input_manifest(repository_root)
    with _network_disabled():
        execution = execute_reference_scenario_with_inspection(
            repository_root,
            nominal,
            seed=_SEED,
        )
        manifest = execution.manifest
        nominal_checks = {
            "nominal_runtime_complete": execution.run.complete,
            "event_chain_valid": execution.runtime_bundle.event_log.verify(),
            "trace_chain_valid": execution.runtime_bundle.trace_repository.verify_chain(),
            "evidence_chain_valid": execution.runtime_bundle.evidence_ledger.verify_chain(),
            "commitment_chain_valid": execution.runtime_bundle.commitment_log.verify_chain(),
            "authorization_joins_valid": reference_authorization_joins_valid(
                execution.run,
                execution.runtime_bundle,
            ),
            "correction_joins_valid": reference_correction_joins_valid(execution.run),
            "resource_crew_conservation_valid": _resource_crew_conservation(execution),
            "commitment_conservation_valid": _commitment_conservation(execution),
            "outcome_censoring_valid": _outcome_censoring_valid(execution),
            "capacity_accounting_valid": _capacity_accounting_valid(execution),
            "public_bundle_hidden_free": _public_bundle_hidden_free(nominal, manifest),
        }
        del execution
        gc.collect()
        verify_exact_reference_replay(
            repository_root,
            trusted_reference_root=output,
            reference_relative_path=Path("nominal"),
            replay_output_root=replay,
        )
        first_publication = publish_reference_bundle(
            trusted_reference_root=output,
            reference_relative_path=Path("nominal"),
            output_root=publication_first,
        )
        second_publication = publish_reference_bundle(
            trusted_reference_root=output,
            reference_relative_path=Path("nominal"),
            output_root=publication_second,
        )
    if build_reference_scientific_input_manifest(repository_root) != scientific:
        raise RuntimeError("Reference scientific inputs changed during Phase 6 core execution")
    resource_receipt = _resource_receipt(started, output)
    body: dict[str, object] = {
        "schema_version": "delta-reference-phase6-core-receipt-v1",
        "scientific_status": "development-integration-check-not-validation-evidence",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "seed": _SEED,
        "scientific_input_aggregate_sha256": scientific.aggregate_sha256,
        "nominal_replay_manifest_digest": manifest.manifest_digest,
        "nominal_scenario_input_digest": manifest.scenario_input_digest,
        "publication_manifest_digest": first_publication.manifest_digest,
        "exact_replay_byte_identical": True,
        "publication_regeneration_byte_identical": (
            first_publication == second_publication
            and _publication_equal(publication_first, publication_second)
        ),
        **nominal_checks,
        "offline_execution_guarded": True,
        "resource_receipt": resource_receipt.model_dump(mode="json"),
        "all_checks_pass": all(nominal_checks.values())
        and first_publication == second_publication
        and _publication_equal(publication_first, publication_second),
    }
    receipt = ReferencePhase6CoreReceipt(
        **body,
        receipt_digest=decision_digest(body),
    )
    atomic_write_bytes(
        output / "phase6_core_receipt.json",
        canonical_json_bytes(receipt.model_dump(mode="json")),
        root=output,
        label="Reference Phase 6 core receipt",
    )
    return receipt


def _load_nominal_manifest(
    trusted_nominal_root: Path,
    nominal_relative_path: Path,
) -> ReferenceReplayManifest:
    return verify_reference_artifacts(
        trusted_root=trusted_nominal_root,
        bundle_relative_path=nominal_relative_path,
    )


def _artifact_path(
    trusted_root: Path,
    bundle_relative_path: Path,
    manifest: ReferenceReplayManifest,
    name: str,
) -> Path:
    descriptor = next(item for item in manifest.artifacts if item.name == name)
    return ArtifactLocator(
        root=trusted_root / bundle_relative_path,
        relative_name=Path(descriptor.file_name),
        maximum_bytes=_MAX_INPUT_BYTES,
        label=f"Reference Phase 6 nominal artifact {name}",
    ).resolve()


def run_reference_phase6_isolation(
    repository_root: Path,
    output_root: Path,
    *,
    trusted_nominal_root: Path,
    nominal_relative_path: Path,
) -> ReferencePhase6IsolationReceipt:
    """Run full hidden-lineage deletion and eight-axis probes on the spent seed."""

    output = _output_root(output_root, "Reference Phase 6 isolation output root")
    runtime_root = output / "without_lineage_store"
    public_artifacts = output / "without_lineage_public"
    runtime_root.mkdir()
    public_artifacts.mkdir()
    nominal_manifest = _load_nominal_manifest(trusted_nominal_root, nominal_relative_path)
    scientific = build_reference_scientific_input_manifest(repository_root)
    with _network_disabled():
        scenario = generate_reference_scenario(repository_root, seed=_SEED)
        removed_hidden = scenario.observations.hidden.model_copy(
            update={"entries": (), "hidden_digest": "0" * 64}
        )
        without_lineage = replace(
            scenario,
            observations=scenario.observations.model_copy(update={"hidden": removed_hidden}),
        )
        bundle = build_reference_runtime(without_lineage, runtime_root)
        run = bundle.runtime.run()
        capacity = evaluate_reference_capacity(without_lineage, run)
        request = ReferenceArtifactWriteRequest(
            repository_root=repository_root,
            output_root=public_artifacts,
            scenario=without_lineage,
            run=run,
            runtime_bundle=bundle,
            capacity=capacity,
            predictor_provenance=ToyActionPrefixPredictor().provenance(),
        )
        writer = ReferenceArtifactWriter(public_artifacts)
        written = {
            spec.name: writer.write(spec)
            for spec in build_reference_artifact_specs(request)
            if not spec.contains_hidden_truth
        }
        axes = build_reference_phase6_axis_results(repository_root, scenario)
    if build_reference_scientific_input_manifest(repository_root) != scientific:
        raise RuntimeError("Reference scientific inputs changed during Phase 6 isolation")

    comparisons = {}
    for name in (
        "decisions",
        "outcomes",
        "reconciliations",
        "public_event_projection",
        "trace_chain",
        "evidence_chain",
        "commitment_chain",
    ):
        nominal_path = _artifact_path(
            trusted_nominal_root,
            nominal_relative_path,
            nominal_manifest,
            name,
        )
        comparisons[name] = _files_equal(
            nominal_path,
            public_artifacts / written[name].file_name,
        )
    body: dict[str, object] = {
        "schema_version": "delta-reference-phase6-isolation-receipt-v1",
        "scientific_status": "development-integration-check-not-validation-evidence",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "seed": _SEED,
        "scientific_input_aggregate_sha256": scientific.aggregate_sha256,
        "nominal_replay_manifest_digest": nominal_manifest.manifest_digest,
        "hidden_lineage_removed": True,
        "public_decisions_byte_equivalent": comparisons["decisions"],
        "public_outcomes_byte_equivalent": comparisons["outcomes"],
        "public_reconciliations_byte_equivalent": comparisons["reconciliations"],
        "public_event_projection_byte_equivalent": comparisons["public_event_projection"],
        "trace_chain_byte_equivalent": comparisons["trace_chain"],
        "evidence_chain_byte_equivalent": comparisons["evidence_chain"],
        "commitment_chain_byte_equivalent": comparisons["commitment_chain"],
        "axis_results": [item.model_dump(mode="json") for item in axes],
        "all_checks_pass": all(comparisons.values()) and all(item.passed for item in axes),
    }
    receipt = ReferencePhase6IsolationReceipt(
        **body,
        receipt_digest=decision_digest(body),
    )
    atomic_write_bytes(
        output / "phase6_isolation_receipt.json",
        canonical_json_bytes(receipt.model_dump(mode="json")),
        root=output,
        label="Reference Phase 6 isolation receipt",
    )
    return receipt


def run_reference_phase6_fault(
    repository_root: Path,
    output_root: Path,
) -> ReferencePhase6FaultReceipt:
    """Run the registered fault/restart path offline on the spent seed."""

    output = _output_root(output_root, "Reference Phase 6 fault output root")
    execution_root = output / "fault_execution"
    execution_root.mkdir()
    with _network_disabled():
        report = run_reference_g3_integrity(
            repository_root,
            execution_root,
            seed=_SEED,
        )
    current = build_reference_scientific_input_manifest(repository_root)
    if report.scientific_input_aggregate_sha256 != current.aggregate_sha256:
        raise RuntimeError("Reference scientific inputs changed during Phase 6 fault execution")
    body: dict[str, object] = {
        "schema_version": "delta-reference-phase6-fault-receipt-v1",
        "scientific_status": "development-integration-check-not-validation-evidence",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "seed": _SEED,
        "offline_execution_guarded": True,
        "integrity_report": report.model_dump(mode="json"),
        "all_checks_pass": report.all_checks_pass,
    }
    receipt = ReferencePhase6FaultReceipt(
        **body,
        receipt_digest=decision_digest(body),
    )
    atomic_write_bytes(
        output / "phase6_fault_receipt.json",
        canonical_json_bytes(receipt.model_dump(mode="json")),
        root=output,
        label="Reference Phase 6 fault receipt",
    )
    return receipt


def _check(
    check_id: ReferencePhase6CheckId,
    passed: bool,
    evidence_digests: tuple[str, ...],
    note: str,
) -> ReferencePhase6CheckResult:
    return ReferencePhase6CheckResult(
        check_id=check_id,
        passed=passed,
        evidence_digests=tuple(sorted(set(evidence_digests))),
        note=note,
    )


def finalize_reference_phase6_acceptance(
    values: ReferencePhase6FinalizeInput,
) -> ReferencePhase6AcceptanceReport:
    """Bind the three staged runs only after all source identities still agree."""

    output = _output_root(values.output_root, "Reference Phase 6 final output root")
    core = _load_model(
        values.core_root,
        values.core_receipt_relative_path,
        ReferencePhase6CoreReceipt,
        label="Reference Phase 6 core receipt",
    )
    isolation = _load_model(
        values.isolation_root,
        values.isolation_receipt_relative_path,
        ReferencePhase6IsolationReceipt,
        label="Reference Phase 6 isolation receipt",
    )
    fault_receipt = _load_model(
        values.fault_root,
        values.fault_receipt_relative_path,
        ReferencePhase6FaultReceipt,
        label="Reference Phase 6 offline fault receipt",
    )
    fault = fault_receipt.integrity_report
    handoff = _load_model(
        values.repository_root,
        values.g3_handoff_relative_path,
        ReferenceG3HandoffManifest,
        label="Reference corrected G3 handoff manifest",
    )
    scientific = build_reference_scientific_input_manifest(values.repository_root)
    if handoff.scientific_input_aggregate_sha256 != scientific.aggregate_sha256:
        raise ValueError("Reference G3 handoff does not bind the current Phase 6 source inventory")
    if handoff.leap_implementation_present or handoff.effectiveness_evidence_present:
        raise ValueError("Reference Phase 6 base acceptance cannot bind LEAP behavior")
    if isolation.nominal_replay_manifest_digest != core.nominal_replay_manifest_digest:
        raise ValueError("Reference Phase 6 staged receipts name different nominal executions")
    if not (
        core.scientific_input_aggregate_sha256
        == isolation.scientific_input_aggregate_sha256
        == fault.scientific_input_aggregate_sha256
        == scientific.aggregate_sha256
    ):
        raise ValueError("Reference Phase 6 staged receipts bind different scientific inputs")
    if core.nominal_scenario_input_digest != fault.scenario_input_digest:
        raise ValueError("Reference nominal and fault runs bind different exogenous scenarios")
    if fault.scenario_seed != _SEED:
        raise ValueError("Reference Phase 6 fault receipt uses another development seed")
    protocol = _repository_binding(values.repository_root, _PHASE6_PROTOCOL)
    checks = (
        _check(
            "P6-SOURCE-BOUND",
            True,
            (scientific.aggregate_sha256, handoff.manifest_digest, protocol.sha256),
            "Complete scientific inputs, the corrected G3 handoff, and this protocol are bound.",
        ),
        _check(
            "P6-SPENT-SEED",
            core.seed == isolation.seed == fault.scenario_seed == _SEED,
            (core.receipt_digest, isolation.receipt_digest),
            "Every staged run uses the already-spent illustrative development seed.",
        ),
        _check(
            "P6-DETERMINISM",
            core.exact_replay_byte_identical,
            (core.nominal_replay_manifest_digest,),
            "Clean regeneration reproduces the nominal generation and runtime bytes.",
        ),
        _check(
            "P6-NOMINAL-RUNTIME",
            core.nominal_runtime_complete,
            (core.receipt_digest,),
            "The complete nominal 96-hour event machine reaches scenario censoring.",
        ),
        _check(
            "P6-FAULT-COVERAGE",
            fault.fault_coverage_complete and fault.fault_targets_all_reachable,
            (fault.report_digest,),
            "The registered semantic fault schedule covers every required fault family.",
        ),
        _check(
            "P6-RESTART-EQUIVALENCE",
            fault.exogenous_inputs_byte_equivalent
            and fault.restart_public_state_equivalent
            and fault.restart_durable_state_equivalent,
            (fault.report_digest,),
            "Restarted execution matches uninterrupted public and durable continuation.",
        ),
        _check(
            "P6-CHAIN-INTEGRITY",
            core.event_chain_valid
            and core.trace_chain_valid
            and core.evidence_chain_valid
            and core.commitment_chain_valid
            and core.authorization_joins_valid
            and core.correction_joins_valid
            and fault.event_chains_valid
            and fault.trace_chains_valid
            and fault.evidence_chains_valid
            and fault.commitment_chains_valid
            and fault.authorization_joins_valid
            and fault.correction_joins_valid,
            (core.receipt_digest, fault.report_digest),
            "Nominal and faulted event, TRACE, evidence, commitment, and correction joins verify.",
        ),
        _check(
            "P6-HIDDEN-SEPARATION",
            core.public_bundle_hidden_free
            and isolation.public_decisions_byte_equivalent
            and isolation.public_outcomes_byte_equivalent
            and isolation.public_reconciliations_byte_equivalent
            and isolation.public_event_projection_byte_equivalent
            and isolation.trace_chain_byte_equivalent
            and isolation.evidence_chain_byte_equivalent
            and isolation.commitment_chain_byte_equivalent
            and fault.public_artifacts_hidden_free,
            (core.receipt_digest, fault.report_digest, isolation.receipt_digest),
            "Public runtime bytes are hidden-free and unchanged after hidden-lineage deletion.",
        ),
        _check(
            "P6-AXIS-ISOLATION",
            all(item.passed for item in isolation.axis_results),
            tuple(item.evidence_digest for item in isolation.axis_results),
            "All eight approved causal-axis mechanisms pass keyed isolation probes.",
        ),
        _check(
            "P6-CONSERVATION",
            core.resource_crew_conservation_valid
            and core.commitment_conservation_valid
            and core.outcome_censoring_valid,
            (core.receipt_digest,),
            "Resource, crew, commitment, service-interval, and censoring invariants hold.",
        ),
        _check(
            "P6-CAPACITY-ACCOUNTING",
            core.capacity_accounting_valid,
            (core.nominal_replay_manifest_digest,),
            "Typed strict and sensitivity capacity accounting preserves unserviceable states.",
        ),
        _check(
            "P6-EXACT-REPLAY",
            core.exact_replay_byte_identical,
            (core.nominal_replay_manifest_digest,),
            "Every registered nominal artifact and manifest byte reproduces exactly.",
        ),
        _check(
            "P6-PUBLICATION-REGENERATION",
            core.publication_regeneration_byte_identical,
            (core.publication_manifest_digest,),
            "The development result table and deterministic figures reproduce exactly.",
        ),
        _check(
            "P6-OFFLINE-EXECUTION",
            core.offline_execution_guarded and fault_receipt.offline_execution_guarded,
            (core.receipt_digest, fault_receipt.receipt_digest),
            "Nominal, fault, replay, and publication stages completed with sockets disabled.",
        ),
    )
    if tuple(item.check_id for item in checks) != REFERENCE_PHASE6_CHECK_IDS:
        raise RuntimeError("Reference Phase 6 final checks are incomplete")
    body: dict[str, object] = {
        "schema_version": "delta-reference-phase6-development-acceptance-v1",
        "scientific_status": "development-integration-acceptance-not-validation-evidence",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "seed": _SEED,
        "seed_status": "spent-development-illustrative",
        "protocol": protocol.model_dump(mode="json"),
        "scientific_input_manifest_digest": scientific.aggregate_sha256,
        "g3_handoff_manifest_digest": handoff.manifest_digest,
        "nominal_replay_manifest_digest": core.nominal_replay_manifest_digest,
        "fault_integrity_report_digest": fault.report_digest,
        "publication_manifest_digest": core.publication_manifest_digest,
        "checks": [item.model_dump(mode="json") for item in checks],
        "axis_results": [item.model_dump(mode="json") for item in isolation.axis_results],
        "resource_receipt": core.resource_receipt.model_dump(mode="json"),
        "all_nonperformance_checks_pass": all(item.passed for item in checks),
        "canonical_performance_status": core.resource_receipt.canonical_gate_status,
        "selection_validation_or_confirmatory_authority": False,
        "leap_behavior_present": False,
    }
    report = ReferencePhase6AcceptanceReport(
        **body,
        report_digest=decision_digest(body),
    )
    atomic_write_bytes(
        output / "phase6_development_acceptance_report.json",
        canonical_json_bytes(report.model_dump(mode="json")),
        root=output,
        label="Reference Phase 6 acceptance report",
    )
    return report
