"""Direct-file and source-tree inventory for Reference replay provenance."""

from __future__ import annotations

import hashlib
from pathlib import Path

from trace_jepa.support import (
    ArtifactLocator,
    canonical_json_bytes,
    safe_directory,
    sha256_file,
)

from .models import ReferenceFileInput, ReferenceValueInput
from .source_closure import reference_source_paths

_MAX_INPUT_BYTES = 256 * 1024 * 1024
_G3_TEST_INPUTS = (
    "tests/delta/reference/test_reference_capacity.py",
    "tests/delta/reference/test_reference_cli.py",
    "tests/delta/reference/test_reference_decision_engine.py",
    "tests/delta/reference/test_reference_g3_architecture.py",
    "tests/delta/reference/test_reference_g3_characterization.py",
    "tests/delta/reference/test_reference_g3_decision.py",
    "tests/delta/reference/test_reference_g3_integrity.py",
    "tests/delta/reference/test_reference_mission_runtime.py",
    "tests/delta/reference/test_reference_observations.py",
    "tests/delta/reference/test_reference_offline_sources.py",
    "tests/delta/reference/test_reference_pipeline.py",
    "tests/delta/reference/test_reference_predictor_evidence.py",
    "tests/delta/reference/test_reference_protocol.py",
    "tests/delta/reference/test_reference_provenance.py",
    "tests/delta/reference/test_reference_runtime_factory.py",
    "tests/delta/reference/test_reference_trace_storage.py",
    "tests/delta/reference/test_reference_visibility.py",
)
_DIRECT_INPUTS = (
    "configs/governance/wf_dfld_01_reference_governance_v1.yaml",
    "configs/scenarios/wf_dfld_01_reference_development.yaml",
    "data/scenario/delta/reference/calibration/reference_truth_coefficients_v2.json",
    "data/scenario/delta/reference/calibration/reference_truth_fit_protocol_v1.yaml",
    "data/scenario/delta/reference/calibration/reference_truth_fit_report_v1.json",
    "data/scenario/delta/reference/calibration/reference_observation_fit_protocol_v1.yaml",
    "data/scenario/delta/reference/calibration/reference_observation_coefficients_v2.json",
    "data/scenario/delta/reference/exposure/reference_exposure_parameters_v1.yaml",
    "data/scenario/delta/reference/environment/reference_python311_linux_amd64_v1.json",
    "data/scenario/delta/reference/geography/derived/reference_geography_build_manifest_v3.json",
    "data/scenario/delta/reference/geography/derived/reference_geography_catalog_v3.json",
    "data/scenario/delta/reference/geography/source_lifecycle_erratum_v1.yaml",
    "data/scenario/delta/reference/geography/source_metadata_v3.yaml",
    "data/scenario/delta/reference/geography/source_retrieval_receipts_v3.yaml",
    "data/scenario/delta/reference/geography/sources/caltrans_local_crossings_v1.geojson",
    "data/scenario/delta/reference/geography/sources/caltrans_state_crossings_v1.geojson",
    "data/scenario/delta/reference/geography/sources/census_designated_places_v1.geojson",
    "data/scenario/delta/reference/geography/sources/census_incorporated_places_v1.geojson",
    "data/scenario/delta/reference/geography/sources/dwr_lma_target_v1.geojson",
    "data/scenario/delta/reference/geography/sources/usgs_gnis_communities_v1.geojson",
    "data/scenario/delta/reference/geography/sources/usgs_gnis_woodward_crossing_v1.geojson",
    "data/scenario/delta/reference/physical/reference_gauge_context_v1.yaml",
    "data/scenario/delta/reference/physical/reference_physical_parameters_v1.yaml",
    "data/scenario/delta/reference/resources/reference_activation_parameters_v1.yaml",
    "data/scenario/delta/reference/resources/reference_resource_parameters_v1.yaml",
    "data/scenario/delta/reference/sources/entity_source_crosswalk_v1.yaml",
    "data/scenario/delta/reference/sources/gauge_identity_research_v1.yaml",
    "data/scenario/delta/reference/sources/requirements_v1.yaml",
    "data/scenario/delta/reference/sources/source_research_v1.yaml",
    "data/scenario/delta/reference/topology_design_v1.yaml",
    "data/scenario/delta/reference_protocol/reference_fault_schedule_v1.json",
    "data/scenario/delta/reference_protocol/reference_g3_acceptance_registry_v1.json",
    "data/scenario/delta/reference_protocol/small_baseline_v1.json",
    "docs/delta/reference/REFERENCE_CAPACITY_PROTOCOL_V1.md",
    "docs/delta/reference/REFERENCE_CALIBRATION_FEASIBILITY_V1.md",
    "docs/delta/reference/REFERENCE_G3_TRACE_LEAP_HANDOFF_ADR_V2.md",
    "docs/delta/reference/REFERENCE_PHYSICAL_MODEL_CARD_V1.md",
    "docs/delta/reference/REFERENCE_REPLAY_PROTOCOL_V1.md",
    "docs/delta/reference/REFERENCE_REPLAY_PROTOCOL_V2.md",
    "docs/delta/reference/WF_DFLD_01_REFERENCE_GEOGRAPHY_AMENDMENT_V2.md",
    "docs/delta/reference/WF_DFLD_01_REFERENCE_PROTOCOL_AMENDMENT_V1.md",
    "docs/delta/reference/WF_DFLD_01_REFERENCE_PROTOCOL_AMENDMENT_V2.md",
    "docs/delta/reference/WF_DFLD_01_REFERENCE_PROTOCOL_AMENDMENT_V3.md",
    "docs/delta/reference/WF_DFLD_01_REFERENCE_PROTOCOL_AMENDMENT_V4.md",
    "docs/delta/reference/WF_DFLD_01_REFERENCE_PROTOCOL_DRAFT.md",
    "docs/delta/reference/TRACE_LEAP_MECHANISM_IDENTITY_AND_ADAPTATION_AUDIT_V1.md",
    "pyproject.toml",
    "requirements-delta-python311.in",
    "requirements-delta-python311.lock",
    *_G3_TEST_INPUTS,
)


