"""Remote-only execution and aggregation for base Reference validation-v2."""

from __future__ import annotations

import hashlib
import json
import os
import socket
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from trace_jepa.support import (
    ArtifactLocator,
    atomic_write_bytes,
    canonical_json_bytes,
    safe_directory,
    sha256_file,
)
from trace_reference import load_reference_config, verify_small_baseline
from trace_reference.decision.canonical import decision_digest
from trace_reference.generation import generate_reference_scenario
from trace_reference.provenance import (
    execute_reference_scenario_with_inspection,
    verify_exact_reference_replay,
)
from trace_reference.publication import publish_reference_bundle
from trace_reference.runtime import build_reference_runtime

from .acceptance import (
    reference_capacity_accounting_valid,
    reference_commitment_conservation_valid,
    reference_outcome_censoring_valid,
    reference_public_bundle_hidden_free,
    reference_resource_crew_conservation_valid,
)
from .capacity import evaluate_reference_capacity
from .g3_execution import run_reference_g3_integrity
from .g3_integrity import (
    reference_authorization_joins_valid,
    reference_correction_joins_valid,
)
from .registration import (
    REFERENCE_VALIDATION_FREEZE,
    REFERENCE_VALIDATION_PROTOCOL,
    require_original_validation_boundary,
)
from .registration_models import (
    REFERENCE_VALIDATION_METRIC_NAMES,
    REFERENCE_VALIDATION_MISSION_GATE_IDS,
    ReferenceBaseValidationOriginalReport,
    ReferenceProtectedSeedPlan,
    ReferenceValidationBinding,
    ReferenceValidationDescriptiveInterval,
    ReferenceValidationGateResult,
    ReferenceValidationMissionReceipt,
    ReferenceValidationShardReceipt,
)
from .statistics import ReferenceSeedMetric, cluster_bootstrap_mean_interval

_CONFIG = Path("configs/scenarios/wf_dfld_01_reference_development.yaml")
_SMALL_REGISTRY = Path("data/scenario/delta/reference_protocol/small_baseline_v1.json")
_VALIDATION_NAMESPACE = "WF-DFLD-01-REFERENCE|validation-v2|index"
_MAX_RECEIPT_BYTES = 64 * 1024 * 1024


@contextmanager
def _network_disabled() -> Iterator[None]:
    def blocked_socket(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("Reference original scientific execution forbids network sockets")

    with patch.object(socket, "socket", blocked_socket):
        yield


def _protected_seed(index: int) -> int:
    payload = f"{_VALIDATION_NAMESPACE.removesuffix('|index')}|{index}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big") & 0x7FFFFFFF


def _seed_list() -> tuple[int, ...]:
    seeds = tuple(_protected_seed(index) for index in range(100))
    if len(set(seeds)) != len(seeds):
        raise RuntimeError("Reference validation-v2 seed derivation produced a collision")
    return seeds


def prepare_protected_seed_plan(
    repository_root: Path,
    output_path: Path,
    *,
    environment: Mapping[str, str] | None = None,
) -> ReferenceProtectedSeedPlan:
    """Derive the protected list only after all remote original guards verify."""

    if output_path.exists():
        raise ValueError("Reference protected seed plan output already exists")
    _, _, identity = require_original_validation_boundary(
        repository_root,
        os.environ if environment is None else environment,
    )
    seeds = _seed_list()
    digest_body = {
        "namespace": _VALIDATION_NAMESPACE,
        "derivation_algorithm": (
            "sha256-utf8-first-u32-big-endian-mask-unsigned31-reject-collision-v1"
        ),
        "seeds": seeds,
    }
    plan = ReferenceProtectedSeedPlan(
        schema_version="delta-reference-protected-seed-plan-v2",
        scenario_id="WF-DFLD-01-REFERENCE",
        execution=identity,
        namespace=_VALIDATION_NAMESPACE,
        derivation_algorithm=(
            "sha256-utf8-first-u32-big-endian-mask-unsigned31-reject-collision-v1"
        ),
        seeds=seeds,
        seed_list_sha256=hashlib.sha256(canonical_json_bytes(digest_body)).hexdigest(),
    )
    root = safe_directory(output_path.parent, declared_root=output_path.parent, label="seed plan root")
    atomic_write_bytes(
        output_path,
        canonical_json_bytes(plan.model_dump(mode="json")),
        root=root,
        label="Reference protected seed plan",
    )
    return plan


