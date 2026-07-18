#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from run_day1_amendment_1 import (
    _assert_g2_matches_amendment,
    _verify_amendment,
    _verify_original_evidence,
)
from trace_jepa.evaluation.day1 import _atomic_json, run_g2, run_smoke
from trace_jepa.util import sha256_file, sha256_value


AMENDMENT_ID = "day1-measurement-amendment-2"
PRIOR_AMENDMENT_MANIFEST_SHA256 = (
    "04733e7cde22dba4b9a8d3658028361af929bba012beefaef51d7bd31f5f6778"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _verify_prior_amendment_evidence(private_root: Path) -> dict:
    evidence_root = private_root / "day1-evidence/day1-protocol-amendment-1"
    manifest_path = evidence_root / "AMENDMENT_1_EVIDENCE_MANIFEST.json"
    checksum_path = evidence_root / "AMENDMENT_1_EVIDENCE_MANIFEST.sha256"
    if sha256_file(manifest_path) != PRIOR_AMENDMENT_MANIFEST_SHA256:
        raise RuntimeError("amendment-1 evidence manifest hash changed")
    checksum = checksum_path.read_text(encoding="utf-8").split()
    if checksum != [PRIOR_AMENDMENT_MANIFEST_SHA256, manifest_path.name]:
        raise RuntimeError("amendment-1 detached checksum is invalid")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for relative_path, expected in manifest["files"].items():
        if sha256_file(evidence_root / relative_path) != expected:
            raise RuntimeError(f"amendment-1 evidence changed: {relative_path}")

    marker_lines: list[str] = []
    artifact_lines: list[str] = []
    completion_paths = sorted(evidence_root.rglob("COMPLETED.json"))
    for completion_path in completion_paths:
        cell_root = completion_path.parent.resolve(strict=True)
        marker_lines.append(
            f"{sha256_file(completion_path)}  "
            f"{completion_path.relative_to(evidence_root).as_posix()}\n"
        )
        marker = json.loads(completion_path.read_text(encoding="utf-8"))
        expected_artifacts = marker["artifact_sha256"]
        actual_paths = {
            path.relative_to(cell_root).as_posix()
            for path in cell_root.rglob("*")
            if path.is_file() and path.name != "COMPLETED.json"
        }
        if actual_paths != set(expected_artifacts):
            raise RuntimeError("amendment-1 cell artifact inventory changed")
        for relative_path, expected in sorted(expected_artifacts.items()):
            artifact_path = cell_root / relative_path
            resolved_artifact = artifact_path.resolve(strict=True)
            try:
                resolved_artifact.relative_to(cell_root)
            except ValueError as exc:
                raise RuntimeError("amendment-1 artifact path escapes its cell") from exc
            if artifact_path.is_symlink() or not artifact_path.is_file():
                raise RuntimeError(
                    "amendment-1 artifact must be a regular non-symlink file"
                )
            if sha256_file(artifact_path) != expected:
                raise RuntimeError("amendment-1 artifact hash changed")
            artifact_lines.append(
                f"{expected}  {artifact_path.relative_to(evidence_root).as_posix()}\n"
            )

    marker_hash = hashlib.sha256(
        "".join(sorted(marker_lines)).encode("utf-8")
    ).hexdigest()
    artifact_hash = hashlib.sha256(
        "".join(sorted(artifact_lines)).encode("utf-8")
    ).hexdigest()
    if len(completion_paths) != manifest["completion_marker_count"]:
        raise RuntimeError("amendment-1 completion-marker count changed")
    if marker_hash != manifest["completion_marker_listing_sha256"]:
        raise RuntimeError("amendment-1 completion-marker aggregate changed")
    if len(artifact_lines) != manifest["referenced_artifact_count"]:
        raise RuntimeError("amendment-1 referenced-artifact count changed")
    if artifact_hash != manifest["referenced_artifact_listing_sha256"]:
        raise RuntimeError("amendment-1 referenced-artifact aggregate changed")
    return manifest


def main() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    private_root = repository_root.parent
    parser = argparse.ArgumentParser(
        description=(
            "Run development-only measurement amendment 2 through G2 and smoke."
        )
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--output",
        type=Path,
        default=private_root / "day1-evidence/day1-protocol-amendment-2",
    )
    parser.add_argument("--no-resume", action="store_true")
    arguments = parser.parse_args()

    original_manifest = _verify_original_evidence(private_root)
    prior_manifest = _verify_prior_amendment_evidence(private_root)
    protocol_path = private_root / "README_EXPERIMENTS_AMENDMENT_02.json"
    workload_path = repository_root / "configs/workloads/g2_later_horizon_v2.yaml"
    amendment = _verify_amendment(
        repository_root=repository_root,
        protocol_path=protocol_path,
        workload_path=workload_path,
        expected_amendment_id=AMENDMENT_ID,
    )

    evidence_parent = (private_root / "day1-evidence").resolve(strict=True)
    expected_output = evidence_parent / "day1-protocol-amendment-2"
    if arguments.output.resolve() != expected_output:
        raise RuntimeError(
            "output must equal the dedicated amendment-2 evidence root"
        )
    protected_roots = {
        (evidence_parent / "day1-protocol").resolve(strict=True),
        (evidence_parent / "day1-protocol-amendment-1").resolve(strict=True),
    }
    for protected in protected_roots:
        try:
            expected_output.relative_to(protected)
        except ValueError:
            continue
        raise RuntimeError("amendment-2 output overlaps protected evidence")

    g2 = run_g2(
        output_root=arguments.output / "g2",
        repository_root=repository_root,
        protocol_path=protocol_path,
        duration_s=7800.0,
        workers=arguments.workers,
        resume=not arguments.no_resume,
        evaluation_workload_path=workload_path,
        protocol_amendment_id=AMENDMENT_ID,
        fixed_noise_settings=(0.35,),
    )
    observed_provenance = _assert_g2_matches_amendment(
        g2=g2,
        amendment=amendment,
        protocol_path=protocol_path,
    )
    smoke = None
    if g2["status"] == "passed":
        smoke = run_smoke(
            noise=0.35,
            output_root=arguments.output / "smoke",
            repository_root=repository_root,
            protocol_path=protocol_path,
            duration_s=7800.0,
            workers=arguments.workers,
            resume=not arguments.no_resume,
            evaluation_workload_path=workload_path,
            protocol_amendment_id=AMENDMENT_ID,
            expected_g2_provenance=g2["selected_phase_provenance"],
        )

    _verify_amendment(
        repository_root=repository_root,
        protocol_path=protocol_path,
        workload_path=workload_path,
        expected_amendment_id=AMENDMENT_ID,
    )
    _verify_original_evidence(private_root)
    _verify_prior_amendment_evidence(private_root)

    result = {
        "schema_version": "trace-day1-measurement-amendment-run-v1",
        "created_at_utc": _utc_now(),
        "amendment_id": AMENDMENT_ID,
        "protocol_sha256": sha256_file(protocol_path),
        "source_tree_sha256": observed_provenance["source_tree_hash"],
        "workload_sha256": observed_provenance["evaluation_workload"]["sha256"],
        "parent_evidence_manifest_sha256": PRIOR_AMENDMENT_MANIFEST_SHA256,
        "parent_source_tree_sha256": prior_manifest["source_tree_sha256"],
        "original_evidence_manifest_sha256": (
            "4595cd658e2888eb841dc7c198e5f838329b5d1d45f80bd0725a3f0502b23184"
        ),
        "original_source_tree_sha256": original_manifest["source_tree_sha256"],
        "g2_status": g2["status"],
        "g2_result_hash": g2["result_hash"],
        "smoke_status": smoke["status"] if smoke is not None else "withheld",
        "smoke_result_hash": smoke["result_hash"] if smoke is not None else None,
    }
    result["result_hash"] = sha256_value(result)
    _atomic_json(arguments.output / "AMENDMENT_RUN_RESULT.json", result)
    print(json.dumps({"g2": g2, "smoke": smoke, "result": result}, indent=2))


if __name__ == "__main__":
    main()
