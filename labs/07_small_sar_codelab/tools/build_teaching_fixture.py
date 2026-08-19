"""Export the approved public Small records into the dependency-free student fixture.

This is an instructor/release tool.  It reads the registered public book, selects
only the four named teaching cases, and writes a compact JSON fixture consumed
by the student-only runtime.  It never reads or copies hidden truth, lineage,
validation, or research-source artifacts into the student workspace.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

LAB_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = LAB_ROOT.parents[1]
CASES_PATH = LAB_ROOT / "student" / "_support" / "cases.json"
DEFAULT_OUTPUT = LAB_ROOT / "student" / "_support" / "teaching_fixture.json"
SCENARIO_OUTPUT_NAMES = (
    "calls.json",
    "evidence_ledger.json",
    "trace_records.json",
    "controller_decisions.json",
    "commitments.json",
    "outcomes.json",
)


class FixtureBuildError(RuntimeError):
    """Raised when the frozen public records cannot form the teaching fixture."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FixtureBuildError(f"cannot read JSON from {path}") from exc


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _one(
    items: Iterable[Mapping[str, Any]],
    *,
    label: str,
    predicate: Any,
) -> Mapping[str, Any]:
    matches = [item for item in items if predicate(item)]
    if len(matches) != 1:
        raise FixtureBuildError(f"expected exactly one {label}; found {len(matches)}")
    return matches[0]