def _load_seed_plan(
    trusted_root: Path,
    relative_path: Path,
) -> ReferenceProtectedSeedPlan:
    path = ArtifactLocator(
        root=trusted_root,
        relative_name=relative_path,
        maximum_bytes=_MAX_RECEIPT_BYTES,
        label="Reference protected seed plan",
    ).resolve()
    return ReferenceProtectedSeedPlan.model_validate_json(path.read_text("utf-8"))


def _directory_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _gate(
    gate_id: str,
    passed: bool,
    evidence: object,
    adverse_finding: str | None = None,
) -> ReferenceValidationGateResult:
    return ReferenceValidationGateResult(
        gate_id=gate_id,
        passed=passed,
        evidence_sha256=hashlib.sha256(canonical_json_bytes(evidence)).hexdigest(),
        adverse_finding=None if passed else (adverse_finding or "registered gate failed"),
    )


def _hidden_lineage_independent(execution_root: Path, execution: object) -> bool:
    from trace_reference.provenance import ReferenceExecutionInspection

    if not isinstance(execution, ReferenceExecutionInspection):
        raise TypeError("Reference hidden-lineage check requires an inspected execution")
    removed = execution.scenario.observations.hidden.model_copy(
        update={"entries": (), "hidden_digest": "0" * 64}
    )
    scenario = replace(
        execution.scenario,
        observations=execution.scenario.observations.model_copy(update={"hidden": removed}),
    )
    without_root = execution_root / "without_lineage_store"
    without_root.mkdir()
    without = build_reference_runtime(scenario, without_root)
    run = without.runtime.run()
    original = execution.run
    return (
        run.decisions == original.decisions
        and run.outcomes == original.outcomes
        and run.reconciliations == original.reconciliations
        and without.trace_repository.chain_entries()
        == execution.runtime_bundle.trace_repository.chain_entries()
        and without.evidence_ledger.chain_entries()
        == execution.runtime_bundle.evidence_ledger.chain_entries()
        and without.commitment_log.chain_entries()
        == execution.runtime_bundle.commitment_log.chain_entries()
    )


def _scarcity_metrics(repository_root: Path, mission_root: Path, seed: int) -> tuple[int, int, bool]:
    config = load_reference_config(repository_root, _CONFIG)
    scarcity = config.model_copy(update={"axes": config.axes.model_copy(update={"kappa": 0.5})})
    canonical = generate_reference_scenario(repository_root, seed=seed, config=config)
    scenario = generate_reference_scenario(repository_root, seed=seed, config=scarcity)
    exogenous_equal = (
        canonical.geography == scenario.geography
        and canonical.physical == scenario.physical
        and canonical.exposure == scenario.exposure
        and canonical.truth == scenario.truth
        and canonical.observations == scenario.observations
        and canonical.prior == scenario.prior
    )
    scarcity_root = mission_root / "scarcity_store"
    scarcity_root.mkdir()
    runtime = build_reference_runtime(scenario, scarcity_root)
    run = runtime.runtime.run()
    capacity = evaluate_reference_capacity(scenario, run)
    return (
        capacity.peak_finite_strict_concurrent_load_ratio_milli,
        capacity.strict_unserviceable_window_count,
        exogenous_equal,
    )


def _mission_metrics(execution: object, scarcity: tuple[int, int, bool]) -> dict[str, int]:
    from trace_reference.provenance import ReferenceExecutionInspection

    if not isinstance(execution, ReferenceExecutionInspection):
        raise TypeError("Reference metric extraction requires an inspected execution")
    run = execution.run
    scenario = execution.scenario
    count_values = {
        "acquisition_request_count": sum(
            item.disposition == "acquisition-requested" for item in run.decisions
        ),
        "allocation_count": sum(item.disposition == "allocated" for item in run.decisions),
        "compensation_count": len(run.compensations),
        "consistency_debt_count": len(run.consistency_debts),
        "evaluation_report_count": sum(
            item.observed_at_s >= 0 for item in scenario.observations.raw.reports
        ),
        "evaluation_truth_incident_count": sum(
            item.onset_s >= 0 for item in scenario.truth.incidents
        ),
        "refusal_count": sum(item.disposition == "refused" for item in run.decisions),
        "scarcity_strict_unserviceable_window_count": scarcity[1],
        "strict_unserviceable_window_count": (
            execution.capacity.strict_unserviceable_window_count
        ),
    }
    ratio_values = {
        "scarcity_peak_finite_strict_load_ratio": scarcity[0],
        "strict_peak_finite_load_ratio": (
            execution.capacity.peak_finite_strict_concurrent_load_ratio_milli
        ),
    }
    values = {
        **{name: value * 1_000_000 for name, value in count_values.items()},
        **{name: value * 1_000 for name, value in ratio_values.items()},
    }
    return dict(sorted(values.items()))


