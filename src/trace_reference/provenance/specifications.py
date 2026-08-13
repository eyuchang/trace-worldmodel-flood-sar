"""Declarative Reference artifact inventory and aggregate result construction."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from trace_jepa.predictor.protocol import PredictorProvenance
from trace_jepa.support import canonical_json_bytes
from trace_reference.domain import ReferenceEventVisibility, ReferenceScenarioArtifacts
from trace_reference.runtime import ReferenceMissionRun, ReferenceRuntimeBundle
from trace_reference.validation.capacity_models import ReferenceCapacityEvaluation

from .models import ReferenceResultSummary
from .scientific_inputs import build_reference_scientific_input_manifest


@dataclass(frozen=True)
class ReferenceArtifactSpec:
    name: str
    file_name: str
    value: object
    contains_hidden_truth: bool = False
    content_encoding: Literal["canonical-json", "canonical-json-gzip-v1"] = "canonical-json"


@dataclass(frozen=True)
class ReferenceArtifactWriteRequest:
    repository_root: Path
    output_root: Path
    scenario: ReferenceScenarioArtifacts
    run: ReferenceMissionRun
    runtime_bundle: ReferenceRuntimeBundle
    capacity: ReferenceCapacityEvaluation
    predictor_provenance: PredictorProvenance


def _model_values(values: tuple[BaseModel, ...]) -> list[object]:
    return [item.model_dump(mode="json") for item in values]


def _result_summary(request: ReferenceArtifactWriteRequest) -> ReferenceResultSummary:
    scenario = request.scenario
    run = request.run
    capacity = request.capacity
    body = {
        "schema_version": "delta-reference-result-summary-v1",
        "scientific_status": "development-descriptive-not-validation-evidence",
        "seed": scenario.truth.seed,
        "report_count": len(scenario.observations.raw.reports),
        "evaluation_report_count": sum(
            item.observed_at_s >= 0 for item in scenario.observations.raw.reports
        ),
        "truth_incident_count": len(scenario.truth.incidents),
        "evaluation_truth_incident_count": sum(
            item.onset_s >= 0 for item in scenario.truth.incidents
        ),
        "decision_count": len(run.decisions),
        "allocation_count": sum(item.disposition == "allocated" for item in run.decisions),
        "refusal_count": sum(item.disposition == "refused" for item in run.decisions),
        "outcome_count": len(run.outcomes),
        "compensation_count": len(run.compensations),
        "consistency_debt_count": len(run.consistency_debts),
        "peak_finite_strict_concurrent_load_ratio_milli": (
            capacity.peak_finite_strict_concurrent_load_ratio_milli
        ),
        "strict_unserviceable_window_count": capacity.strict_unserviceable_window_count,
    }
    return ReferenceResultSummary(
        **body,
        result_digest=hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
    )


def build_reference_artifact_specs(
    request: ReferenceArtifactWriteRequest,
) -> tuple[ReferenceArtifactSpec, ...]:
    """Build the canonical public/hidden artifact inventory in name order."""

    scenario = request.scenario
    run = request.run
    bundle = request.runtime_bundle
    public_events = tuple(
        item
        for item in bundle.event_log.events
        if item.visibility == ReferenceEventVisibility.CONTROLLER_VISIBLE
    )
    specs = (
        ReferenceArtifactSpec(
            "capacity_evaluation",
            "capacity_evaluation.json",
            request.capacity.model_dump(mode="json"),
        ),
        ReferenceArtifactSpec(
            "commitment_chain", "commitment_chain.json", bundle.commitment_log.chain_entries()
        ),
        ReferenceArtifactSpec(
            "commitments", "commitments.json", _model_values(tuple(bundle.commitment_log.all()))
        ),
        ReferenceArtifactSpec(
            "configuration", "configuration.json", scenario.config.model_dump(mode="json")
        ),
        ReferenceArtifactSpec(
            "consistency_debts", "consistency_debts.json", _model_values(run.consistency_debts)
        ),
        ReferenceArtifactSpec(
            "contradictions", "contradictions.json", _model_values(run.contradictions)
        ),
        ReferenceArtifactSpec(
            "coordination_activations",
            "coordination_activations.json",
            scenario.coordination.activations.model_dump(mode="json"),
        ),
        ReferenceArtifactSpec(
            "coordination_audit",
            "coordination_audit.json",
            scenario.coordination.hidden.model_dump(mode="json"),
            True,
        ),
        ReferenceArtifactSpec(
            "coordination_public",
            "coordination_public.json",
            scenario.coordination.public.model_dump(mode="json"),
        ),
        ReferenceArtifactSpec("decisions", "decisions.json", _model_values(run.decisions)),
        ReferenceArtifactSpec(
            "delivery_envelopes",
            "delivery_envelopes.json",
            scenario.observations.delivery.model_dump(mode="json"),
        ),
        ReferenceArtifactSpec(
            "evidence_chain", "evidence_chain.json", bundle.evidence_ledger.chain_entries()
        ),
        ReferenceArtifactSpec(
            "evidence_ledger", "evidence_ledger.json", _model_values(bundle.evidence_ledger.all())
        ),
        ReferenceArtifactSpec(
            "exposure", "exposure.json", scenario.exposure.model_dump(mode="json"), True
        ),
        ReferenceArtifactSpec(
            "fault_applications",
            "fault_applications.json",
            _model_values(run.fault_applications),
            True,
        ),
        ReferenceArtifactSpec(
            "full_event_chain",
            "full_event_chain.json.gz",
            bundle.event_log.events,
            True,
            "canonical-json-gzip-v1",
        ),
        ReferenceArtifactSpec(
            "gauge_context", "gauge_context.json", scenario.gauge_context.model_dump(mode="json")
        ),
        ReferenceArtifactSpec(
            "geography", "geography.json", scenario.geography.model_dump(mode="json")
        ),
        ReferenceArtifactSpec(
            "governance", "governance.json", scenario.governance.model_dump(mode="json")
        ),
        ReferenceArtifactSpec(
            "hidden_lineage",
            "hidden_lineage.json",
            scenario.observations.hidden.model_dump(mode="json"),
            True,
        ),
        ReferenceArtifactSpec("outcomes", "outcomes.json", _model_values(run.outcomes)),
        ReferenceArtifactSpec(
            "physical_truth", "physical_truth.json", scenario.physical.model_dump(mode="json"), True
        ),
        ReferenceArtifactSpec(
            "predictor_prior", "predictor_prior.json", scenario.prior.model_dump(mode="json")
        ),
        ReferenceArtifactSpec(
            "public_event_projection",
            "public_event_projection.json.gz",
            public_events,
            False,
            "canonical-json-gzip-v1",
        ),
        ReferenceArtifactSpec(
            "raw_reports", "raw_reports.json", scenario.observations.raw.model_dump(mode="json")
        ),
        ReferenceArtifactSpec(
            "reconciliations", "reconciliations.json", _model_values(run.reconciliations)
        ),
        ReferenceArtifactSpec(
            "resource_audit",
            "resource_audit.json",
            scenario.resources.hidden_telemetry_audit.model_dump(mode="json"),
            True,
        ),
        ReferenceArtifactSpec(
            "resource_catalog",
            "resource_catalog.json",
            scenario.resources.public_catalog.model_dump(mode="json"),
        ),
        ReferenceArtifactSpec(
            "resource_telemetry",
            "resource_telemetry.json",
            scenario.resources.public.model_dump(mode="json"),
        ),
        ReferenceArtifactSpec(
            "resource_truth",
            "resource_truth.json",
            scenario.resources.hidden.model_dump(mode="json"),
            True,
        ),
        ReferenceArtifactSpec(
            "result_summary",
            "result_summary.json",
            _result_summary(request).model_dump(mode="json"),
        ),
        ReferenceArtifactSpec(
            "runtime_summary",
            "runtime_summary.json",
            {
                "schema_version": "delta-reference-runtime-summary-v1",
                "through_s": run.through_s,
                "complete": run.complete,
                "event_prefix_digest": run.event_prefix_digest,
                "trace_prefix_digest": run.trace_prefix_digest,
                "evidence_prefix_digest": run.evidence_prefix_digest,
                "commitment_prefix_digest": run.commitment_prefix_digest,
                "fault_profile_id": run.fault_profile_id,
                "unreachable_delivery_fault_ids": run.unreachable_delivery_fault_ids,
            },
        ),
        ReferenceArtifactSpec(
            "scientific_input_manifest",
            "scientific_input_manifest.json",
            build_reference_scientific_input_manifest(request.repository_root).model_dump(
                mode="json"
            ),
        ),
        ReferenceArtifactSpec(
            "trace_chain", "trace_chain.json", bundle.trace_repository.chain_entries()
        ),
        ReferenceArtifactSpec(
            "trace_records",
            "trace_records.json",
            _model_values(tuple(bundle.trace_repository.all())),
        ),
        ReferenceArtifactSpec("truth", "truth.json", scenario.truth.model_dump(mode="json"), True),
    )
    return tuple(sorted(specs, key=lambda item: item.name))
