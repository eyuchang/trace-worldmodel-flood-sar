from __future__ import annotations

import json
import zipfile
from pathlib import Path

import httpx
import pytest
import yaml

from trace_jepa.scenario.delta.artifacts import ArtifactMismatchError, verify_scenario_artifacts
from trace_jepa.scenario.delta.environment import (
    ReferenceEnvironmentError,
    inspect_reference_environment,
    load_environment_contract,
    locked_distributions,
)
from trace_jepa.scenario.delta.geography_builder import (
    GeographyBuildSecurityError,
    _fetch_source,
    _safe_output_path,
    _verify_archive_member,
)
from trace_jepa.scenario.delta.geography_models import GeographyCatalog
from trace_jepa.scenario.delta.geography_sources import GeographySourceDefinition
from trace_jepa.scenario.delta.loading import DeltaConfigurationError, load_geography_catalog
from trace_jepa.support import ArtifactLocator
from trace_jepa.util import sha256_file

ROOT = Path(__file__).resolve().parents[3]
ENVIRONMENT_CONTRACT = ROOT / "data/scenario/delta/environment/python311_linux_amd64_v1.json"
ENVIRONMENT_LOCK = ROOT / "requirements-delta-python311.lock"
GEOGRAPHY = ROOT / "data/scenario/delta/geography/delta_small_geography_v3.yaml"
GEOGRAPHY_MANIFEST = ROOT / "data/scenario/delta/geography/build_manifest_v3.json"


def _json_definition(
    *, retrieval_locator: str | None = "https://example.test/source"
) -> GeographySourceDefinition:
    return GeographySourceDefinition(
        source_id="test-machine-source",
        title="Test source",
        landing_page_locator="https://example.test/about",
        retrieval_locator=retrieval_locator,
        file_name="source.json",
        snapshot_format="json",
        expected_media_types=("application/json",),
        source_tier="test",
        status="test",
        use="security test",
        license_name="test fixture",
        license_locator="https://example.test/license",
        redistribution_status="project-owned-test-fixture",
    )


def test_reference_environment_contract_binds_exact_image_and_complete_hash_lock() -> None:
    contract = load_environment_contract(ENVIRONMENT_CONTRACT)
    assert contract.exact_python_version == "3.11.14"
    assert contract.oci_platform == "linux/amd64"
    assert contract.immutable_image_reference.endswith(
        "@sha256:88b6d3132a0850db3587a4f4ff28d5568e7d65ff99f0ee34f42be864ddb4ca1d"
    )
    assert contract.oci_index_sha256 == (
        "3b3706a90cb23f04fabb0d255824f9a70ceb46177041898133dd5a35f3a50f0a"
    )
    assert contract.required_imports == ["pyproj", "rasterio", "shapely"]
    assert sha256_file(ENVIRONMENT_LOCK) == contract.dependency_lock_sha256
    locked = locked_distributions(ENVIRONMENT_LOCK)
    for required in ("numpy", "pydantic", "pyproj", "rasterio", "shapely", "pytest"):
        assert required in locked


def test_environment_inspection_reports_noncanonical_local_runtime_without_mutation() -> None:
    verification = inspect_reference_environment(ENVIRONMENT_CONTRACT, ENVIRONMENT_LOCK)
    if verification.matches:
        assert verification.interpreter == "3.11.14"
        assert verification.platform_system == "Linux"
        assert verification.platform_machine == "x86_64"
    else:
        assert verification.mismatches


def test_environment_inputs_reject_symlinks(tmp_path: Path) -> None:
    contract_link = tmp_path / "contract.json"
    contract_link.symlink_to(ENVIRONMENT_CONTRACT)
    with pytest.raises(ReferenceEnvironmentError, match="symlink"):
        load_environment_contract(contract_link)

    lock_link = tmp_path / "lock.txt"
    lock_link.symlink_to(ENVIRONMENT_LOCK)
    with pytest.raises(ReferenceEnvironmentError, match="symlink"):
        locked_distributions(lock_link)


def test_delta_configuration_inputs_reject_symlinks(tmp_path: Path) -> None:
    geography_link = tmp_path / "geography.yaml"
    geography_link.symlink_to(GEOGRAPHY)
    with pytest.raises(DeltaConfigurationError, match="must not be a symlink"):
        load_geography_catalog(geography_link)