def _run_mission(
    repository_root: Path,
    mission_root: Path,
    *,
    mission_index: int,
    seed: int,
) -> ReferenceValidationMissionReceipt:
    nominal = mission_root / "nominal"
    replay = mission_root / "replay"
    publication_first = mission_root / "publication_first"
    publication_second = mission_root / "publication_second"
    fault = mission_root / "fault"
    for path in (nominal, replay, publication_first, publication_second, fault):
        path.mkdir()
    with _network_disabled():
        execution = execute_reference_scenario_with_inspection(
            repository_root,
            nominal,
            seed=seed,
        )
        chain_valid = (
            execution.run.complete
            and execution.runtime_bundle.event_log.verify()
            and execution.runtime_bundle.trace_repository.verify_chain()
            and execution.runtime_bundle.evidence_ledger.verify_chain()
            and execution.runtime_bundle.commitment_log.verify_chain()
            and reference_authorization_joins_valid(execution.run, execution.runtime_bundle)
            and reference_correction_joins_valid(execution.run)
        )
        conservation_valid = (
            reference_resource_crew_conservation_valid(execution)
            and reference_commitment_conservation_valid(execution)
            and reference_outcome_censoring_valid(execution)
            and reference_capacity_accounting_valid(execution)
        )
        public_hidden_free = reference_public_bundle_hidden_free(nominal, execution.manifest)
        hidden_independent = _hidden_lineage_independent(mission_root, execution)
        verify_exact_reference_replay(
            repository_root,
            trusted_reference_root=mission_root,
            reference_relative_path=Path("nominal"),
            replay_output_root=replay,
        )
        first = publish_reference_bundle(
            trusted_reference_root=mission_root,
            reference_relative_path=Path("nominal"),
            output_root=publication_first,
        )
        second = publish_reference_bundle(
            trusted_reference_root=mission_root,
            reference_relative_path=Path("nominal"),
            output_root=publication_second,
        )
        publication_equal = first == second and (
            _directory_digest(publication_first) == _directory_digest(publication_second)
        )
        g3 = run_reference_g3_integrity(repository_root, fault, seed=seed)
        scarcity = _scarcity_metrics(repository_root, mission_root, seed)
    gates = tuple(
        sorted(
            (
                _gate(
                    "RV-CHAIN-INTEGRITY",
                    chain_valid,
                    {
                        "event": execution.run.event_prefix_digest,
                        "trace": execution.run.trace_prefix_digest,
                        "evidence": execution.run.evidence_prefix_digest,
                        "commitment": execution.run.commitment_prefix_digest,
                    },
                ),
                _gate(
                    "RV-CONSERVATION",
                    conservation_valid and scarcity[2],
                    {"capacity": execution.capacity.evaluation_digest, "scarcity_crn": scarcity[2]},
                ),
                _gate(
                    "RV-EXACT-REPLAY",
                    publication_equal,
                    {"manifest": execution.manifest.manifest_digest, "publication": first.manifest_digest},
                ),
                _gate(
                    "RV-FAULT-REACHABILITY",
                    g3.fault_coverage_complete and g3.fault_targets_all_reachable,
                    g3.report_digest,
                ),
                _gate(
                    "RV-HIDDEN-TRUTH",
                    public_hidden_free and hidden_independent and g3.public_artifacts_hidden_free,
                    {
                        "public_hidden_free": public_hidden_free,
                        "deletion_equivalent": hidden_independent,
                        "fault_hidden_free": g3.public_artifacts_hidden_free,
                    },
                ),
                _gate(
                    "RV-RECOVERY-EQUIVALENCE",
                    g3.exogenous_inputs_byte_equivalent
                    and g3.restart_public_state_equivalent
                    and g3.restart_durable_state_equivalent,
                    g3.report_digest,
                ),
            ),
            key=lambda item: item.gate_id,
        )
    )
    body = {
        "schema_version": "delta-reference-validation-mission-receipt-v2",
        "mission_index": mission_index,
        "mission_seed_sha256": hashlib.sha256(str(seed).encode("ascii")).hexdigest(),
        "scenario_input_digest": execution.manifest.scenario_input_digest,
        "nominal_manifest_digest": execution.manifest.manifest_digest,
        "fault_report_digest": g3.report_digest,
        "gates": [item.model_dump(mode="json") for item in gates],
        "metric_micros": _mission_metrics(execution, scarcity),
    }
    return ReferenceValidationMissionReceipt(
        **body,
        receipt_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )


