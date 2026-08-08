from __future__ import annotations

import importlib
import importlib.metadata
import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from trace_jepa.support import sha256_file

_LOCK_REQUIREMENT = re.compile(r"^([A-Za-z0-9_.-]+)==([^ ;\\]+)")


class ReferenceEnvironmentError(RuntimeError):
    """Raised when execution does not match the frozen Delta reference environment."""


class EnvironmentContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    contract_id: str
    scope: str
    package_python_support: str
    exact_python_version: str
    platform_system: str
    platform_machine: str
    oci_image: str
    oci_tag_for_discovery_only: str
    oci_index_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    oci_platform_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    oci_platform: str
    dependency_lock_file: str
    dependency_lock_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dependency_input_file: str
    dependency_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_imports: list[str] = Field(min_length=1)
    installation: str
    claims: list[str] = Field(min_length=1)

    @property
    def immutable_image_reference(self) -> str:
        return f"{self.oci_image}@sha256:{self.oci_platform_manifest_sha256}"


class EnvironmentVerification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_id: str
    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    lock_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    interpreter: str
    platform_system: str
    platform_machine: str
    checked_distributions: dict[str, str]
    mismatches: list[str]

    @property
    def matches(self) -> bool:
        return not self.mismatches


def load_environment_contract(path: Path) -> EnvironmentContract:
    if path.is_symlink():
        raise ReferenceEnvironmentError(f"environment contract must not be a symlink: {path}")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ReferenceEnvironmentError(f"environment contract must be a regular file: {resolved}")
    try:
        return EnvironmentContract.model_validate_json(resolved.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise ReferenceEnvironmentError(f"invalid environment contract: {resolved}") from exc


def locked_distributions(lock_path: Path) -> dict[str, str]:
    if lock_path.is_symlink():
        raise ReferenceEnvironmentError(f"dependency lock must not be a symlink: {lock_path}")
    resolved = lock_path.resolve(strict=True)
    requirements: dict[str, str] = {}
    for line in resolved.read_text("utf-8").splitlines():
        match = _LOCK_REQUIREMENT.match(line)
        if match is None:
            continue
        name, version = match.groups()
        normalized = re.sub(r"[-_.]+", "-", name).lower()
        if normalized in requirements:
            raise ReferenceEnvironmentError(f"duplicate locked distribution: {name}")
        requirements[normalized] = version
    if not requirements:
        raise ReferenceEnvironmentError(f"dependency lock has no pinned distributions: {resolved}")
    return requirements


def inspect_reference_environment(
    contract_path: Path,
    lock_path: Path,
) -> EnvironmentVerification:
    contract = load_environment_contract(contract_path)
    lock_digest = sha256_file(lock_path)
    mismatches: list[str] = []
    if lock_path.name != contract.dependency_lock_file:
        mismatches.append("dependency lock file name differs from the contract")
    if lock_digest != contract.dependency_lock_sha256:
        mismatches.append("dependency lock digest differs from the contract")
    interpreter = platform.python_version()
    if interpreter != contract.exact_python_version:
        mismatches.append(
            f"Python {interpreter} != required Python {contract.exact_python_version}"
        )
    platform_system = platform.system()
    if platform_system != contract.platform_system:
        mismatches.append(
            f"platform system {platform_system} != required {contract.platform_system}"
        )
    platform_machine = platform.machine()
    if platform_machine != contract.platform_machine:
        mismatches.append(
            f"platform machine {platform_machine} != required {contract.platform_machine}"
        )
    installed: dict[str, str] = {}
    for normalized_name, expected_version in locked_distributions(lock_path).items():
        try:
            actual_version = importlib.metadata.version(normalized_name)
        except importlib.metadata.PackageNotFoundError:
            mismatches.append(f"locked distribution is not installed: {normalized_name}")
            continue
        installed[normalized_name] = actual_version
        if actual_version != expected_version:
            mismatches.append(f"{normalized_name} {actual_version} != locked {expected_version}")
    for module_name in contract.required_imports:
        try:
            importlib.import_module(module_name)
        except (ImportError, OSError) as exc:
            mismatches.append(f"required import {module_name} failed: {exc}")
    return EnvironmentVerification(
        contract_id=contract.contract_id,
        contract_sha256=sha256_file(contract_path),
        lock_sha256=lock_digest,
        interpreter=interpreter,
        platform_system=platform_system,
        platform_machine=platform_machine,
        checked_distributions=dict(sorted(installed.items())),
        mismatches=mismatches,
    )


def require_reference_environment(contract_path: Path, lock_path: Path) -> None:
    verification = inspect_reference_environment(contract_path, lock_path)
    if not verification.matches:
        raise ReferenceEnvironmentError("; ".join(verification.mismatches))


def execution_receipt(
    contract_path: Path,
    lock_path: Path,
    *,
    source_commit: str,
    ci_run_id: str | None = None,
    execution_role: str | None = None,
) -> dict[str, object]:
    verification = inspect_reference_environment(contract_path, lock_path)
    return {
        "schema_version": "delta-execution-receipt-v1",
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit,
        "ci_run_id": ci_run_id,
        "execution_role": execution_role,
        "python_executable": sys.executable,
        **verification.model_dump(mode="json"),
    }
