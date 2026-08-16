"""Public-only, deterministic runtime for the TRACE Small SAR code lab.

The registered simulator remains read-only.  This module projects a few
controller-visible book records into a bounded teaching loop and invokes the
student's controller functions.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import Any

from lab_types import (
    ReasonCode,
    RescueDecision,
    RescueEventType,
    RescueRequest,
    ResourceView,
    TraceAuthorization,
    TraceDecision,
)
from pydantic import ValidationError

from trace_jepa.contracts import Commitment, TraceRecord, WorldModelEvidence

LAB_ROOT = Path(__file__).resolve().parent
REPO_ROOT = LAB_ROOT.parents[1]
CASE_MANIFEST_PATH = LAB_ROOT / "fixtures" / "public_case_manifest.json"
PROTECTED_OUTPUT_ROOTS = (
    REPO_ROOT / "data" / "scenario" / "delta" / "reference",
    REPO_ROOT / "docs" / "delta" / "validation",
    REPO_ROOT / "src" / "trace_jepa" / "scenario" / "delta",
)


class LabDataError(RuntimeError):
    """Raised when the public teaching input violates its frozen contract."""


@dataclass(frozen=True, slots=True)
class PublicCase:
    """Validated controller-visible input for one teaching case."""

    case_id: str
    request: RescueRequest
    authorization: TraceAuthorization
    resources: tuple[ResourceView, ...]
    canonical_event: Mapping[str, Any]
    canonical_commitment: Mapping[str, Any] | None
    canonical_outcome: Mapping[str, Any] | None
    expected_event_type: str
    expected_reason_code: str
    expected_resource_id: str | None


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LabDataError(f"cannot read valid JSON from {path}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise LabDataError(f"cannot hash {path}") from exc
    return digest.hexdigest()


def _one(items: Iterable[Mapping[str, Any]], *, label: str, predicate: Any) -> Mapping[str, Any]:
    matches = [item for item in items if predicate(item)]
    if len(matches) != 1:
        raise LabDataError(f"expected exactly one {label}; found {len(matches)}")
    return matches[0]


def _load_declared_artifacts(
    case_manifest: Mapping[str, Any],
    book_manifest: Mapping[str, Any],
    book_path: Path,
) -> dict[str, Any]:
    """Hash-check and load the explicitly declared public artifact set."""

    entries = {
        item.get("file_name"): item
        for item in book_manifest.get("artifacts", [])
        if isinstance(item, dict)
    }
    loaded: dict[str, Any] = {}
    for expected in case_manifest.get("public_artifacts", []):
        file_name = expected.get("file_name")
        if not isinstance(file_name, str) or Path(file_name).name != file_name:
            raise LabDataError("public artifact names must be simple file names")
        registered = entries.get(file_name)
        if registered is None:
            raise LabDataError(f"{file_name} is absent from the book manifest")
        if registered.get("contains_hidden_truth") is not False:
            raise LabDataError(f"refusing non-public artifact: {file_name}")
        if registered.get("sha256") != expected.get("sha256"):
            raise LabDataError(f"registered hash drift for {file_name}")

        artifact_path = book_path / file_name
        if _sha256(artifact_path) != expected.get("sha256"):
            raise LabDataError(f"on-disk hash drift for {file_name}")
        loaded[file_name] = _load_json(artifact_path)

    if not loaded:
        raise LabDataError("no public artifacts were declared")
    return loaded


def load_public_book() -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Load and hash-check only artifacts declared public by the book manifest."""

    case_manifest = _load_json(CASE_MANIFEST_PATH)
    source = case_manifest.get("source", {})
    if source.get("base_commit") != "3f912bdf3fbacb679063da9ed2ce15a2330b91ab":
        raise LabDataError("teaching fixture is not bound to the delivered Small commit")

    book_path = (REPO_ROOT / str(source.get("book_path", ""))).resolve()
    reference_root = (REPO_ROOT / "data" / "scenario" / "delta" / "reference").resolve()
    if book_path != reference_root and reference_root not in book_path.parents:
        raise LabDataError("book path escapes the read-only reference root")

    manifest_path = book_path / "manifest.json"
    if _sha256(manifest_path) != source.get("book_manifest_sha256"):
        raise LabDataError("book manifest hash does not match the lab provenance record")
    book_manifest = _load_json(manifest_path)
    if book_manifest.get("scenario_id") != source.get("scenario_id"):
        raise LabDataError("scenario ID does not match the lab provenance record")
    if book_manifest.get("source_tree_sha256") != source.get("source_tree_sha256"):
        raise LabDataError("source tree hash does not match the lab provenance record")

    loaded = _load_declared_artifacts(case_manifest, book_manifest, book_path)
    return case_manifest, loaded


