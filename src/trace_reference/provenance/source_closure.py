"""Static local-import closure for the non-LEAP Reference execution surfaces."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

from trace_jepa.support import ArtifactLocator, safe_directory

_LOCAL_PACKAGE_ROOTS = ("trace_jepa", "trace_reference")
REFERENCE_SOURCE_ENTRY_MODULES = (
    "trace_reference.benchmark_cli",
    "trace_reference.calibration.cli",
    "trace_reference.cli",
    "trace_reference.decision.counterfactual",
    "trace_reference.delivery_history",
    "trace_reference.geography.build_cli",
    "trace_reference.validation.g3_handoff",
    "trace_reference.validation.canonical_receipt",
    "trace_reference.validation.original_execution",
)
_MAX_SOURCE_BYTES = 4 * 1024 * 1024


class ReferenceSourceClosureError(RuntimeError):
    """A registered local module is absent, unsafe, or syntactically invalid."""


def _is_local_module(module_name: str) -> bool:
    return module_name in _LOCAL_PACKAGE_ROOTS or module_name.startswith(
        tuple(f"{root}." for root in _LOCAL_PACKAGE_ROOTS)
    )


def reference_module_path(repository_root: Path, module_name: str) -> Path | None:
    """Resolve one local module without searching ambient import paths."""

    relative = Path("src") / Path(*module_name.split("."))
    candidates = (relative.with_suffix(".py"), relative / "__init__.py")
    for candidate in candidates:
        path = repository_root / candidate
        if not path.is_file():
            continue
        return ArtifactLocator(
            root=repository_root,
            relative_name=candidate,
            maximum_bytes=_MAX_SOURCE_BYTES,
            label=f"Reference source module {module_name}",
        ).resolve()
    return None


def _module_name(repository_root: Path, path: Path) -> str:
    source_root = safe_directory(
        repository_root / "src",
        declared_root=repository_root,
        label="Reference source-closure root",
    )
    relative = path.relative_to(source_root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _import_base(current: str, path: Path, node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        return node.module
    package = current.split(".") if path.name == "__init__.py" else current.split(".")[:-1]
    keep = len(package) - (node.level - 1)
    if keep < 1:
        return None
    parts = package[:keep]
    if node.module:
        parts.extend(node.module.split("."))
    return ".".join(parts)


def imported_reference_modules(repository_root: Path, path: Path) -> set[str]:
    """Return resolvable local imports declared by one trusted source file."""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise ReferenceSourceClosureError(f"cannot parse Reference source module: {path}") from exc
    current = _module_name(repository_root, path)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(item.name for item in node.names if _is_local_module(item.name))
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        base = _import_base(current, path, node)
        if base is None or not _is_local_module(base):
            continue
        modules.add(base)
        modules.update(
            candidate
            for alias in node.names
            if alias.name != "*"
            and (candidate := f"{base}.{alias.name}")
            and reference_module_path(repository_root, candidate) is not None
        )
    return modules


def _parent_initializers(repository_root: Path, module_name: str) -> set[Path]:
    parts = module_name.split(".")
    parents = set()
    for end in range(1, len(parts)):
        parent = reference_module_path(repository_root, ".".join(parts[:end]))
        if parent is not None and parent.name == "__init__.py":
            parents.add(parent)
    return parents


def reference_source_paths(
    repository_root: Path,
    entry_modules: Iterable[str] = REFERENCE_SOURCE_ENTRY_MODULES,
) -> tuple[Path, ...]:
    """Compute the deterministic transitive source closure for base Reference."""

    root = safe_directory(
        repository_root,
        declared_root=repository_root,
        label="Reference source-closure repository",
    )
    pending = list(entry_modules)
    visited: set[str] = set()
    paths: set[Path] = set()
    while pending:
        module_name = pending.pop()
        if module_name in visited:
            continue
        visited.add(module_name)
        path = reference_module_path(root, module_name)
        if path is None:
            raise ReferenceSourceClosureError(
                f"registered Reference source module is absent: {module_name}"
            )
        paths.add(path)
        paths.update(_parent_initializers(root, module_name))
        pending.extend(imported_reference_modules(root, path) - visited)
    return tuple(sorted(paths, key=lambda item: item.relative_to(root).as_posix()))
