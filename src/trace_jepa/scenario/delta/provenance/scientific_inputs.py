"""Complete, deterministic inventory of WF-DFLD-01-SMALL scientific inputs."""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trace_jepa.support import atomic_write_bytes, canonical_json_bytes, sha256_file


class ScientificInputError(RuntimeError):
    """A frozen scientific input is missing, substituted, or changed."""


class ScientificInputMember(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_length: int = Field(ge=0)


class ScientificInputManifest(BaseModel):
    """Self-reference-free file inventory plus protocol-independent core digest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "delta-scientific-input-manifest-v2"
    scope: str = "WF-DFLD-01-SMALL-v9"
    members: list[ScientificInputMember] = Field(min_length=1)
    core_aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    acceptance_member_path: str = "configs/scenarios/wf_dfld_01_small_acceptance_v5.yaml"
    exclusions: tuple[str, ...] = (
        "generated reports",
        "reference bundles",
        "publication figures",
        "caches",
        "execution receipts",
        "this manifest",
    )

    @model_validator(mode="after")
    def validate_members(self) -> ScientificInputManifest:
        paths = [member.path for member in self.members]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError("scientific-input members must be unique and sorted")
        if self.acceptance_member_path not in paths:
            raise ValueError("scientific-input manifest must include acceptance v9")
        return self


_EXPLICIT_CORE_INPUTS = (
    ".github/workflows/delta-confirmatory-v8.yml",
    "configs/models/vjepa2_1_base.yaml",
    "configs/policies/trace_delta_small_v1.yaml",
    "configs/scenarios/wf_dfld_01_small.yaml",
    "data/scenario/delta/calibration/v7_process_coefficients_v1.json",
    "data/scenario/delta/calibration/v8_process_coefficients_v1.json",
    "data/scenario/delta/calibration/v8_reconciliation_selection_v1.json",
    "data/scenario/delta/environment/python311_linux_amd64_v1.json",
    "data/scenario/delta/geography/build_manifest_v3.json",
    "data/scenario/delta/geography/delta_small_geography_v3.yaml",
    "data/scenario/delta/resources/rio_vista_fire_source_extract_v1.json",
    "models/manifests/vjepa2_1_vit_base_384.manifest.json",
    "pyproject.toml",
    "requirements-delta-python311.in",
    "requirements-delta-python311.lock",
    "src/trace_jepa/predictor/toy_qualification_v1.json",
)


def _safe_member(repository_root: Path, path: Path) -> Path:
    resolved_root = repository_root.resolve(strict=True)
    if repository_root.is_symlink():
        raise ScientificInputError("repository root must not be a symlink")
    try:
        relative = path.absolute().relative_to(repository_root.absolute())
    except ValueError as exc:
        raise ScientificInputError(f"scientific input escapes repository: {path}") from exc
    cursor = repository_root
    for component in relative.parts:
        cursor = cursor / component
        if cursor.is_symlink():
            raise ScientificInputError(f"scientific input crosses a symlink: {cursor}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ScientificInputError(f"scientific input is absent: {path}") from exc
    if not resolved.is_file() or not resolved.is_relative_to(resolved_root):
        raise ScientificInputError(f"unsafe scientific input: {path}")
    return resolved


def scientific_input_paths(
    repository_root: Path,
    *,
    include_acceptance: bool = True,
) -> list[Path]:
    """Enumerate every current non-generated input used by Tasks 1 and 2."""

    paths = {repository_root / relative for relative in _EXPLICIT_CORE_INPUTS}
    if include_acceptance:
        paths.add(repository_root / "configs/scenarios/wf_dfld_01_small_acceptance_v5.yaml")
    paths.update((repository_root / "src/trace_jepa").rglob("*.py"))
    paths.update((repository_root / "scripts").glob("*.py"))
    paths.update((repository_root / "data/scenario/delta/geography/sources").glob("*"))
    return sorted((_safe_member(repository_root, path) for path in paths), key=str)


def _aggregate_digest(members: Iterable[ScientificInputMember]) -> str:
    digest = hashlib.sha256()
    for member in members:
        path_bytes = member.path.encode("utf-8")
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(member.byte_length.to_bytes(8, "big"))
        digest.update(bytes.fromhex(member.sha256))
    return digest.hexdigest()


def build_scientific_input_manifest(repository_root: Path) -> ScientificInputManifest:
    resolved_root = repository_root.resolve(strict=True)
    members = [
        ScientificInputMember(
            path=path.relative_to(resolved_root).as_posix(),
            sha256=sha256_file(path),
            byte_length=path.stat().st_size,
        )
        for path in scientific_input_paths(repository_root)
    ]
    acceptance_path = "configs/scenarios/wf_dfld_01_small_acceptance_v5.yaml"
    core_members = [member for member in members if member.path != acceptance_path]
    return ScientificInputManifest(
        members=members,
        core_aggregate_sha256=_aggregate_digest(core_members),
        aggregate_sha256=_aggregate_digest(members),
    )


def scientific_input_core_aggregate(repository_root: Path) -> str:
    """Hash the complete freeze except the not-yet-created acceptance protocol."""

    resolved_root = repository_root.resolve(strict=True)
    members = [
        ScientificInputMember(
            path=path.relative_to(resolved_root).as_posix(),
            sha256=sha256_file(path),
            byte_length=path.stat().st_size,
        )
        for path in scientific_input_paths(repository_root, include_acceptance=False)
    ]
    return _aggregate_digest(members)


def write_scientific_input_manifest(repository_root: Path, output_path: Path) -> None:
    resolved_root = repository_root.resolve(strict=True)
    if output_path.is_symlink():
        raise ScientificInputError("scientific manifest output must not be a symlink")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_parent = output_path.parent.resolve(strict=True)
    if not resolved_parent.is_relative_to(resolved_root):
        raise ScientificInputError("scientific manifest output must remain inside repository")
    atomic_write_bytes(
        output_path,
        canonical_json_bytes(
            build_scientific_input_manifest(repository_root).model_dump(mode="json")
        ),
        root=resolved_parent,
        label="scientific input manifest",
    )


def verify_scientific_input_manifest(
    repository_root: Path,
    manifest_path: Path,
) -> ScientificInputManifest:
    safe_manifest = _safe_member(repository_root, manifest_path)
    if safe_manifest.stat().st_size > 2_000_000:
        raise ScientificInputError("scientific input manifest exceeds 2 MB")
    try:
        manifest = ScientificInputManifest.model_validate_json(safe_manifest.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise ScientificInputError("invalid scientific input manifest") from exc
    expected = build_scientific_input_manifest(repository_root)
    if manifest != expected:
        expected_by_path = {member.path: member for member in expected.members}
        for member in manifest.members:
            if expected_by_path.get(member.path) != member:
                raise ScientificInputError(f"scientific input changed after freeze: {member.path}")
        raise ScientificInputError("scientific input membership or aggregate changed")
    return manifest


def _module_name(repository_root: Path, path: Path) -> str:
    relative = path.resolve(strict=True).relative_to((repository_root / "src").resolve(strict=True))
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def imported_local_modules(repository_root: Path, path: Path) -> set[str]:
    """Resolve absolute and relative local imports from one source module."""

    tree = ast.parse(path.read_text("utf-8"), filename=str(path))
    modules: set[str] = set()
    current = _module_name(repository_root, path)
    package = current.split(".") if path.name == "__init__.py" else current.split(".")[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(item.name for item in node.names if item.name.startswith("trace_jepa"))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module and node.module.startswith("trace_jepa"):
                modules.add(node.module)
            elif node.level > 0:
                keep = len(package) - (node.level - 1)
                if keep < 1:
                    continue
                prefix = package[:keep]
                if node.module:
                    prefix.extend(node.module.split("."))
                base = ".".join(prefix)
                if base.startswith("trace_jepa"):
                    modules.add(base)
                    modules.update(
                        f"{base}.{alias.name}"
                        for alias in node.names
                        if alias.name != "*"
                        and module_path(repository_root, f"{base}.{alias.name}") is not None
                    )
    return modules


def module_path(repository_root: Path, module_name: str) -> Path | None:
    relative = Path("src") / Path(*module_name.split("."))
    module_file = repository_root / relative.with_suffix(".py")
    package_file = repository_root / relative / "__init__.py"
    if module_file.is_file():
        return module_file
    if package_file.is_file():
        return package_file
    return None


def import_closure(repository_root: Path, entry_modules: Iterable[str]) -> set[Path]:
    """Compute the static transitive local-import closure for registered entries."""

    pending = list(entry_modules)
    visited_modules: set[str] = set()
    paths: set[Path] = set()
    while pending:
        module = pending.pop()
        if module in visited_modules:
            continue
        visited_modules.add(module)
        path = module_path(repository_root, module)
        if path is None:
            continue
        paths.add(path.resolve(strict=True))
        pending.extend(imported_local_modules(repository_root, path) - visited_modules)
    return paths