def _request_for_call(
    call_id: str,
    belief_cluster_id: str,
    calls: Sequence[Mapping[str, Any]],
    predictor_requests: Sequence[Mapping[str, Any]],
) -> tuple[RescueRequest, tuple[ResourceView, ...]]:
    call = _one(calls, label=f"call {call_id}", predicate=lambda item: item.get("call_id") == call_id)
    predictor_request = _one(
        predictor_requests,
        label=f"predictor request {call_id}",
        predicate=lambda item: item.get("plan", {})
        .get("actions", [{}])[0]
        .get("parameters", {})
        .get("call_id")
        == call_id,
    )
    plan = predictor_request["plan"]
    action = plan["actions"][0]
    context = predictor_request["observation"]["context"]
    request = RescueRequest(
        call_id=call_id,
        belief_cluster_id=belief_cluster_id,
        call_type=str(call["reported"]["call_type"]),
        action_type=str(action["action_type"]),
        required_capability=str(action["parameters"]["required_capability"]),
        route_id=str(action["route_id"]),
        simulation_time_s=int(context["simulation_time_s"]),
    )
    resources = tuple(
        ResourceView(
            resource_id=str(item["resource_id"]),
            capabilities=tuple(str(value) for value in item["capabilities"]),
            currently_available=bool(item["currently_available"]),
            route_reachable=bool(item["route_reachable"]),
            route_id=str(item["route_id"]),
            routed_travel_s=int(item["routed_travel_s"]),
        )
        for item in context["compatible_resources"]
    )
    return request, resources


