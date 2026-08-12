"""Composition root for the non-LEAP Reference mission runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trace_jepa.experimental import RevalidationGuard
from trace_jepa.predictor import ActionPrefixPredictor, ToyActionPrefixPredictor
from trace_jepa.runtime import PolicyConfig, PolicyEngine, TraceRuntime
from trace_jepa.support import safe_directory
from trace_reference.decision import EvidenceAcquisitionExecutor
from trace_reference.domain import (
    ReferenceEvent,
    ReferenceFaultSchedule,
    ReferenceMissionRestartCheckpoint,
    ReferenceScenarioArtifacts,
)

from .decision_engine import ReferenceDecisionEngine, ReferenceDecisionEngineDependencies
from .event_store import ReferenceEventLog
from .mission_runtime import ReferenceMissionRuntime
from .routing import ReferenceRouteService
from .scenario_index import ReferenceScenarioIndex
from .trace_gateway import ReferenceTraceGateway
from .trace_storage import (
    ReferenceCommitmentLog,
    ReferenceEvidenceLedger,
    ReferenceTraceRepository,
)

REFERENCE_POLICY_VERSION = "trace-reference-base-development-v1"
REFERENCE_ENVIRONMENT_VERSION = "trace-reference-python311-development-v1"


@dataclass(frozen=True)
class ReferenceRuntimeBundle:
    """Complete owned runtime surface and its durable stores."""

    runtime: ReferenceMissionRuntime
    event_log: ReferenceEventLog
    trace_repository: ReferenceTraceRepository
    evidence_ledger: ReferenceEvidenceLedger
    commitment_log: ReferenceCommitmentLog


def build_reference_runtime(
    scenario: ReferenceScenarioArtifacts,
    trusted_output_root: Path,
    *,
    predictor: ActionPrefixPredictor | None = None,
    events: tuple[ReferenceEvent, ...] = (),
    fault_schedule: ReferenceFaultSchedule | None = None,
    restart_checkpoint: ReferenceMissionRestartCheckpoint | None = None,
) -> ReferenceRuntimeBundle:
    """Compose the canonical development runtime without adding LEAP behavior."""

    root = safe_directory(
        trusted_output_root,
        declared_root=trusted_output_root,
        label="Reference runtime output root",
    )
    selected_predictor = predictor or ToyActionPrefixPredictor()
    provenance = selected_predictor.provenance()
    guard = RevalidationGuard.bootstrap(
        predictor_version=provenance.predictor_version,
        calibration_version=provenance.calibration_version,
        model_hash=provenance.model_hash,
        calibration_hash=provenance.calibration_hash,
        qualified_families=provenance.qualified_action_types,
    )
    policy = PolicyEngine(
        PolicyConfig(
            policy_version=REFERENCE_POLICY_VERSION,
            min_model_support=0.60,
            max_ood_score=0.35,
            max_uncertainty=0.30,
            max_rollout_horizon=8,
            max_observation_age_s=3_600,
            require_authority_for=provenance.supported_action_types,
            enable_revalidation_guard=True,
            high_consequence_actions=provenance.supported_action_types,
        ),
        revalidation=guard,
    )
    event_log = ReferenceEventLog(events)
    trace_repository = ReferenceTraceRepository(root)
    evidence_ledger = ReferenceEvidenceLedger(root)
    commitment_log = ReferenceCommitmentLog(root)
    core = TraceRuntime(
        repository=trace_repository,
        ledger=evidence_ledger,
        commitments=commitment_log,
        policy=policy,
    )
    index = ReferenceScenarioIndex.from_physical(
        scenario.geography,
        scenario.gauge_context,
        scenario.physical,
    )
    engine = ReferenceDecisionEngine(
        ReferenceDecisionEngineDependencies(
            scenario=scenario,
            index=index,
            route_service=ReferenceRouteService(index),
            predictor=selected_predictor,
            event_log=event_log,
            trace_gateway=ReferenceTraceGateway(core, event_log),
            evidence_ledger=evidence_ledger,
            trace_repository=trace_repository,
            commitment_log=commitment_log,
            acquisition_executor=EvidenceAcquisitionExecutor(),
            policy_version=policy.config.policy_version,
            environment_contract_version=REFERENCE_ENVIRONMENT_VERSION,
        )
    )
    runtime = ReferenceMissionRuntime(
        scenario,
        engine,
        fault_schedule=fault_schedule,
        restart_checkpoint=restart_checkpoint,
    )
    return ReferenceRuntimeBundle(
        runtime,
        event_log,
        trace_repository,
        evidence_ledger,
        commitment_log,
    )