def _failed_mission_receipt(
    mission_index: int,
    seed: int,
    finding: str,
) -> ReferenceValidationMissionReceipt:
    gates = tuple(
        _gate(gate_id, False, {"mission_index": mission_index}, finding[:500])
        for gate_id in REFERENCE_VALIDATION_MISSION_GATE_IDS
    )
    metrics = dict.fromkeys(REFERENCE_VALIDATION_METRIC_NAMES, 0)
    body = {
        "schema_version": "delta-reference-validation-mission-receipt-v2",
        "mission_index": mission_index,
        "mission_seed_sha256": hashlib.sha256(str(seed).encode("ascii")).hexdigest(),
        "scenario_input_digest": "0" * 64,
        "nominal_manifest_digest": "0" * 64,
        "fault_report_digest": "0" * 64,
        "gates": [item.model_dump(mode="json") for item in gates],
        "metric_micros": metrics,
    }
    return ReferenceValidationMissionReceipt(
        **body,
        receipt_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )


def run_reference_validation_shard(
    repository_root: Path,
    output_path: Path,
    *,
    shard_index: int,
    seed_plan_root: Path,
    seed_plan_relative_path: Path,
    environment: Mapping[str, str] | None = None,
) -> ReferenceValidationShardReceipt:
    """Execute one five-mission shard without retaining heavyweight bundles."""

    if output_path.exists():
        raise ValueError("Reference validation shard output already exists")
    protocol, freeze, identity = require_original_validation_boundary(
        repository_root,
        os.environ if environment is None else environment,
    )
    if not 0 <= shard_index < protocol.shard_count:
        raise ValueError("Reference validation shard index is outside the frozen plan")
    plan = _load_seed_plan(seed_plan_root, seed_plan_relative_path)
    if plan.execution != identity:
        raise ValueError("Reference protected seed plan belongs to another execution")
    output_root = safe_directory(
        output_path.parent,
        declared_root=output_path.parent,
        label="Reference validation shard output root",
    )
    work = output_root / f"mission-work-{shard_index:02d}"
    work.mkdir()
    missions = []
    try:
        for mission_index in range(shard_index * 5, shard_index * 5 + 5):
            mission_root = work / f"mission-{mission_index:03d}"
            mission_root.mkdir()
            try:
                mission_receipt = _run_mission(
                    repository_root,
                    mission_root,
                    mission_index=mission_index,
                    seed=plan.seeds[mission_index],
                )
            except Exception as exc:  # noqa: BLE001 - failures are registered evidence
                mission_receipt = _failed_mission_receipt(
                    mission_index,
                    plan.seeds[mission_index],
                    f"{type(exc).__name__}: {exc}",
                )
            missions.append(mission_receipt)
            for path in sorted(
                mission_root.rglob("*"),
                key=lambda item: len(item.parts),
                reverse=True,
            ):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            mission_root.rmdir()
    finally:
        if work.exists() and not any(work.iterdir()):
            work.rmdir()
    protocol_sha = sha256_file(repository_root / REFERENCE_VALIDATION_PROTOCOL)
    body = {
        "schema_version": "delta-reference-validation-shard-receipt-v2",
        "execution": identity.model_dump(mode="json"),
        "shard_index": shard_index,
        "protocol_sha256": protocol_sha,
        "freeze_digest": freeze.freeze_digest,
        "missions": [item.model_dump(mode="json") for item in missions],
    }
    shard_receipt = ReferenceValidationShardReceipt(
        **body,
        shard_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )
    atomic_write_bytes(
        output_path,
        canonical_json_bytes(shard_receipt.model_dump(mode="json")),
        root=output_root,
        label="Reference validation shard receipt",
    )
    return shard_receipt


