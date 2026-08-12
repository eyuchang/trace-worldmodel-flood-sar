"""Pure verification of a registered fault/restart Reference execution."""

from __future__ import annotations

import json
from dataclasses import dataclass

from trace_reference.decision.canonical import decision_digest
from trace_reference.domain import (
    ReferenceEventVisibility,
    ReferenceFaultSchedule,
)
from trace_reference.runtime import ReferenceRuntimeBundle
from trace_reference.runtime.mission_state import ReferenceMissionRun

from .models import ReferenceG3IntegrityReport, ReferenceRuntimeCounts

_HIDDEN_FIELD_NAMES = frozenset(
    {
        "accepted_truth_incident_id",
        "affected_truth_person_ids",
        "candidate_digest",
        "episode_key",
        "hidden_lineage",
        "truth_incident_id",
        "truth_person_id",
        "truth_person_ids",
    }
)


@dataclass(frozen=True)
class ReferenceG3IntegrityInput:
    """Runtime objects needed to verify one development fault/restart fixture."""

    scenario_seed: int
    faulted_scenario_input_digest: str
    restart_checkpoint_scenario_input_digest: str
    schedule: ReferenceFaultSchedule
    faulted_run: ReferenceMissionRun
    faulted_bundle: ReferenceRuntimeBundle
    restarted_run: ReferenceMissionRun
    restarted_bundle: ReferenceRuntimeBundle


def _counts(run: ReferenceMissionRun) -> ReferenceRuntimeCounts:
    return ReferenceRuntimeCounts(
        decisions=len(run.decisions),
        allocations=sum(item.disposition == "allocated" for item in run.decisions),
        refusals=sum(item.disposition == "refused" for item in run.decisions),
        acquisition_requests=sum(
            item.disposition == "acquisition-requested" for item in run.decisions
        ),
        outcomes=len(run.outcomes),
        reconciliations=len(run.reconciliations),
        compensations=len(run.compensations),
        consistency_debts=len(run.consistency_debts),
    )


def _authorization_joins_valid(
    run: ReferenceMissionRun,
    bundle: ReferenceRuntimeBundle,
) -> bool:
    commitments = {item.commitment_id: item for item in bundle.commitment_log.all()}
    allocation_ids = tuple(
        item.commitment_id for item in run.decisions if item.disposition == "allocated"
    )
    outcome_ids = tuple(item.commitment_id for item in run.outcomes)
    if (
        None in allocation_ids
        or len(set(allocation_ids)) != len(allocation_ids)
        or set(allocation_ids) != set(commitments)
        or len(set(outcome_ids)) != len(outcome_ids)
        or set(outcome_ids) != set(commitments)
    ):
        return False
    for decision in run.decisions:
        if decision.disposition != "allocated":
            continue
        commitment = commitments.get(decision.commitment_id or "")
        if commitment is None:
            return False
        if (
            decision.trace_record_id != commitment.authorizing_record_id
            or decision.trace_record_version != commitment.authorizing_record_version
        ):
            return False
        try:
            record = bundle.trace_repository.get(
                commitment.authorizing_record_id,
                commitment.authorizing_record_version,
            )
        except KeyError:
            return False
        if not record.consumer_actions or record.consumer_actions[-1].decision.value not in {
            "clear",
            "qualify",
        }:
            return False
    for outcome in run.outcomes:
        commitment = commitments.get(outcome.commitment_id)
        if commitment is None:
            return False
        if (
            outcome.authorizing_trace_record_id != commitment.authorizing_record_id
            or outcome.authorizing_trace_record_version != commitment.authorizing_record_version
        ):
            return False
    return True


def _correction_joins_valid(run: ReferenceMissionRun) -> bool:
    compensations = {item.invalidated_commitment_id: item for item in run.compensations}
    debts = {item.invalidated_commitment_id: item for item in run.consistency_debts}
    if len(compensations) != len(run.compensations) or len(debts) != len(run.consistency_debts):
        return False
    for contradiction in run.contradictions:
        compensation = compensations.get(contradiction.commitment_id)
        if compensation is None:
            return False
        if compensation.triggering_trace_record_id != contradiction.authorizing_trace_record_id:
            return False
        debt = debts.get(contradiction.commitment_id)
        if compensation.status == "failed":
            if debt is None or debt.failed_compensation_id != compensation.compensation_id:
                return False
        elif debt is not None:
            return False
    failed_commitments = {
        item.invalidated_commitment_id for item in run.compensations if item.status == "failed"
    }
    return len(compensations) == len(run.contradictions) and set(debts) == failed_commitments


def _contains_hidden_value(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).casefold() in _HIDDEN_FIELD_NAMES or _contains_hidden_value(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_hidden_value(item) for item in value)
    return isinstance(value, str) and value.startswith(("RI-", "RP-"))


