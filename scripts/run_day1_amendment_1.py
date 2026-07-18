#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from trace_jepa.evaluation.day1 import _atomic_json, run_g2, run_smoke
from trace_jepa.evaluation.runner import scientific_source_tree_hash
from trace_jepa.evaluation.workloads import load_evaluation_workload
from trace_jepa.util import sha256_file, sha256_value


AMENDMENT_ID = "g2-workload-amendment-1"
ORIGINAL_MANIFEST_SHA256 = (
    "4595cd658e2888eb841dc7c198e5f838329b5d1d45f80bd0725a3f0502b23184"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _verify_original_evidence(private_root: Path) -> dict:
    evidence_root = private_root / "day1-evidence/day1-protocol"
    manifest_path = evidence_root / "DAY1_EVIDENCE_MANIFEST.json"
    if sha256_file(manifest_path) != ORIGINAL_MANIFEST_SHA256:
        raise RuntimeError("original Day-1 evidence manifest hash changed")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for relative_path, expected in manifest["files"].items():
        path = evidence_root / relative_path
        if sha256_file(path) != expected:
            raise RuntimeError(f"original evidence changed: {relative_path}")

    completion_paths = sorted((evidence_root / "g2").rglob("COMPLETED.json"))
    for completion_path in completion_paths:
        cell_root = completion_path.parent.resolve(strict=True)
        marker = json.loads(completion_path.read_text(encoding="utf-8"))
        expected_artifacts = marker["artifact_sha256"]
        actual_artifacts = {
            path.relative_to(cell_root).as_posix()
            for path in cell_root.rglob("*")
            if path.is_file() and path.name != "COMPLETED.json"
        }
        if actual_artifacts != set(expected_artifacts):
            raise RuntimeError(
                f"original cell inventory changed: {cell_root.relative_to(evidence_root)}"
            )
        for relative_path, expected_hash in expected_artifacts.items():
            artifact_path = cell_root / relative_path
            resolved_artifact = artifact_path.resolve(strict=True)
            try:
                resolved_artifact.relative_to(cell_root)
            except ValueError as exc:
                raise RuntimeError("original artifact path escapes its cell") from exc
            if artifact_path.is_symlink() or not artifact_path.is_file():
                raise RuntimeError("original artifact must be a regular non-symlink file")
            if sha256_file(artifact_path) != expected_hash:
                raise RuntimeError(
                    f"original artifact changed: "
                    f"{artifact_path.relative_to(evidence_root)}"
                )
    lines = sorted(
        f"{sha256_file(path)}  {path.relative_to(evidence_root).as_posix()}\n"
        for path in completion_paths
    )
    listing_hash = hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()
    if len(completion_paths) != manifest["completion_marker_count"]:
        raise RuntimeError("original completion-marker count changed")
    if listing_hash != manifest["completion_marker_listing_sha256"]:
        raise RuntimeError("original completion-marker listing hash changed")
    return manifest


def _verify_amendment(
    *,
    repository_root: Path,
    protocol_path: Path,
    workload_path: Path,
    expected_amendment_id: str = AMENDMENT_ID,
) -> dict:
    checksum_path = protocol_path.with_suffix(".sha256")
    checksum_fields = checksum_path.read_text(encoding="utf-8").split()
    if len(checksum_fields) != 2 or checksum_fields[1] != protocol_path.name:
        raise RuntimeError("protocol amendment checksum file is invalid")
    if checksum_fields[0] != sha256_file(protocol_path):
        raise RuntimeError("protocol amendment checksum does not match")
    amendment = json.loads(protocol_path.read_text(encoding="utf-8"))
    if amendment["amendment_id"] != expected_amendment_id:
        raise RuntimeError("unexpected protocol amendment ID")
    source_hash = scientific_source_tree_hash(repository_root)
    if amendment["amended_source_tree_sha256"] != source_hash:
        raise RuntimeError(
            "source tree differs from the predeclared amendment source hash"
        )
    workload = load_evaluation_workload(
        workload_path.name,
        workload_root=workload_path.parent,
        expected_amendment_id=expected_amendment_id,
        expected_regime="R-B",
    )
    if amendment["workload"]["raw_sha256"] != sha256_file(workload_path):
        raise RuntimeError("workload bytes differ from the amendment")
    if amendment["workload"]["semantic_sha256"] != workload.workload_hash:
        raise RuntimeError("workload semantics differ from the amendment")
    if amendment["gate"]["forcing_noise_std"] != [0.35]:
        raise RuntimeError("amended G2 must use the single predeclared noise setting")
    return amendment


def _assert_g2_matches_amendment(
    *,
    g2: dict,
    amendment: dict,
    protocol_path: Path,
) -> dict:
    provenance = g2.get("scientific_provenance")
    if not isinstance(provenance, dict):
        raise RuntimeError("G2 did not produce one consistent scientific provenance")
    expected_workload = amendment["workload"]
    checks = {
        "source tree": (
            provenance["source_tree_hash"],
            amendment["amended_source_tree_sha256"],
        ),
        "protocol": (provenance["protocol"]["sha256"], sha256_file(protocol_path)),
        "workload bytes": (
            provenance["evaluation_workload"]["sha256"],
            expected_workload["raw_sha256"],
        ),
        "workload semantics": (
            provenance["evaluation_workload"]["semantic_hash"],
            expected_workload["semantic_sha256"],
        ),
        "workload ID": (
            provenance["evaluation_workload"]["workload_id"],
            expected_workload["workload_id"],
        ),
        "amendment ID": (
            provenance["protocol_amendment_id"],
            amendment["amendment_id"],
        ),
        "duration": (provenance["duration_s"], 7800.0),
        "tick": (provenance["tick_s"], 1.0),
    }
    mismatches = [name for name, (actual, expected) in checks.items() if actual != expected]
    if mismatches:
        raise RuntimeError(
            "G2 provenance differs from the frozen amendment: "
            + ", ".join(mismatches)
        )
    for setting in g2["history"]:
        phase = setting["phase_provenance"]
        if (
            phase["forcing_noise_std"] != 0.35
            or phase["requested_speed"] != 50.0
            or phase["regime"] != "R-B"
            or phase["partition"] != "development"
        ):
            raise RuntimeError("G2 phase provenance differs from the amendment")
    return provenance


def main() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    private_root = repository_root.parent
    parser = argparse.ArgumentParser(
        description="Run versioned G2 workload amendment 1 and gated smoke."
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--output",
        type=Path,
        default=private_root / "day1-evidence/day1-protocol-amendment-1",
    )
    parser.add_argument("--no-resume", action="store_true")
    arguments = parser.parse_args()

    original_manifest = _verify_original_evidence(private_root)
    protocol_path = private_root / "README_EXPERIMENTS_AMENDMENT_01.json"
    workload_path = repository_root / "configs/workloads/g2_later_horizon_v1.yaml"
    amendment = _verify_amendment(
        repository_root=repository_root,
        protocol_path=protocol_path,
        workload_path=workload_path,
    )
    resolved_output = arguments.output.resolve()
    evidence_parent = (private_root / "day1-evidence").resolve(strict=True)
    original_evidence_root = (evidence_parent / "day1-protocol").resolve(
        strict=True
    )
    expected_output = evidence_parent / "day1-protocol-amendment-1"
    if resolved_output != expected_output:
        raise RuntimeError(
            "amended output must equal the dedicated amendment-1 evidence root"
        )
    try:
        resolved_output.relative_to(original_evidence_root)
    except ValueError:
        pass
    else:
        raise RuntimeError(
            "amended output must not equal or descend from the original evidence root"
        )

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
    )
    _verify_original_evidence(private_root)

    result = {
        "schema_version": "trace-day1-amendment-run-v1",
        "created_at_utc": _utc_now(),
        "amendment_id": AMENDMENT_ID,
        "protocol_sha256": sha256_file(protocol_path),
        "source_tree_sha256": observed_provenance["source_tree_hash"],
        "workload_sha256": observed_provenance["evaluation_workload"][
            "sha256"
        ],
        "parent_evidence_manifest_sha256": ORIGINAL_MANIFEST_SHA256,
        "parent_source_tree_sha256": original_manifest["source_tree_sha256"],
        "g2_status": g2["status"],
        "g2_result_hash": g2["result_hash"],
        "smoke_status": smoke["status"] if smoke is not None else "withheld",
        "smoke_result_hash": (
            smoke["result_hash"] if smoke is not None else None
        ),
    }
    result["result_hash"] = sha256_value(result)
    _atomic_json(arguments.output / "AMENDMENT_RUN_RESULT.json", result)
    print(json.dumps({"g2": g2, "smoke": smoke, "result": result}, indent=2))


if __name__ == "__main__":
    main()