def _missing_shard_receipt(
    shard_index: int,
    identity: object,
    protocol_sha256: str,
    freeze_digest: str,
) -> ReferenceValidationShardReceipt:
    from .registration_models import ReferenceOriginalExecutionIdentity

    if not isinstance(identity, ReferenceOriginalExecutionIdentity):
        raise TypeError("Reference missing-shard synthesis requires original execution identity")
    missions = tuple(
        _failed_mission_receipt(
            mission_index,
            0,
            "workflow shard produced no receipt",
        )
        for mission_index in range(shard_index * 5, shard_index * 5 + 5)
    )
    body = {
        "schema_version": "delta-reference-validation-shard-receipt-v2",
        "execution": identity.model_dump(mode="json"),
        "shard_index": shard_index,
        "protocol_sha256": protocol_sha256,
        "freeze_digest": freeze_digest,
        "missions": [item.model_dump(mode="json") for item in missions],
    }
    return ReferenceValidationShardReceipt(
        **body,
        shard_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )


def _load_shards(
    root: Path,
    *,
    identity: object,
    protocol_sha256: str,
    freeze_digest: str,
) -> tuple[ReferenceValidationShardReceipt, ...]:
    values = []
    for shard_index in range(20):
        try:
            path = ArtifactLocator(
                root=root,
                relative_name=Path(f"shard-{shard_index:02d}.json"),
                maximum_bytes=_MAX_RECEIPT_BYTES,
                label=f"Reference validation shard {shard_index}",
            ).resolve()
        except (OSError, ValueError):
            values.append(
                _missing_shard_receipt(
                    shard_index,
                    identity,
                    protocol_sha256,
                    freeze_digest,
                )
            )
            continue
        values.append(
            ReferenceValidationShardReceipt.model_validate_json(path.read_text("utf-8"))
        )
    return tuple(values)


def _aggregate_gate(
    gate_id: str,
    mission_receipts: tuple[ReferenceValidationMissionReceipt, ...],
    *,
    fixed_pass: bool | None = None,
    fixed_evidence: object | None = None,
) -> ReferenceValidationGateResult:
    matches = tuple(gate for item in mission_receipts for gate in item.gates if gate.gate_id == gate_id)
    passed = all(item.passed for item in matches) if fixed_pass is None else fixed_pass
    evidence = fixed_evidence if fixed_evidence is not None else tuple(item.evidence_sha256 for item in matches)
    return _gate(gate_id, passed, evidence, "one or more mission-level checks failed")


def _binding(root: Path, relative_path: Path) -> ReferenceValidationBinding:
    return ReferenceValidationBinding(
        repository_relative_path=relative_path.as_posix(),
        sha256=sha256_file(root / relative_path),
    )


