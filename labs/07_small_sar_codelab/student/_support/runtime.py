"""Dependency-free, public-only runtime for the Small SAR student workshop.

The runtime reads one frozen teaching fixture included in the student ZIP.  It
never imports the research repository, contacts a service, downloads a model,
or creates hidden-truth artifacts.  Students can therefore run the same small
scenario on their own laptops with only Python installed.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import Any

from _support.types import (
    ReasonCode,
    RescueDecision,
    RescueEventType,
    RescueRequest,
    ResourceView,
    TraceAuthorization,
    TraceDecision,
)

STUDENT_ROOT = Path(__file__).resolve().parents[1]
LAB_ROOT = STUDENT_ROOT.parent
FIXTURE_PATH = Path(__file__).resolve().with_name("teaching_fixture.json")
SCENARIO_FILES = (
    "calls.json",
    "evidence_ledger.json",
    "trace_records.json",
    "controller_decisions.json",
    "commitments.json",
    "outcomes.json",
)


class LabDataError(RuntimeError):
    """Raised when the bundled public teaching fixture is malformed."""


@dataclass(frozen=True, slots=True)
class PublicCase:
    """One controller-visible case supplied by the workshop fixture."""

    case_id: str
    request: RescueRequest
    authorization: TraceAuthorization
    resources: tuple[ResourceView, ...]
    expected_event_type: str
    expected_reason_code: str
    expected_resource_id: str | None


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LabDataError("the supplied teaching data could not be read") from exc


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise LabDataError(f"{label} must be a JSON object")
    return value


def _list(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise LabDataError(f"{label} must be a JSON list")
    return value


def _fixture() -> Mapping[str, Any]:
    fixture = _mapping(_load_json(FIXTURE_PATH), label="teaching fixture")
    if fixture.get("schema_version") != "trace-small-sar-teaching-fixture-v2":
        raise LabDataError("the teaching fixture has an unsupported version")
    artifacts = _mapping(fixture.get("scenario_artifacts"), label="scenario artifacts")
    if set(artifacts) != set(SCENARIO_FILES):
        raise LabDataError("the teaching fixture has an unexpected scenario file")
    forbidden = {"ground_truth.json", "call_lineage.json"}
    if forbidden.intersection(artifacts):
        raise LabDataError("the teaching fixture contains non-student data")
    return fixture


def _request(raw: Mapping[str, Any]) -> RescueRequest:
    try:
        return RescueRequest(
            call_id=str(raw["call_id"]),
            belief_cluster_id=str(raw["belief_cluster_id"]),
            call_type=str(raw["call_type"]),
            action_type=str(raw["action_type"]),
            required_capability=str(raw["required_capability"]),
            route_id=str(raw["route_id"]),
            simulation_time_s=int(raw["simulation_time_s"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LabDataError("a teaching request is malformed") from exc


def _authorization(raw: Mapping[str, Any]) -> TraceAuthorization:
    try:
        return TraceAuthorization(
            call_id=str(raw["call_id"]),
            belief_cluster_id=str(raw["belief_cluster_id"]),
            record_id=str(raw["record_id"]),
            record_version=int(raw["record_version"]),
            decision=TraceDecision(str(raw["decision"])),
            visible_evidence_basis=tuple(str(item) for item in _list(raw["visible_evidence_basis"], label="visible evidence basis")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise LabDataError("a teaching TRACE authorization is malformed") from exc


def _resources(raw: Any) -> tuple[ResourceView, ...]:
    resources: list[ResourceView] = []
    for item in _list(raw, label="teaching resources"):
        record = _mapping(item, label="teaching resource")
        try:
            resources.append(
                ResourceView(
                    resource_id=str(record["resource_id"]),
                    capabilities=tuple(str(value) for value in _list(record["capabilities"], label="resource capabilities")),
                    currently_available=bool(record["currently_available"]),
                    route_reachable=bool(record["route_reachable"]),
                    route_id=str(record["route_id"]),
                    routed_travel_s=int(record["routed_travel_s"]),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise LabDataError("a teaching resource is malformed") from exc
    return tuple(resources)


def build_cases() -> dict[str, PublicCase]:
    """Load the four frozen, controller-visible teaching cases."""

    cases: dict[str, PublicCase] = {}
    for item in _list(_fixture().get("cases"), label="teaching cases"):
        record = _mapping(item, label="teaching case")
        expected = _mapping(record.get("expected"), label="expected decision")
        case = PublicCase(
            case_id=str(record["case_id"]),
            request=_request(_mapping(record.get("request"), label="teaching request")),
            authorization=_authorization(
                _mapping(record.get("authorization"), label="teaching authorization")
            ),
            resources=_resources(record.get("resources")),
            expected_event_type=str(expected["event_type"]),
            expected_reason_code=str(expected["reason_code"]),
            expected_resource_id=(
                None
                if expected.get("selected_resource_id") is None
                else str(expected["selected_resource_id"])
            ),
        )
        if case.case_id in cases:
            raise LabDataError(f"duplicate teaching case: {case.case_id}")
        cases[case.case_id] = case
    if tuple(cases) != ("allocation", "evidence_hold", "capacity_refusal", "visible_repair"):
        raise LabDataError("the teaching cases are incomplete or out of order")
    return cases


def _decision_dict(decision: RescueDecision) -> dict[str, Any]:
    return {
        key: value.value if isinstance(value, Enum) else value
        for key, value in asdict(decision).items()
    }


def _book_decision(case: PublicCase) -> RescueDecision:
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


def _assert_matches_expected(case: PublicCase, decision: RescueDecision) -> None:
    if decision.event_type.value != case.expected_event_type:
        raise LabDataError(
            f"{case.case_id}: got {decision.event_type.value}, expected {case.expected_event_type}"
        )
    if decision.reason_code.value != case.expected_reason_code:
        raise LabDataError(
            f"{case.case_id}: got {decision.reason_code.value}, expected {case.expected_reason_code}"
        )
    if decision.selected_resource_id != case.expected_resource_id:
        raise LabDataError(f"{case.case_id}: selected an unexpected response unit")


def _case_result(case: PublicCase, decision: RescueDecision, *, variant: str) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "variant": variant,
        "input": {
            "call_id": case.request.call_id,
            "call_type": case.request.call_type,
            "required_capability": case.request.required_capability,
            "trace_decision": case.authorization.decision.value,
            "trace_record": f"{case.authorization.record_id}@v{case.authorization.record_version}",
            "visible_resource_count": len(case.resources),
        },
        "student_decision": _decision_dict(decision),
        "scope": "bundled teaching case" if variant == "none" else "what-if resource copy",
    }


def _repair_result(cases: Mapping[str, PublicCase], controller: ModuleType | None) -> dict[str, Any]:
    allocation = cases["allocation"]
    repair_case = cases["visible_repair"]
    initial = _book_decision(allocation) if controller is None else controller.decide_rescue(
        allocation.request,
        allocation.authorization,
        allocation.resources,
    )
    if not isinstance(initial, RescueDecision):
        raise LabDataError("decide_rescue must return a RescueDecision")
    if controller is not None:
        _assert_matches_expected(allocation, initial)
        history = controller.apply_visible_repair((initial,), repair_case.authorization)
        if not isinstance(history, tuple) or len(history) != 2 or history[0] != initial:
            raise LabDataError("repair must append exactly one decision to the existing history")
        repaired = history[1]
    else:
        repaired = _book_decision(repair_case)
        history = (initial, repaired)
    if not isinstance(repaired, RescueDecision):
        raise LabDataError("repair history must contain RescueDecision values")
    if controller is not None:
        _assert_matches_expected(repair_case, repaired)
    if repaired.selected_resource_id is not None:
        raise LabDataError("a repair must not select a new response unit")
    return {
        "case_id": repair_case.case_id,
        "variant": "none",
        "input": {
            "call_id": repair_case.request.call_id,
            "belief_cluster_id": repair_case.request.belief_cluster_id,
            "trace_decision": repair_case.authorization.decision.value,
            "trace_record": f"{repair_case.authorization.record_id}@v{repair_case.authorization.record_version}",
            "visible_evidence_basis": list(repair_case.authorization.visible_evidence_basis),
        },
        "student_history": [_decision_dict(item) for item in history],
        "new_commitment_created": False,
        "scope": "bundled teaching repair",
    }


def _variant_resources(case: PublicCase, variant: str) -> tuple[ResourceView, ...]:
    if variant == "none":
        return case.resources
    if variant == "no-capacity" and case.case_id == "allocation":
        return tuple(replace(resource, currently_available=False) for resource in case.resources)
    if variant == "restore-capacity" and case.case_id == "capacity_refusal":
        if not case.resources:
            raise LabDataError("the capacity case has no resources to restore")
        first = replace(case.resources[0], currently_available=True)
        return (first, *case.resources[1:])
    raise ValueError(f"variant {variant!r} is not defined for case {case.case_id!r}")


def _report(controller_name: str, results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "trace-small-sar-teaching-run-v2",
        "scenario_id": "WF-DFLD-01-SMALL",
        "controller": controller_name,
        "scenario_files_modified": False,
        "results": list(results),
        "learning_scope": "simulated flood-response exercise",
    }


def _load_controller(name: str) -> ModuleType:
    modules = {
        "exercise": "exercise.rescue_controller",
        "solution": "instructor.solution.rescue_controller",
    }
    if name not in modules:
        raise ValueError("controller must be 'exercise' or 'solution'")
    if name == "solution" and str(LAB_ROOT) not in sys.path:
        sys.path.insert(0, str(LAB_ROOT))
    module = importlib.import_module(modules[name])
    required = ("eligible_resources", "decide_rescue", "apply_visible_repair")
    if any(not callable(getattr(module, function, None)) for function in required):
        raise LabDataError(f"{name} controller is missing a required function")
    return module


def run_lab(controller_name: str, case_name: str, variant: str = "none") -> dict[str, Any]:
    """Run selected teaching cases through supplied records or a controller."""

    cases = build_cases()
    if case_name not in {*cases, "all"}:
        raise ValueError(f"unknown teaching case: {case_name}")
    if controller_name == "book":
        if variant != "none":
            raise ValueError("the supplied walkthrough does not support variants")
        selected = tuple(cases) if case_name == "all" else (case_name,)
        results: list[Mapping[str, Any]] = []
        for case_id in selected:
            if case_id == "visible_repair":
                results.append(_repair_result(cases, None))
            else:
                case = cases[case_id]
                results.append(_case_result(case, _book_decision(case), variant="none"))
        return _report("bundled-public-records", results)

    controller = _load_controller(controller_name)
    selected = tuple(cases) if case_name == "all" else (case_name,)
    if variant != "none" and len(selected) != 1:
        raise ValueError("a what-if variant needs one selected teaching case")
    results = []
    for case_id in selected:
        if case_id == "visible_repair":
            if variant != "none":
                raise ValueError("the repair case does not support variants")
            results.append(_repair_result(cases, controller))
            continue
        case = cases[case_id]
        resources = _variant_resources(case, variant)
        decision = controller.decide_rescue(case.request, case.authorization, resources)
        if not isinstance(decision, RescueDecision):
            raise LabDataError("decide_rescue must return a RescueDecision")
        if variant == "none":
            _assert_matches_expected(case, decision)
        results.append(_case_result(case, decision, variant=variant))
    return _report(controller_name, results)


def format_report(report: Mapping[str, Any]) -> str:
    """Render a concise text walkthrough for students in the terminal."""

    titles = {
        "allocation": "1. Welfare check",
        "evidence_hold": "2. Levee inspection",
        "capacity_refusal": "3. Medical response",
    }
    lines = ["TRACE Small SAR walkthrough", "==========================="]
    for result in report["results"]:
        if "student_decision" not in result:
            before, after = result["student_history"]
            lines.extend(
                (
                    "4. New information about the welfare check",
                    (
                        f"   History: keep allocation v{before['trace_record_version']}, "
                        f"then append repair v{after['trace_record_version']}"
                    ),
                    "   New resource commitment: no",
                    "",
                )
            )
            continue
        decision = result["student_decision"]
        trace_decision = str(decision["trace_decision"]).upper()
        trace_explanation = (
            "continue to the resource check"
            if trace_decision == "CLEAR"
            else "stop before checking resources"
        )
        lines.extend((titles[result["case_id"]], f"   TRACE: {trace_decision} - {trace_explanation}"))
        if decision["event_type"] == "allocation":
            lines.extend(
                (
                    f"   Controller: ALLOCATE {decision['selected_resource_id']}",
                    "   Why: a suitable unit is available and its route is reachable",
                )
            )
        elif decision["reason_code"] == ReasonCode.TRACE_NOT_CLEAR.value:
            lines.extend(("   Controller: REFUSE", "   Why: TRACE did not clear the action"))
        else:
            lines.extend(
                (
                    "   Controller: REFUSE",
                    "   Why: no suitable unit is currently available",
                )
            )
        lines.append("")
    if lines[-1] == "":
        lines.pop()
    lines.extend(
        (
            "===========================",
            "Key idea: CLEAR lets the controller check resources; it does not dispatch one.",
        )
    )
    return "\n".join(lines)


def scenario_summary() -> Mapping[str, int]:
    """Return the exact event counts from the bundled four-case scenario."""

    summary = _mapping(_fixture().get("scenario_summary"), label="scenario summary")
    try:
        return {
            "allocated": int(summary["allocated"]),
            "refused": int(summary["refused"]),
            "repaired": int(summary["repaired"]),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise LabDataError("the bundled scenario summary is malformed") from exc


def _canonical_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def scenario_payloads() -> dict[str, bytes]:
    """Build the six safe, deterministic files for the student scenario run."""

    artifacts = _mapping(_fixture().get("scenario_artifacts"), label="scenario artifacts")
    return {name: _canonical_bytes(artifacts[name]) for name in SCENARIO_FILES}


def write_scenario(output: Path) -> None:
    """Create one public-only teaching scenario directory without overwriting it."""

    resolved = output.expanduser().resolve()
    if resolved.exists():
        raise ValueError(f"{resolved.name} already exists")
    if resolved.parent.is_symlink():
        raise ValueError("scenario output parent must not be a symlink")
    resolved.mkdir(parents=False)
    try:
        for name, payload in scenario_payloads().items():
            (resolved / name).write_bytes(payload)
    except OSError:
        for path in resolved.iterdir():
            path.unlink()
        resolved.rmdir()
        raise


def scenario_directories_match(left: Path, right: Path) -> bool:
    """Return whether both directories contain the exact six teaching files."""

    return all(
        (left / name).is_file()
        and (right / name).is_file()
        and (left / name).read_bytes() == (right / name).read_bytes()
        for name in SCENARIO_FILES
    )


def write_report(report: Mapping[str, Any], output: Path) -> None:
    """Write a JSON report once to an explicit non-symlink output path."""

    parent = output.expanduser().parent.resolve()
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError("report output parent must be a regular directory")
    resolved = parent / output.name
    if resolved.exists() or resolved.is_symlink():
        raise ValueError("refusing to overwrite an existing report")
    descriptor, temporary_name = tempfile.mkstemp(dir=parent, prefix=f".{resolved.name}.", suffix=".tmp")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_canonical_bytes(report))
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, resolved)
    finally:
        temporary.unlink(missing_ok=True)