def _public_artifacts_hidden_free(
    bundle: ReferenceRuntimeBundle,
    schedule: ReferenceFaultSchedule,
) -> bool:
    family_labels = tuple(item.family for item in schedule.triggers)
    for event in bundle.event_log.events:
        if event.visibility != ReferenceEventVisibility.CONTROLLER_VISIBLE:
            continue
        try:
            value = json.loads(event.payload_json)
        except json.JSONDecodeError:
            return False
        if _contains_hidden_value(value):
            return False
        public_text = event.payload_json.casefold()
        if any(label in public_text for label in family_labels):
            return False
    return True


def _restart_public_state_equivalent(values: ReferenceG3IntegrityInput) -> bool:
    first = values.faulted_run
    second = values.restarted_run
    return (
        first.decisions == second.decisions
        and first.outcomes == second.outcomes
        and first.contradictions == second.contradictions
        and first.compensations == second.compensations
        and first.consistency_debts == second.consistency_debts
        and first.reconciliations == second.reconciliations
    )


def _restart_durable_state_equivalent(values: ReferenceG3IntegrityInput) -> bool:
    first = values.faulted_bundle
    second = values.restarted_bundle
    return (
        first.trace_repository.prefix_digest == second.trace_repository.prefix_digest
        and first.commitment_log.prefix_digest == second.commitment_log.prefix_digest
        and first.evidence_ledger.prefix_digest == second.evidence_ledger.prefix_digest
    )


def build_reference_g3_integrity_report(
    values: ReferenceG3IntegrityInput,
) -> ReferenceG3IntegrityReport:
    """Build a digest-bound development report without applying statistical gates."""

    expected = tuple(sorted(item.family for item in values.schedule.triggers))
    observed = tuple(sorted(item.family for item in values.restarted_run.fault_applications))
    event_chains = (
        values.faulted_bundle.event_log.verify() and values.restarted_bundle.event_log.verify()
    )
    trace_chains = (
        values.faulted_bundle.trace_repository.verify_chain()
        and values.restarted_bundle.trace_repository.verify_chain()
    )
    evidence_chains = (
        values.faulted_bundle.evidence_ledger.verify_chain()
        and values.restarted_bundle.evidence_ledger.verify_chain()
    )
    commitment_chains = (
        values.faulted_bundle.commitment_log.verify_chain()
        and values.restarted_bundle.commitment_log.verify_chain()
    )
    fault_coverage = observed == expected
    fault_targets_reachable = (
        not values.faulted_run.unreachable_delivery_fault_ids
        and not values.restarted_run.unreachable_delivery_fault_ids
    )
    exogenous_equal = (
        values.faulted_scenario_input_digest == values.restart_checkpoint_scenario_input_digest
    )
    restart_public = _restart_public_state_equivalent(values)
    restart_durable = _restart_durable_state_equivalent(values)
    authorization_joins = _authorization_joins_valid(
        values.restarted_run,
        values.restarted_bundle,
    )
    correction_joins = _correction_joins_valid(values.restarted_run)
    hidden_free = _public_artifacts_hidden_free(
        values.faulted_bundle,
        values.schedule,
    ) and _public_artifacts_hidden_free(values.restarted_bundle, values.schedule)
    checks = (
        event_chains,
        trace_chains,
        evidence_chains,
        commitment_chains,
        fault_coverage,
        fault_targets_reachable,
        exogenous_equal,
        restart_public,
        restart_durable,
        authorization_joins,
        correction_joins,
        hidden_free,
    )
    body = {
        "schema_version": "delta-reference-g3-runtime-integrity-v1",
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "scenario_seed": values.scenario_seed,
        "scientific_status": "development-integration-check-not-validation-evidence",
        "fault_profile_id": values.schedule.profile_id,
        "expected_fault_families": expected,
        "observed_fault_families": observed,
        "faulted_counts": _counts(values.faulted_run).model_dump(mode="json"),
        "event_chains_valid": event_chains,
        "trace_chains_valid": trace_chains,
        "evidence_chains_valid": evidence_chains,
        "commitment_chains_valid": commitment_chains,
        "fault_coverage_complete": fault_coverage,
        "fault_targets_all_reachable": fault_targets_reachable,
        "exogenous_inputs_byte_equivalent": exogenous_equal,
        "restart_public_state_equivalent": restart_public,
        "restart_durable_state_equivalent": restart_durable,
        "authorization_joins_valid": authorization_joins,
        "correction_joins_valid": correction_joins,
        "public_artifacts_hidden_free": hidden_free,
        "all_checks_pass": all(checks),
    }
    return ReferenceG3IntegrityReport(**body, report_digest=decision_digest(body))