def test_geography_v3_has_complete_source_references_and_dem_member_proof() -> None:
    catalog = GeographyCatalog.model_validate(yaml.safe_load(GEOGRAPHY.read_text("utf-8")))
    manifest = json.loads(GEOGRAPHY_MANIFEST.read_text("utf-8"))
    assert catalog.schema_version == "delta-small-geography-v3"
    assert manifest["schema_version"] == "delta-small-geography-build-manifest-v3"
    assert catalog.build_manifest_sha256 == sha256_file(GEOGRAPHY_MANIFEST)
    source_by_id = {item.source_id: item for item in catalog.sources}
    raster = source_by_id["dwr-bay-delta-dem-v4.3-delta-10m-raster"]
    assert raster.archive_member == "dem_delta_10m_20250312.tif"
    assert raster.archive_member_sha256 == raster.sha256
    assert raster.archive_member_verification == "streamed-sha256-equals-extracted-raster"
    assert {item.elevation_summary.source_id for item in catalog.islands} == {raster.source_id}
    for source in catalog.sources:
        assert source.landing_page_locator
        assert source.media_type
        assert source.snapshot_format


def test_machine_refresh_validates_media_and_json_before_atomic_replace(tmp_path: Path) -> None:
    definition = _json_definition()
    destination = tmp_path / definition.file_name
    destination.write_text('{"preserved":true}\n', encoding="utf-8")

    def invalid_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html></html>")

    with (
        httpx.Client(transport=httpx.MockTransport(invalid_handler)) as client,
        pytest.raises(GeographyBuildSecurityError, match="media type"),
    ):
        _fetch_source(client, definition, tmp_path)
    assert destination.read_text("utf-8") == '{"preserved":true}\n'

    def valid_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json; charset=utf-8"},
            json={"ok": True},
        )

    with httpx.Client(transport=httpx.MockTransport(valid_handler)) as client:
        record = _fetch_source(client, definition, tmp_path)
    assert json.loads(destination.read_text("utf-8")) == {"ok": True}
    assert record.retrieval_locator == definition.retrieval_locator
    assert record.landing_page_locator == definition.landing_page_locator
    assert record.media_type == "application/json"


def test_nonmachine_source_refresh_fails_before_network_or_write(tmp_path: Path) -> None:
    definition = _json_definition(retrieval_locator=None)
    with (
        httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500))) as client,
        pytest.raises(GeographyBuildSecurityError, match="no validated machine-readable"),
    ):
        _fetch_source(client, definition, tmp_path)
    assert not (tmp_path / definition.file_name).exists()


def test_dem_member_verification_rejects_traversal_and_digest_mismatch(tmp_path: Path) -> None:
    raster = tmp_path / "dem.tif"
    raster.write_bytes(b"deterministic-raster")
    unsafe_archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(unsafe_archive, "w") as bundle:
        bundle.writestr("../escape", b"unsafe")
        bundle.writestr("dem.tif", raster.read_bytes())
    with pytest.raises(GeographyBuildSecurityError, match="unsafe DEM archive member"):
        _verify_archive_member(
            ArtifactLocator(tmp_path, Path("unsafe.zip"), 1_000_000, "DEM archive"),
            ArtifactLocator(tmp_path, Path("dem.tif"), 1_000_000, "DEM raster"),
            "dem.tif",
        )

    safe_archive = tmp_path / "safe.zip"
    with zipfile.ZipFile(safe_archive, "w") as bundle:
        bundle.writestr("dem.tif", b"different-raster")
    with pytest.raises(GeographyBuildSecurityError, match=r"size mismatch|digest mismatch"):
        _verify_archive_member(
            ArtifactLocator(tmp_path, Path("safe.zip"), 1_000_000, "DEM archive"),
            ArtifactLocator(tmp_path, Path("dem.tif"), 1_000_000, "DEM raster"),
            "dem.tif",
        )


def test_geography_outputs_reject_symlink_targets_and_parents(tmp_path: Path) -> None:
    target = tmp_path / "real.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(GeographyBuildSecurityError, match="symlink"):
        _safe_output_path(link)

    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(GeographyBuildSecurityError, match="parent must not be a symlink"):
        _safe_output_path(linked_parent / "output.json")


def test_replay_verification_rejects_symlink_artifact_root(tmp_path: Path) -> None:
    real_root = tmp_path / "real-artifacts"
    real_root.mkdir()
    linked_root = tmp_path / "linked-artifacts"
    linked_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(ArtifactMismatchError, match="root must not be a symlink"):
        verify_scenario_artifacts(linked_root)
