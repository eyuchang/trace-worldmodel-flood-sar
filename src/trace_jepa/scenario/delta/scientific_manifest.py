from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trace_jepa.scenario.delta.artifacts import canonical_json_bytes, sha256_file


class ScientificInputError(RuntimeError):
    """Raised when a frozen scientific input is missing, substituted, or changed."""


class ScientificInputMember(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_length: int = Field(ge=0)


class ScientificInputManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "delta-scientific-input-manifest-v1"
    scope: str = "WF-DFLD-01-SMALL-v8"
    members: list[ScientificInputMember] = Field(min_length=1)
    aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
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
        return self


_EXPLICIT_INPUTS = (
    "configs/models/vjepa2_1_base.yaml",
    "configs/policies/trace_delta_small_v1.yaml",
    "configs/scenarios/wf_dfld_01_small.yaml",
    "data/scenario/delta/calibration/v8_process_coefficients_v1.json",
    "data/scenario/delta/calibration/v8_reconciliation_selection_v1.json",
    "data/scenario/delta/environment/python311_linux_amd64_v1.json",
    "data/scenario/delta/geography/build_manifest_v3.json",
    "data/scenario/delta/geography/delta_small_geography_v3.yaml",
    "data/scenario/delta/resources/rio_vista_fire_source_extract_v1.json",
    "requirements-delta-python311.lock",
    "scripts/calibrate_delta_v8.py",
    "scripts/select_delta_v8_reconciliation.py",
    "scripts/verify_delta_reference_environment.py",
    "src/trace_jepa/contracts/models.py",
    "src/trace_jepa/controller.py",
    "src/trace_jepa/experimental/profile.py",
    "src/trace_jepa/experimental/revalidation.py",
)


def _within_repository(repository_root: Path, path: Path) -> Path:
    resolved_root = repository_root.resolve(strict=True)
    if repository_root.is_symlink():
        raise ScientificInputError("repository root must not be a symlink")
    if path.is_symlink():
        raise ScientificInputError(f"scientific input must not be a symlink: {path}")
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or not resolved.is_relative_to(resolved_root):
        raise ScientificInputError(f"unsafe scientific input: {path}")
    return resolved


def scientific_input_paths(repository_root: Path) -> list[Path]:
    """Return the complete, self-reference-free v8 scientific input surface."""

    paths = {repository_root / relative for relative in _EXPLICIT_INPUTS}
    paths.update((repository_root / "src/trace_jepa/scenario/delta").glob("*.py"))
    paths.update((repository_root / "src/trace_jepa/predictor").glob("*.py"))
    paths.update((repository_root / "src/trace_jepa/predictor").glob("*.json"))
    paths.update((repository_root / "src/trace_jepa/runtime").glob("*.py"))
    paths.update((repository_root / "data/scenario/delta/geography/sources").glob("*"))
    return sorted((_within_repository(repository_root, path) for path in paths), key=str)


def _aggregate_digest(members: list[ScientificInputMember]) -> str:
    payload = [member.model_dump(mode="json") for member in members]
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


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
    return ScientificInputManifest(members=members, aggregate_sha256=_aggregate_digest(members))


def write_scientific_input_manifest(repository_root: Path, output_path: Path) -> None:
    resolved_root = repository_root.resolve(strict=True)
    if output_path.is_symlink():
        raise ScientificInputError("scientific manifest output must not be a symlink")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_parent = output_path.parent.resolve(strict=True)
    if not resolved_parent.is_relative_to(resolved_root):
        raise ScientificInputError("scientific manifest output must remain inside the repository")
    output_path.write_bytes(
        canonical_json_bytes(
            build_scientific_input_manifest(repository_root).model_dump(mode="json")
        )
    )


def verify_scientific_input_manifest(
    repository_root: Path,
    manifest_path: Path,
) -> ScientificInputManifest:
    safe_manifest = _within_repository(repository_root, manifest_path)
    if safe_manifest.stat().st_size > 1_000_000:
        raise ScientificInputError("scientific input manifest exceeds 1 MB")
    try:
        manifest = ScientificInputManifest.model_validate(json.loads(safe_manifest.read_text()))
    except (OSError, ValueError) as exc:
        raise ScientificInputError("invalid scientific input manifest") from exc
    expected_paths = [
        path.relative_to(repository_root.resolve(strict=True)).as_posix()
        for path in scientific_input_paths(repository_root)
    ]
    if [member.path for member in manifest.members] != expected_paths:
        raise ScientificInputError("scientific input membership changed after freeze")
    for member in manifest.members:
        path = _within_repository(repository_root, repository_root / member.path)
        if path.stat().st_size != member.byte_length or sha256_file(path) != member.sha256:
            raise ScientificInputError(f"scientific input changed after freeze: {member.path}")
    if _aggregate_digest(manifest.members) != manifest.aggregate_sha256:
        raise ScientificInputError("scientific input aggregate digest is invalid")
    return manifest
