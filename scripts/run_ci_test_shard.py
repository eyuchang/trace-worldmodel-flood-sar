"""Verify and execute the complete, disjoint CI test-shard registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from trace_jepa.support import ArtifactLocator, safe_directory, safe_output_file

_SCHEMA = "delta-reference-ci-test-shards-v1"
_COVERAGE_SOURCES = (
    "trace_jepa.scenario.delta",
    "trace_jepa.predictor",
    "trace_jepa.experimental.revalidation",
    "trace_jepa.support",
)
_SHARD_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class TestShard:
    """One bounded pytest target set executed in a fresh CI job."""

    shard_id: str
    targets: tuple[str, ...]


@dataclass(frozen=True)
class TestShardRegistry:
    """The complete disjoint test and coverage contract for branch CI."""

    expected_full_node_count: int
    expected_test_file_count: int
    coverage_sources: tuple[str, ...]
    shards: tuple[TestShard, ...]


def _object(value: Any, *, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} must contain exactly {sorted(keys)}")
    return value


def _safe_target(repository_root: Path, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("CI shard targets must be nonempty strings")
    file_name = value.split("::", maxsplit=1)[0]
    pure = PurePosixPath(file_name)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts or pure.parts[0] != "tests":
        raise ValueError(f"CI shard target is outside tests/: {value}")
    candidate = repository_root.joinpath(*pure.parts)
    if candidate.is_symlink() or not candidate.exists():
        raise ValueError(f"CI shard target is absent or symlinked: {value}")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(repository_root):
        raise ValueError(f"CI shard target resolves outside the repository: {value}")
    return value


def load_registry(repository_root: Path, registry_path: Path) -> TestShardRegistry:
    """Load the shard contract through one caller-trusted repository root."""

    root = safe_directory(
        repository_root,
        declared_root=repository_root,
        label="CI repository root",
    )
    path = ArtifactLocator.from_path(
        root=root,
        path=registry_path,
        maximum_bytes=1024 * 1024,
        label="CI shard registry",
    ).resolve()
    payload = _object(
        json.loads(path.read_text(encoding="utf-8")),
        keys={
            "coverage_sources",
            "expected_full_node_count",
            "expected_test_file_count",
            "schema_version",
            "shards",
        },
        label="CI shard registry",
    )
    if payload["schema_version"] != _SCHEMA:
        raise ValueError("CI shard registry schema is unsupported")
    coverage_sources = tuple(payload["coverage_sources"])
    if coverage_sources != _COVERAGE_SOURCES:
        raise ValueError("CI shard registry changed the registered coverage surface")
    raw_shards = payload["shards"]
    if not isinstance(raw_shards, list) or not raw_shards:
        raise ValueError("CI shard registry must declare at least one shard")
    shards = []
    for raw_shard in raw_shards:
        value = _object(raw_shard, keys={"shard_id", "targets"}, label="CI shard")
        shard_id = value["shard_id"]
        if not isinstance(shard_id, str) or _SHARD_ID.fullmatch(shard_id) is None:
            raise ValueError("CI shard ID is invalid")
        raw_targets = value["targets"]
        if not isinstance(raw_targets, list) or not raw_targets:
            raise ValueError(f"CI shard {shard_id} has no targets")
        targets = tuple(_safe_target(root, item) for item in raw_targets)
        if len(set(targets)) != len(targets):
            raise ValueError(f"CI shard {shard_id} repeats a target")
        shards.append(TestShard(shard_id=shard_id, targets=targets))
    if len({item.shard_id for item in shards}) != len(shards):
        raise ValueError("CI shard registry repeats a shard ID")
    for name in ("expected_full_node_count", "expected_test_file_count"):
        if not isinstance(payload[name], int) or payload[name] <= 0:
            raise ValueError(f"CI shard registry {name} must be positive")
    return TestShardRegistry(
        expected_full_node_count=payload["expected_full_node_count"],
        expected_test_file_count=payload["expected_test_file_count"],
        coverage_sources=coverage_sources,
        shards=tuple(shards),
    )


def _collect_nodes(repository_root: Path, targets: tuple[str, ...]) -> tuple[str, ...]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        "-o",
        "addopts=",
        *targets,
    ]
    result = subprocess.run(
        command,
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "pytest collection failed for CI shard targets:\n" + result.stdout + result.stderr
        )
    nodes = tuple(
        line.strip()
        for line in result.stdout.splitlines()
        if line.startswith("tests/") and "::" in line
    )
    if not nodes:
        raise RuntimeError("CI shard target collection produced no pytest nodes")
    return nodes


def verify_registry(
    repository_root: Path,
    registry: TestShardRegistry,
) -> dict[str, object]:
    """Prove that shard nodes are a disjoint, exact partition of the suite."""

    full_nodes = _collect_nodes(repository_root, ("tests",))
    test_files = tuple(sorted(repository_root.joinpath("tests").rglob("test_*.py")))
    assignments: Counter[str] = Counter()
    shard_counts: dict[str, int] = {}
    for shard in registry.shards:
        nodes = _collect_nodes(repository_root, shard.targets)
        assignments.update(nodes)
        shard_counts[shard.shard_id] = len(nodes)
    full = Counter(full_nodes)
    missing = sorted((full - assignments).elements())
    extra = sorted((assignments - full).elements())
    repeated = sorted(node for node, count in assignments.items() if count != 1)
    if missing or extra or repeated:
        raise ValueError(
            "CI shard registry is not an exact disjoint partition: "
            f"missing={missing[:5]} extra={extra[:5]} repeated={repeated[:5]}"
        )
    if len(full_nodes) != registry.expected_full_node_count:
        raise ValueError(
            "CI full-suite node count changed: "
            f"expected {registry.expected_full_node_count}, observed {len(full_nodes)}"
        )
    if len(test_files) != registry.expected_test_file_count:
        raise ValueError(
            "CI test-file count changed: "
            f"expected {registry.expected_test_file_count}, observed {len(test_files)}"
        )
    digest = hashlib.sha256("\n".join(full_nodes).encode("utf-8")).hexdigest()
    return {
        "collection_sha256": digest,
        "full_node_count": len(full_nodes),
        "shard_counts": shard_counts,
        "shard_ids": [item.shard_id for item in registry.shards],
        "test_file_count": len(test_files),
    }


def run_shard(
    repository_root: Path,
    registry: TestShardRegistry,
    *,
    shard_id: str,
    coverage_output: Path,
) -> int:
    """Run one registered shard with the unchanged branch-coverage surface."""

    selected = next((item for item in registry.shards if item.shard_id == shard_id), None)
    if selected is None:
        raise ValueError(f"unknown CI shard: {shard_id}")
    safe_directory(
        coverage_output.parent,
        declared_root=repository_root,
        label="CI coverage output directory",
    )
    output = safe_output_file(
        coverage_output,
        declared_root=repository_root,
        label="CI coverage output",
    )
    if output.exists():
        raise ValueError("CI coverage output already exists")
    environment = dict(os.environ)
    environment["COVERAGE_FILE"] = str(output)
    command = [
        sys.executable,
        "-m",
        "coverage",
        "run",
        "--branch",
        f"--source={','.join(registry.coverage_sources)}",
        "-m",
        "pytest",
        *selected.targets,
    ]
    result = subprocess.run(command, cwd=repository_root, env=environment, check=False)
    if result.returncode == 0 and (not output.is_file() or output.stat().st_size == 0):
        raise RuntimeError("CI shard passed without writing coverage data")
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--shard")
    parser.add_argument("--coverage-output", type=Path)
    args = parser.parse_args()
    root = safe_directory(
        args.repository_root,
        declared_root=args.repository_root,
        label="CI repository root",
    )
    registry = load_registry(root, args.registry)
    if args.verify:
        if args.shard is not None or args.coverage_output is not None:
            parser.error("--verify cannot be combined with shard execution")
        print(json.dumps(verify_registry(root, registry), indent=2, sort_keys=True))
        return 0
    if args.shard is None or args.coverage_output is None:
        parser.error("shard execution requires --shard and --coverage-output")
    return run_shard(
        root,
        registry,
        shard_id=args.shard,
        coverage_output=args.coverage_output,
    )


if __name__ == "__main__":
    raise SystemExit(main())