def aggregate_reference_validation_report(
    repository_root: Path,
    output_path: Path,
    *,
    shard_root: Path,
    seed_plan_root: Path,
    seed_plan_relative_path: Path,
    environment: Mapping[str, str] | None = None,
) -> ReferenceBaseValidationOriginalReport:
    """Aggregate exactly 20 verified shards and preserve every adverse result."""

    if output_path.exists():
        raise ValueError("Reference original validation report output already exists")
    protocol, freeze, identity = require_original_validation_boundary(
        repository_root,
        os.environ if environment is None else environment,
    )
    plan = _load_seed_plan(seed_plan_root, seed_plan_relative_path)
    protocol_sha = sha256_file(repository_root / REFERENCE_VALIDATION_PROTOCOL)
    shards = _load_shards(
        shard_root,
        identity=identity,
        protocol_sha256=protocol_sha,
        freeze_digest=freeze.freeze_digest,
    )
    if any(item.execution != identity for item in shards) or plan.execution != identity:
        raise ValueError("Reference original evidence belongs to another workflow execution")
    if tuple(item.shard_index for item in shards) != tuple(range(20)):
        raise ValueError("Reference original validation shards are incomplete")
    missions = tuple(mission for shard in shards for mission in shard.missions)
    if tuple(item.mission_index for item in missions) != tuple(range(100)):
        raise ValueError("Reference original validation mission coverage is incomplete")
    shard_bindings_valid = all(
        item.protocol_sha256 == protocol_sha and item.freeze_digest == freeze.freeze_digest
        for item in shards
    )
    seed_hashes_valid = all(
        item.mission_seed_sha256 == hashlib.sha256(str(plan.seeds[index]).encode("ascii")).hexdigest()
        for index, item in enumerate(missions)
    )
    phase6 = json.loads((repository_root / freeze.phase6_development_acceptance.repository_relative_path).read_text("utf-8"))
    canonical = json.loads((repository_root / freeze.canonical_phase6_execution_receipt.repository_relative_path).read_text("utf-8"))
    verify_small_baseline(repository_root, _SMALL_REGISTRY)
    fixed = {
        "RV-AXIS-ISOLATION": any(
            item["check_id"] == "P6-AXIS-ISOLATION" and item["passed"]
            for item in phase6["checks"]
        ),
        "RV-CANONICAL-PERFORMANCE": (
            canonical["execution_role"] == "canonical-development-preflight"
            and canonical["environment_verification_matches"]
            and canonical["registered_resource_ceilings_observed_within_limits"]
            and canonical["exact_replay_byte_identical"]
            and canonical["publication_regeneration_byte_identical"]
        ),
        "RV-SMALL-PRESERVATION": True,
        "RV-SOURCE-SECURITY": (
            phase6["all_nonperformance_checks_pass"]
            and shard_bindings_valid
            and seed_hashes_valid
        ),
    }
    gates = tuple(
        _aggregate_gate(
            definition.gate_id,
            missions,
            fixed_pass=fixed.get(definition.gate_id),
            fixed_evidence=(freeze.freeze_digest if definition.gate_id in fixed else None),
        )
        for definition in protocol.exact_gates
    )
    metric_names = tuple(sorted(missions[0].metric_micros))
    if any(tuple(item.metric_micros) != metric_names for item in missions):
        raise ValueError("Reference mission receipts expose inconsistent metric sets")
    intervals = []
    for metric_name in metric_names:
        interval = cluster_bootstrap_mean_interval(
            tuple(
                ReferenceSeedMetric(seed=item.mission_index, value_micros=item.metric_micros[metric_name])
                for item in missions
            ),
            protocol_hash=protocol_sha,
            metric_name=metric_name,
        )
        intervals.append(
            ReferenceValidationDescriptiveInterval(
                metric_name=metric_name,
                point_micros=interval.point_micros,
                lower_micros=interval.lower_micros,
                upper_micros=interval.upper_micros,
                method="deterministic-cluster-bootstrap-percentile-v1",
                resample_count=10_000,
                randomness_sha256=interval.randomness_sha256 or "",
            )
        )
    adverse = tuple(
        f"mission-{mission.mission_index:03d}:{gate.gate_id}:{gate.adverse_finding}"
        for mission in missions
        for gate in mission.gates
        if not gate.passed
    )
    body = {
        "schema_version": "delta-reference-base-validation-original-report-v2",
        "execution_role": "original-base-reference-validation",
        "execution": identity.model_dump(mode="json"),
        "protocol": _binding(repository_root, REFERENCE_VALIDATION_PROTOCOL).model_dump(mode="json"),
        "freeze_record": _binding(repository_root, REFERENCE_VALIDATION_FREEZE).model_dump(mode="json"),
        "freeze_digest": freeze.freeze_digest,
        "scientific_input_aggregate_sha256": freeze.scientific_input_aggregate_sha256,
        "environment_contract_sha256": freeze.environment_contract.sha256,
        "dependency_lock_sha256": freeze.dependency_lock.sha256,
        "seed_list_sha256": plan.seed_list_sha256,
        "mission_count": 100,
        "shard_digests": [item.shard_digest for item in shards],
        "exact_gates": [item.model_dump(mode="json") for item in gates],
        "descriptive_intervals": [item.model_dump(mode="json") for item in intervals],
        "adverse_findings": adverse,
        "all_exact_gates_pass": all(item.passed for item in gates),
    }
    report = ReferenceBaseValidationOriginalReport(
        **body,
        report_digest=decision_digest(body),
    )
    output_root = safe_directory(
        output_path.parent,
        declared_root=output_path.parent,
        label="Reference original report root",
    )
    atomic_write_bytes(
        output_path,
        canonical_json_bytes(report.model_dump(mode="json")),
        root=output_root,
        label="Reference original base-validation report",
    )
    return report
