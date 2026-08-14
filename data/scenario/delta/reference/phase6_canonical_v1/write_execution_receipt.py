from __future__ import annotations

import argparse
import importlib.metadata
import json
import locale
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pyproj
import rasterio
import shapely

from trace_jepa.scenario.delta.environment import inspect_reference_environment
from trace_jepa.support import atomic_write_bytes, canonical_json_bytes, sha256_file
from trace_reference.decision.canonical import decision_digest
from trace_reference.provenance import build_reference_scientific_input_manifest
from trace_reference.validation.acceptance_models import ReferencePhase6CoreReceipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--core-receipt", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--oci-index-sha256", required=True)
    parser.add_argument("--oci-platform-manifest-sha256", required=True)
    parser.add_argument("--derived-image-digest", required=True)
    parser.add_argument("--dockerfile-sha256", required=True)
    parser.add_argument("--docker-engine-version", required=True)
    arguments = parser.parse_args()

    contract_path = arguments.repository_root / (
        "data/scenario/delta/reference/environment/"
        "reference_python311_linux_amd64_v1.json"
    )
    lock_path = arguments.repository_root / "requirements-delta-python311.lock"
    verification = inspect_reference_environment(contract_path, lock_path)
    if not verification.matches:
        raise RuntimeError(f"canonical environment mismatch: {verification.mismatches}")

    core = ReferencePhase6CoreReceipt.model_validate_json(
        arguments.core_receipt.read_text(encoding="utf-8")
    )
    scientific = build_reference_scientific_input_manifest(arguments.repository_root)
    if core.scientific_input_aggregate_sha256 != scientific.aggregate_sha256:
        raise RuntimeError("core receipt and current scientific inputs disagree")
    resource = core.resource_receipt
    observed_limits_pass = bool(
        resource.wall_time_within_limit
        and resource.peak_memory_within_limit
        and resource.transient_output_within_limit
    )
    distributions = dict(
        sorted(
            (distribution.metadata["Name"], distribution.version)
            for distribution in importlib.metadata.distributions()
        )
    )
    body: dict[str, object] = {
        "schema_version": "delta-reference-canonical-phase6-execution-receipt-v1",
        "scientific_status": (
            "development-integration-canonical-environment-check-not-validation-evidence"
        ),
        "execution_role": "canonical-performance-and-replay-development-check",
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "scenario_id": "WF-DFLD-01-REFERENCE",
        "seed": 20260812,
        "seed_status": "spent-development-illustrative",
        "source_commit": arguments.source_commit,
        "scientific_input_aggregate_sha256": scientific.aggregate_sha256,
        "environment_contract_path": str(contract_path.relative_to(arguments.repository_root)),
        "environment_contract_sha256": sha256_file(contract_path),
        "dependency_lock_path": str(lock_path.relative_to(arguments.repository_root)),
        "dependency_lock_sha256": sha256_file(lock_path),
        "oci_index_sha256": arguments.oci_index_sha256,
        "oci_platform_manifest_sha256": arguments.oci_platform_manifest_sha256,
        "oci_platform": "linux/amd64",
        "derived_reference_image_digest": arguments.derived_image_digest,
        "dockerfile_sha256": arguments.dockerfile_sha256,
        "receipt_writer_sha256": sha256_file(Path(__file__)),
        "docker_engine_version": arguments.docker_engine_version,
        "container_constraints": {
            "cpu_count": 1,
            "memory_bytes": 2_147_483_648,
            "memory_swap_bytes": 2_147_483_648,
            "network_mode": "none",
            "pids_limit": 512,
            "repository_mount_read_only": True,
            "root_filesystem_read_only": True,
        },
        "runtime_environment": {
            **verification.model_dump(mode="json"),
            "platform": platform.platform(),
            "python_executable": sys.executable,
            "python_implementation": platform.python_implementation(),
            "python_hash_seed": "0",
            "locale": locale.setlocale(locale.LC_ALL, None),
            "preferred_encoding": locale.getpreferredencoding(False),
            "timezone_names": time.tzname,
            "float_mantissa_bits": sys.float_info.mant_dig,
            "float_radix": sys.float_info.radix,
            "all_distributions": distributions,
            "gdal_version": rasterio.__gdal_version__,
            "geos_version": shapely.geos_version_string,
            "proj_version": pyproj.proj_version_str,
        },
        "raw_core_receipt_path": arguments.core_receipt.name,
        "raw_core_receipt_file_sha256": sha256_file(arguments.core_receipt),
        "raw_core_receipt_digest": core.receipt_digest,
        "raw_resource_receipt_digest": resource.receipt_digest,
        "raw_runner_measurement_role": resource.measurement_role,
        "raw_runner_canonical_gate_status": resource.canonical_gate_status,
        "raw_runner_label_limitation": (
            "The frozen Phase 6 runner labels every direct resource receipt local-preflight; "
            "this separate execution receipt verifies the actual canonical environment."
        ),
        "observed_resource_metrics": {
            "elapsed_milliseconds": resource.elapsed_milliseconds,
            "peak_resident_memory_bytes": resource.peak_resident_memory_bytes,
            "transient_output_bytes": resource.transient_output_bytes,
            "wall_time_limit_s": resource.wall_time_limit_s,
            "peak_memory_limit_bytes": resource.peak_memory_limit_bytes,
            "transient_output_limit_bytes": resource.transient_output_limit_bytes,
        },
        "environment_verification_matches": verification.matches,
        "raw_core_checks_pass": core.all_checks_pass,
        "registered_resource_ceilings_observed_within_limits": observed_limits_pass,
        "exact_replay_byte_identical": core.exact_replay_byte_identical,
        "publication_regeneration_byte_identical": (
            core.publication_regeneration_byte_identical
        ),
        "selection_validation_or_confirmatory_authority": False,
        "leap_behavior_present": False,
    }
    receipt = {**body, "receipt_digest": decision_digest(body)}
    atomic_write_bytes(
        arguments.output_root / "canonical_phase6_execution_receipt.json",
        canonical_json_bytes(receipt),
        root=arguments.output_root,
        label="Reference canonical Phase 6 execution receipt",
    )
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