def reference_direct_input_paths() -> tuple[str, ...]:
    """Return the unique canonical direct-input path registry."""

    paths = tuple(sorted(_DIRECT_INPUTS))
    if len(set(paths)) != len(paths):
        raise RuntimeError("Reference direct-input path registry contains duplicates")
    return paths


def reference_file_inputs(repository_root: Path) -> tuple[ReferenceFileInput, ...]:
    """Resolve and hash every direct file beneath one caller-trusted repository."""

    inputs = []
    for relative_name in reference_direct_input_paths():
        path = ArtifactLocator(
            root=repository_root,
            relative_name=Path(relative_name),
            maximum_bytes=_MAX_INPUT_BYTES,
            label=f"Reference scientific input {relative_name}",
        ).resolve()
        inputs.append(
            ReferenceFileInput(
                name=Path(relative_name).stem,
                repository_relative_path=relative_name,
                sha256=sha256_file(path),
                byte_length=path.stat().st_size,
            )
        )
    return tuple(inputs)


def reference_source_tree_sha256(repository_root: Path) -> str:
    """Hash the complete transitive source closure for base Reference surfaces."""

    safe_directory(repository_root / "src", declared_root=repository_root, label="source root")
    digest = hashlib.sha256()
    for path in reference_source_paths(repository_root):
        safe = ArtifactLocator.from_path(
            root=repository_root,
            path=path,
            maximum_bytes=4 * 1024 * 1024,
            label="Reference Python source",
        ).resolve()
        relative = safe.relative_to(repository_root).as_posix().encode("utf-8")
        payload = safe.read_bytes()
        digest.update(relative)
        digest.update(b"\0")
        digest.update(str(len(payload)).encode("ascii"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def reference_value_input(name: str, identifier: str, value: object) -> ReferenceValueInput:
    """Create one content-addressed canonical non-file input."""

    return ReferenceValueInput(
        name=name,
        identifier=identifier,
        sha256=hashlib.sha256(canonical_json_bytes(value)).hexdigest(),
    )
