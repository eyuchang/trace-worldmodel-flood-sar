"""Enforce the reviewed dependency direction of the canonical Delta packages."""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DELTA = ROOT / "src/trace_jepa/scenario/delta"
CANONICAL_LAYERS = {
    "domain",
    "geography",
    "generation",
    "runtime",
    "reconciliation",
    "provenance",
    "validation",
    "publication",
}
FORBIDDEN_LAYER_EDGES = {
    "domain": {
        "generation",
        "runtime",
        "reconciliation",
        "provenance",
        "validation",
        "publication",
    },
    "geography": {
        "domain",
        "generation",
        "runtime",
        "reconciliation",
        "provenance",
        "validation",
        "publication",
    },
    "generation": {"runtime", "reconciliation", "provenance", "validation", "publication"},
    "reconciliation": {"generation", "runtime", "provenance", "validation", "publication"},
    "runtime": {"generation", "provenance", "validation", "publication"},
    "provenance": {"runtime", "validation", "publication"},
    "publication": {"domain", "geography", "generation", "runtime", "reconciliation", "validation"},
    "validation": {"publication"},
}


class RuntimeImportVisitor(ast.NodeVisitor):
    """Collect imports that execute at module import time, excluding TYPE_CHECKING blocks."""

    def __init__(self) -> None:
        self.imports: list[tuple[str, tuple[str, ...]]] = []

    def visit_If(self, node: ast.If) -> None:
        if isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
            for statement in node.orelse:
                self.visit(statement)
            return
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append((alias.name, ()))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        self.imports.append((module, tuple(alias.name for alias in node.names)))


def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(ROOT / "src").with_suffix("").parts)


def _imports(path: Path) -> list[tuple[str, tuple[str, ...]]]:
    visitor = RuntimeImportVisitor()
    visitor.visit(ast.parse(path.read_text("utf-8"), filename=str(path)))
    return visitor.imports


def _layer(module: str) -> str | None:
    prefix = "trace_jepa.scenario.delta."
    if not module.startswith(prefix):
        return None
    candidate = module.removeprefix(prefix).split(".", maxsplit=1)[0]
    return candidate if candidate in CANONICAL_LAYERS else None


def test_canonical_layers_obey_dependency_direction() -> None:
    violations: list[str] = []
    for source_layer in sorted(CANONICAL_LAYERS):
        for path in sorted((DELTA / source_layer).rglob("*.py")):
            for module, _names in _imports(path):
                destination = _layer(module)
                if destination in FORBIDDEN_LAYER_EDGES[source_layer]:
                    violations.append(
                        f"{path.relative_to(ROOT)}: {source_layer} imports {destination} via {module}"
                    )
    assert violations == []


def test_canonical_packages_have_no_runtime_import_cycles() -> None:
    graph: dict[str, set[str]] = defaultdict(set)
    canonical_prefix = "trace_jepa.scenario.delta."
    paths = [path for layer in CANONICAL_LAYERS for path in sorted((DELTA / layer).rglob("*.py"))]
    modules = {_module_name(path) for path in paths}
    for path in paths:
        source = _module_name(path)
        for imported, _names in _imports(path):
            if imported in modules and imported.startswith(canonical_prefix):
                graph[source].add(imported)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(module: str, trail: tuple[str, ...]) -> None:
        if module in visiting:
            cycle = " -> ".join((*trail, module))
            raise AssertionError(f"canonical Delta import cycle: {cycle}")
        if module in visited:
            return
        visiting.add(module)
        for destination in sorted(graph[module]):
            visit(destination, (*trail, module))
        visiting.remove(module)
        visited.add(module)

    for module in sorted(modules):
        visit(module, ())


def test_canonical_packages_do_not_import_private_cross_module_names() -> None:
    violations: list[str] = []
    for layer in sorted(CANONICAL_LAYERS):
        for path in sorted((DELTA / layer).rglob("*.py")):
            for module, names in _imports(path):
                if module.startswith(("trace_jepa", ".")):
                    private = [name for name in names if name.startswith("_")]
                    if private:
                        violations.append(
                            f"{path.relative_to(ROOT)} imports {private} from {module}"
                        )
    assert violations == []


def test_one_release_compatibility_facades_retain_public_surfaces() -> None:
    from trace_jepa.scenario.delta.artifacts import verify_scenario_artifacts
    from trace_jepa.scenario.delta.loading import load_scenario_config
    from trace_jepa.scenario.delta.models import DeltaScenarioConfig
    from trace_jepa.scenario.delta.runner import DeltaRunResult, run_delta_small

    assert callable(verify_scenario_artifacts)
    assert callable(load_scenario_config)
    assert DeltaScenarioConfig.__name__ == "DeltaScenarioConfig"
    assert DeltaRunResult.__name__ == "DeltaRunResult"
    assert callable(run_delta_small)


def test_ci_checks_the_complete_branch_diff_with_full_history() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text("utf-8")
    assert "fetch-depth: 0" in workflow
    assert "git merge-base HEAD origin/main" in workflow
    assert 'git diff --check "${base}..HEAD"' in workflow
    assert "git diff --check HEAD^" not in workflow
