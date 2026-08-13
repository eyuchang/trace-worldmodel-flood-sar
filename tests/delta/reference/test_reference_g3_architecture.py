from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from trace_reference.provenance.source_closure import (
    imported_reference_modules,
    reference_source_paths,
)
from trace_reference.runtime import ReferenceDecisionPublicInputs

ROOT = Path(__file__).resolve().parents[3]
_G3_PREFIXES = ("trace_reference.decision", "trace_reference.runtime")


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(ROOT / "src").with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _g3_import_graph() -> dict[str, set[str]]:
    paths = {
        _module_name(path): path
        for path in reference_source_paths(ROOT)
        if _module_name(path).startswith(_G3_PREFIXES)
    }
    return {
        name: {
            imported
            for imported in imported_reference_modules(ROOT, path)
            if imported in paths and imported.startswith(_G3_PREFIXES)
        }
        for name, path in paths.items()
    }


def _assert_acyclic(graph: dict[str, set[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise AssertionError(f"G3 import cycle reaches {node}")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in sorted(graph):
        visit(node)


def test_g3_decision_boundary_exposes_only_registered_public_inputs() -> None:
    assert tuple(item.name for item in fields(ReferenceDecisionPublicInputs)) == (
        "resource_telemetry",
        "resource_catalog",
        "coordination",
        "resource_activations",
        "prior",
    )


def test_g3_runtime_and_decision_import_graph_is_acyclic_and_excludes_generation() -> None:
    graph = _g3_import_graph()
    _assert_acyclic(graph)
    runtime_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in reference_source_paths(ROOT)
        if _module_name(path).startswith(_G3_PREFIXES)
    )
    assert "trace_reference.generation" not in runtime_source

    decision_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in reference_source_paths(ROOT)
        if _module_name(path).startswith("trace_reference.decision")
        or _module_name(path) == "trace_reference.runtime.decision_engine"
    )
    for forbidden in (
        "observations.hidden",
        "resources.hidden",
        "scenario.truth",
        "candidate_audit",
        "truth_incident_id",
        "truth_person_id",
    ):
        assert forbidden not in decision_source