def _selected_event(
    spec: Mapping[str, Any],
    decisions: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    return _one(
        decisions,
        label=f"controller event for {spec['case_id']}",
        predicate=lambda item: item.get("call_id") == spec["call_id"]
        and item.get("trace_record_id") == spec["trace_record_id"]
        and item.get("trace_record_version") == spec["trace_record_version"],
    )


def _request_and_resources(
    call: Mapping[str, Any],
    event: Mapping[str, Any],
    predictor_requests: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    call_id = str(event["call_id"])
    predictor = _one(
        predictor_requests,
        label=f"predictor request for {call_id}",
        predicate=lambda item: item.get("plan", {})
        .get("actions", [{}])[0]
        .get("parameters", {})
        .get("call_id")
        == call_id,
    )
    action = predictor["plan"]["actions"][0]
    context = predictor["observation"]["context"]
    request = {
        "call_id": call_id,
        "belief_cluster_id": str(event["belief_cluster_id"]),
        "call_type": str(call["reported"]["call_type"]),
        "action_type": str(action["action_type"]),
        "required_capability": str(action["parameters"]["required_capability"]),
        "route_id": str(action["route_id"]),
        "simulation_time_s": int(context["simulation_time_s"]),
    }
    resources = [
        {
            "resource_id": str(item["resource_id"]),
            "capabilities": [str(value) for value in item["capabilities"]],
            "currently_available": bool(item["currently_available"]),
            "route_reachable": bool(item["route_reachable"]),
            "route_id": str(item["route_id"]),
            "routed_travel_s": int(item["routed_travel_s"]),
        }
        for item in context["compatible_resources"]
    ]
    return request, resources


def _authorization(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "call_id": str(event["call_id"]),
        "belief_cluster_id": str(event["belief_cluster_id"]),
        "record_id": str(event["trace_record_id"]),
        "record_version": int(event["trace_record_version"]),
        "decision": str(event["trace_decision"]),
        "visible_evidence_basis": [str(item) for item in event["visible_evidence_basis"]],
    }


def _scenario_artifacts(
    specs: Sequence[Mapping[str, Any]],
    artifacts: Mapping[str, Any],
) -> dict[str, list[Mapping[str, Any]]]:
    events = [_selected_event(spec, artifacts["controller_decisions.json"]) for spec in specs]
    call_ids = {str(event["call_id"]) for event in events}
    trace_versions = {
        (str(event["trace_record_id"]), int(event["trace_record_version"])) for event in events
    }
    commitment_ids = {
        str(event["commitment_id"])
        for event in events
        if event.get("commitment_id") is not None
    }
    return {
        "calls.json": [
            item for item in artifacts["calls.json"] if str(item.get("call_id")) in call_ids
        ],
        "evidence_ledger.json": [
            item
            for item in artifacts["evidence_ledger.json"]
            if str(item.get("evidence_id", "")).removeprefix("evidence-") in call_ids
        ],
        "trace_records.json": [
            item
            for item in artifacts["trace_records.json"]
            if (str(item.get("record_id")), int(item.get("record_version", -1))) in trace_versions
        ],
        "controller_decisions.json": events,
        "commitments.json": [
            item
            for item in artifacts["commitments.json"]
            if str(item.get("commitment_id")) in commitment_ids
        ],
        "outcomes.json": [
            item
            for item in artifacts["outcomes.json"]
            if str(item.get("authorizing_commitment_id")) in commitment_ids
        ],
    }


def _load_public_artifacts(
    manifest: Mapping[str, Any],
    book_path: Path,
) -> dict[str, Any]:
    declared = manifest.get("public_artifacts")
    if not isinstance(declared, list):
        raise FixtureBuildError("cases manifest has no public artifact list")
    artifacts: dict[str, Any] = {}
    for descriptor in declared:
        if not isinstance(descriptor, dict):
            raise FixtureBuildError("public artifact descriptor must be an object")
        name = descriptor.get("file_name")
        if not isinstance(name, str) or Path(name).name != name:
            raise FixtureBuildError("public artifact name must be a simple file name")
        path = book_path / name
        if _sha256(path) != descriptor.get("sha256"):
            raise FixtureBuildError(f"public artifact hash drift: {name}")
        artifacts[name] = _load_json(path)
    return artifacts


def _build_case(spec: Mapping[str, Any], artifacts: Mapping[str, Any]) -> dict[str, Any]:
    event = _selected_event(spec, artifacts["controller_decisions.json"])
    call_id = str(spec["call_id"])
    call = _one(
        artifacts["calls.json"],
        label=f"call for {spec['case_id']}",
        predicate=lambda item: item.get("call_id") == call_id,
    )
    request, resources = _request_and_resources(call, event, artifacts["predictor_requests.json"])
    return {
        "case_id": str(spec["case_id"]),
        "request": request,
        "authorization": _authorization(event),
        "resources": resources,
        "expected": {
            "event_type": str(spec["expected_event_type"]),
            "reason_code": str(spec["expected_reason_code"]),
            "selected_resource_id": spec.get("expected_resource_id"),
        },
    }


def build_fixture() -> dict[str, Any]:
    """Return the compact, public-only teaching fixture bound to the Small book."""

    manifest = _load_json(CASES_PATH)
    source = manifest.get("source")
    if not isinstance(source, dict):
        raise FixtureBuildError("cases manifest has no source record")
    book_path = (REPO_ROOT / str(source.get("book_path", ""))).resolve()
    reference_root = (REPO_ROOT / "data" / "scenario" / "delta" / "reference").resolve()
    if reference_root not in book_path.parents:
        raise FixtureBuildError("case source must remain inside the public reference root")
    if _sha256(book_path / "manifest.json") != source.get("book_manifest_sha256"):
        raise FixtureBuildError("public book manifest hash drift")

    artifacts = _load_public_artifacts(manifest, book_path)

    specs = manifest.get("cases")
    if not isinstance(specs, list) or len(specs) != 4:
        raise FixtureBuildError("expected four teaching-case specifications")
    cases: list[dict[str, Any]] = []
    for spec in specs:
        if not isinstance(spec, dict):
            raise FixtureBuildError("case specification must be an object")
        cases.append(_build_case(spec, artifacts))

    scenario = _scenario_artifacts(specs, artifacts)
    if tuple(scenario) != SCENARIO_OUTPUT_NAMES:
        raise FixtureBuildError("teaching scenario has an unexpected output path")
    counts = {
        "allocated": sum(case["expected"]["event_type"] == "allocation" for case in cases),
        "refused": sum(case["expected"]["event_type"] == "refusal" for case in cases),
        "repaired": sum(case["expected"]["event_type"] == "repair" for case in cases),
    }
    return {
        "schema_version": "trace-small-sar-teaching-fixture-v2",
        "scenario_summary": counts,
        "scenario_artifacts": scenario,
        "cases": cases,
    }


def write_fixture(output: Path, *, overwrite: bool) -> None:
    """Write one canonical fixture after validating its exact public provenance."""

    resolved = output.expanduser().resolve()
    if resolved.exists() and not overwrite:
        raise FixtureBuildError(f"refusing to overwrite {resolved}")
    if resolved.name != "teaching_fixture.json":
        raise FixtureBuildError("fixture output must be named teaching_fixture.json")
    if not resolved.parent.is_dir():
        raise FixtureBuildError("fixture output directory must already exist")
    payload = json.dumps(build_fixture(), indent=2, sort_keys=True) + "\n"
    resolved.write_text(payload, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        write_fixture(args.output, overwrite=args.overwrite)
    except (FixtureBuildError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 2
    print(f"public teaching fixture ready: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