def _authorization_for_case(
    spec: Mapping[str, Any],
    event: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> TraceAuthorization:
    raw_record = _one(
        records,
        label=f"TRACE record {spec['trace_record_id']} v{spec['trace_record_version']}",
        predicate=lambda item: item.get("record_id") == spec.get("trace_record_id")
        and item.get("record_version") == spec.get("trace_record_version"),
    )
    try:
        record = TraceRecord.model_validate(raw_record)
    except ValidationError as exc:
        raise LabDataError("selected public TRACE record fails its repository contract") from exc

    if event.get("trace_record_id") != record.record_id:
        raise LabDataError("controller event points to a different TRACE record")
    if event.get("trace_record_version") != record.record_version:
        raise LabDataError("controller event points to a different TRACE version")
    if len(record.consumer_actions) != 1:
        raise LabDataError("selected TRACE record must contain exactly one consumer action")

    decision = TraceDecision(str(event["trace_decision"]))
    if record.consumer_actions[0].decision.value != decision.value:
        raise LabDataError("TRACE record and controller event disagree on the consumer action")

    return TraceAuthorization(
        call_id=str(event["call_id"]),
        belief_cluster_id=str(event["belief_cluster_id"]),
        record_id=record.record_id,
        record_version=record.record_version,
        decision=decision,
        failed_gates=tuple(record.failed_gates),
        supersedes_record_id=record.supersedes_record_id,
        supersedes_record_version=record.supersedes_record_version,
        visible_evidence_basis=tuple(str(item) for item in event["visible_evidence_basis"]),
    )


def build_cases() -> dict[str, PublicCase]:
    """Validate the selected public chains and project them into lab types."""

    manifest, artifacts = load_public_book()
    calls = artifacts["calls.json"]
    decisions = artifacts["controller_decisions.json"]
    predictor_requests = artifacts["predictor_requests.json"]
    evidence = artifacts["evidence_ledger.json"]
    records = artifacts["trace_records.json"]
    commitments = artifacts["commitments.json"]
    outcomes = artifacts["outcomes.json"]
    reconciliation = artifacts["controller_reconciliation.json"]

    if reconciliation.get("hidden_lineage_used") is not False:
        raise LabDataError("selected controller reconciliation must not use hidden lineage")

    built: dict[str, PublicCase] = {}
    for spec in manifest["cases"]:
        call_id = str(spec["call_id"])
        event = _one(
            decisions,
            label=f"controller event {call_id}",
            predicate=lambda item, selected=spec: item.get("call_id") == selected.get("call_id")
            and item.get("trace_record_id") == selected.get("trace_record_id")
            and item.get("trace_record_version") == selected.get("trace_record_version"),
        )
        request, resources = _request_for_call(
            call_id,
            str(event["belief_cluster_id"]),
            calls,
            predictor_requests,
        )
        authorization = _authorization_for_case(spec, event, records)

        evidence_raw = _one(
            evidence,
            label=f"evidence {call_id}",
            predicate=lambda item, selected_id=call_id: item.get("evidence_id")
            == f"evidence-{selected_id}",
        )
        try:
            validated_evidence = WorldModelEvidence.model_validate(evidence_raw)
        except ValidationError as exc:
            raise LabDataError("selected public evidence fails its repository contract") from exc
        selected_record = _one(
            records,
            label=f"selected record {call_id}",
            predicate=lambda item, selected=spec: item.get("record_id")
            == selected.get("trace_record_id")
            and item.get("record_version") == selected.get("trace_record_version"),
        )
        if validated_evidence.evidence_id not in selected_record["evidence_refs"]:
            raise LabDataError("TRACE record does not reference the selected public evidence")

        commitment_raw: Mapping[str, Any] | None = None
        outcome_raw: Mapping[str, Any] | None = None
        commitment_id = event.get("commitment_id")
        if commitment_id is not None:
            commitment_raw = _one(
                commitments,
                label=f"commitment {commitment_id}",
                predicate=lambda item, selected_id=commitment_id: item.get("commitment_id")
                == selected_id,
            )
            try:
                commitment = Commitment.model_validate(commitment_raw)
            except ValidationError as exc:
                raise LabDataError("selected public commitment fails its repository contract") from exc
            if commitment.authorizing_record_id != authorization.record_id:
                raise LabDataError("commitment is authorized by a different TRACE record")
            if commitment.authorizing_record_version != authorization.record_version:
                raise LabDataError("commitment is authorized by a different TRACE version")
            outcome_raw = _one(
                outcomes,
                label=f"outcome for {commitment_id}",
                predicate=lambda item, selected_id=commitment_id: item.get(
                    "authorizing_commitment_id"
                )
                == selected_id,
            )
            if outcome_raw.get("authorizing_trace_record_id") != authorization.record_id:
                raise LabDataError("outcome points to a different TRACE record")
            if outcome_raw.get("authorizing_trace_record_version") != authorization.record_version:
                raise LabDataError("outcome points to a different TRACE version")

        built[str(spec["case_id"])] = PublicCase(
            case_id=str(spec["case_id"]),
            request=request,
            authorization=authorization,
            resources=resources,
            canonical_event=event,
            canonical_commitment=commitment_raw,
            canonical_outcome=outcome_raw,
            expected_event_type=str(spec["expected_event_type"]),
            expected_reason_code=str(spec["expected_reason_code"]),
            expected_resource_id=spec.get("expected_resource_id"),
        )
    return built


def load_controller(name: str) -> ModuleType:
    """Load only one of the two lab-local controller modules."""

    if name not in {"starter", "solution"}:
        raise ValueError("controller must be 'starter' or 'solution'")
    module = importlib.import_module(f"{name}.rescue_controller")
    required = ("eligible_resources", "decide_rescue", "apply_visible_repair")
    if any(not callable(getattr(module, function, None)) for function in required):
        raise LabDataError(f"{name} controller is missing a required function")
    return module


def _decision_dict(decision: RescueDecision) -> dict[str, Any]:
    return {
        key: value.value if isinstance(value, Enum) else value
        for key, value in asdict(decision).items()
    }


def _book_decision(case: PublicCase) -> RescueDecision:
    """Project the registered public controller event without using a solution."""

    return RescueDecision(
        call_id=case.request.call_id,
        belief_cluster_id=case.request.belief_cluster_id,
        event_type=RescueEventType(case.expected_event_type),
        reason_code=ReasonCode(case.expected_reason_code),
        trace_record_id=case.authorization.record_id,
        trace_record_version=case.authorization.record_version,
        trace_decision=case.authorization.decision,
        selected_resource_id=case.expected_resource_id,
    )


def _book_case_result(case: PublicCase) -> dict[str, Any]:
    """Render one canonical public event in the same shape as a lab run."""

    decision = _book_decision(case)
    return {
        "case_id": case.case_id,
        "variant": "none",
        "input": {
            "call_id": case.request.call_id,
            "call_type": case.request.call_type,
            "required_capability": case.request.required_capability,
            "trace_decision": case.authorization.decision.value,
            "trace_record": f"{case.authorization.record_id}@v{case.authorization.record_version}",
            "visible_resources": len(case.resources),
        },
        "student_decision": _decision_dict(decision),
        "public_commitment_id": (
            case.canonical_commitment.get("commitment_id")
            if case.canonical_commitment is not None
            else None
        ),
        "public_observed_outcome": (
            case.canonical_outcome.get("status") if case.canonical_outcome is not None else None
        ),
        "scope": "canonical public chain",
    }


def _book_repair_result(cases: Mapping[str, PublicCase]) -> dict[str, Any]:
    allocation = cases["allocation"]
    repair_case = cases["visible_repair"]
    before = _book_decision(allocation)
    after = _book_decision(repair_case)
    if allocation.canonical_commitment is None:
        raise LabDataError("public repair walkthrough requires the prior commitment")
    return {
        "case_id": repair_case.case_id,
        "variant": "none",
        "input": {
            "call_id": repair_case.request.call_id,
            "belief_cluster_id": repair_case.request.belief_cluster_id,
            "trace_decision": repair_case.authorization.decision.value,
            "trace_record": f"{after.trace_record_id}@v{after.trace_record_version}",
            "visible_evidence_basis": list(repair_case.authorization.visible_evidence_basis),
        },
        "student_history": [_decision_dict(before), _decision_dict(after)],
        "prior_public_commitment_retained": allocation.canonical_commitment["commitment_id"],
        "new_commitment_created": False,
        "scope": "canonical public repair chain",
    }


def run_public_book(case_name: str) -> dict[str, Any]:
    """Render selected registered public events without exposing the solution."""

    cases = build_cases()
    if case_name == "all":
        results = [
            _book_case_result(cases[name])
            for name in ("allocation", "evidence_hold", "capacity_refusal")
        ]
        results.append(_book_repair_result(cases))
    elif case_name == "visible_repair":
        results = [_book_repair_result(cases)]
    else:
        selected = cases.get(case_name)
        if selected is None:
            raise ValueError(f"unknown case: {case_name}")
        results = [_book_case_result(selected)]
    return _report("public-book-records", results)


def _assert_matches_canonical(case: PublicCase, decision: RescueDecision) -> None:
    if decision.event_type.value != case.expected_event_type:
        raise LabDataError(
            f"{case.case_id}: got {decision.event_type.value}, expected {case.expected_event_type}"
        )
    if decision.reason_code.value != case.expected_reason_code:
        raise LabDataError(
            f"{case.case_id}: got reason {decision.reason_code.value}, "
            f"expected {case.expected_reason_code}"
        )
    if decision.selected_resource_id != case.expected_resource_id:
        raise LabDataError(
            f"{case.case_id}: selected {decision.selected_resource_id!r}, "
            f"expected {case.expected_resource_id!r}"
        )


def _variant_resources(case: PublicCase, variant: str) -> tuple[ResourceView, ...]:
    if variant == "none":
        return case.resources
    if variant == "no-capacity" and case.case_id == "allocation":
        return tuple(replace(resource, currently_available=False) for resource in case.resources)
    if variant == "restore-capacity" and case.case_id == "capacity_refusal":
        if not case.resources:
            raise LabDataError("capacity case has no visible resources to restore")
        first = replace(case.resources[0], currently_available=True)
        return (first, *case.resources[1:])
    raise ValueError(f"variant {variant!r} is not defined for case {case.case_id!r}")


def run_case(case: PublicCase, controller: ModuleType, *, variant: str = "none") -> dict[str, Any]:
    """Run one public case through the selected student controller."""

    resources = _variant_resources(case, variant)
    decision = controller.decide_rescue(case.request, case.authorization, resources)
    if not isinstance(decision, RescueDecision):
        raise LabDataError("decide_rescue must return a RescueDecision")
    if variant == "none":
        _assert_matches_canonical(case, decision)

    commitment: Mapping[str, Any] | None = None
    outcome: Mapping[str, Any] | None = None
    if decision.event_type is RescueEventType.ALLOCATION and variant == "none":
        commitment = case.canonical_commitment
        outcome = case.canonical_outcome

    return {
        "case_id": case.case_id,
        "variant": variant,
        "input": {
            "call_id": case.request.call_id,
            "call_type": case.request.call_type,
            "required_capability": case.request.required_capability,
            "trace_decision": case.authorization.decision.value,
            "trace_record": f"{case.authorization.record_id}@v{case.authorization.record_version}",
            "visible_resources": len(resources),
        },
        "student_decision": _decision_dict(decision),
        "public_commitment_id": commitment.get("commitment_id") if commitment else None,
        "public_observed_outcome": outcome.get("status") if outcome else None,
        "scope": "canonical public chain" if variant == "none" else "teaching-only variant",
    }


def run_repair_case(cases: Mapping[str, PublicCase], controller: ModuleType) -> dict[str, Any]:
    """Run the allocation followed by its public visible-evidence repair."""

    allocation = cases["allocation"]
    repair = cases["visible_repair"]
    initial = controller.decide_rescue(
        allocation.request,
        allocation.authorization,
        allocation.resources,
    )
    _assert_matches_canonical(allocation, initial)
    history = controller.apply_visible_repair((initial,), repair.authorization)
    if not isinstance(history, tuple) or len(history) != 2:
        raise LabDataError("repair must return the original event plus exactly one appended event")
    if history[0] != initial:
        raise LabDataError("repair rewrote the existing allocation")
    repaired = history[1]
    if not isinstance(repaired, RescueDecision):
        raise LabDataError("repair history must contain RescueDecision values")
    _assert_matches_canonical(repair, repaired)
    if repaired.selected_resource_id is not None:
        raise LabDataError("book repair must not create a new commitment")
    if allocation.canonical_commitment is None:
        raise LabDataError("repair walkthrough requires the prior public commitment")

    return {
        "case_id": repair.case_id,
        "variant": "none",
        "input": {
            "call_id": repair.request.call_id,
            "belief_cluster_id": repair.request.belief_cluster_id,
            "trace_decision": repair.authorization.decision.value,
            "trace_record": (
                f"{repair.authorization.record_id}@v{repair.authorization.record_version}"
            ),
            "visible_evidence_basis": list(repair.authorization.visible_evidence_basis),
        },
        "student_history": [_decision_dict(item) for item in history],
        "prior_public_commitment_retained": allocation.canonical_commitment["commitment_id"],
        "new_commitment_created": False,
        "scope": "canonical public repair chain",
    }


def _report(controller_name: str, results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "trace-small-sar-teaching-run-v1",
        "scenario_id": "WF-DFLD-01-SMALL",
        "controller": controller_name,
        "registered_result_modified": False,
        "results": list(results),
        "limitations": [
            "synthetic reduced-order teaching simulator",
            "controller-visible evidence only",
            "teaching variants are not registered research results",
            "not evidence of operational emergency-response validity",
        ],
    }


def run_lab(controller_name: str, case_name: str, variant: str = "none") -> dict[str, Any]:
    """Run selected cases and return a deterministic teaching report."""

    if controller_name == "book":
        if variant != "none":
            raise ValueError("public-book walkthrough does not support teaching variants")
        return run_public_book(case_name)

    cases = build_cases()
    controller = load_controller(controller_name)
    if case_name == "all":
        if variant != "none":
            raise ValueError("variants require one explicitly selected case")
        results = [
            run_case(cases[name], controller)
            for name in ("allocation", "evidence_hold", "capacity_refusal")
        ]
        results.append(run_repair_case(cases, controller))
    elif case_name == "visible_repair":
        if variant != "none":
            raise ValueError("the repair case does not support a variant")
        results = [run_repair_case(cases, controller)]
    else:
        selected = cases.get(case_name)
        if selected is None:
            raise ValueError(f"unknown case: {case_name}")
        results = [run_case(selected, controller, variant=variant)]

    return _report(controller_name, results)


def format_report(report: Mapping[str, Any]) -> str:
    """Render a compact, deterministic terminal walkthrough."""

    lines = [
        "TRACE Small SAR teaching loop",
        "-----------------------------",
    ]
    for result in report["results"]:
        if "student_decision" in result:
            decision = result["student_decision"]
            selected = decision["selected_resource_id"] or "none"
            lines.append(
                f"{result['case_id']}: TRACE={decision['trace_decision']} -> "
                f"{decision['event_type']} ({decision['reason_code']}), resource={selected}"
            )
            if result["public_observed_outcome"]:
                lines.append(
                    "  public observed outcome: " + str(result["public_observed_outcome"])
                )
        else:
            before, after = result["student_history"]
            lines.append(
                f"visible_repair: {before['event_type']}@v{before['trace_record_version']} -> "
                f"{after['event_type']}@v{after['trace_record_version']} "
                f"(new commitment={str(result['new_commitment_created']).lower()})"
            )
    lines.extend(
        [
            "-----------------------------",
            "Scope: public Small artifacts; lab-only controller; registered result untouched.",
        ]
    )
    return "\n".join(lines)


def write_report(report: Mapping[str, Any], output: Path) -> None:
    """Atomically write once to an explicit non-protected path; never overwrite."""

    parent = output.expanduser().parent.resolve()
    if not parent.is_dir():
        raise ValueError("output parent directory must already exist")
    resolved = parent / output.name
    for protected in PROTECTED_OUTPUT_ROOTS:
        protected_resolved = protected.resolve()
        if resolved == protected_resolved or protected_resolved in resolved.parents:
            raise ValueError("refusing to write inside a protected scientific directory")
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"

    descriptor, temporary_name = tempfile.mkstemp(
        dir=parent,
        prefix=f".{resolved.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, resolved)
    except FileExistsError as exc:
        raise ValueError("refusing to overwrite an existing output file") from exc
    finally:
        temporary.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the public-only TRACE Small SAR student controller.",
    )
    parser.add_argument(
        "--controller",
        choices=("book", "starter", "solution"),
        default="starter",
        help="Use public book events, student code, or the instructor solution.",
    )
    parser.add_argument(
        "--case",
        choices=("all", "allocation", "evidence_hold", "capacity_refusal", "visible_repair"),
        default="all",
    )
    parser.add_argument(
        "--variant",
        choices=("none", "no-capacity", "restore-capacity"),
        default="none",
        help="Explicitly teaching-only resource-state comparison.",
    )
    parser.add_argument("--output", type=Path, help="Optional new JSON file; never overwritten.")
    parser.add_argument("--json", action="store_true", help="Print deterministic JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run_lab(args.controller, args.case, args.variant)
        if args.output is not None:
            write_report(report, args.output)
    except (LabDataError, NotImplementedError, ValidationError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
