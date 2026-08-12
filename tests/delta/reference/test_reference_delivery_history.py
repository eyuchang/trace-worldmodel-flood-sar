from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from trace_reference.delivery_history import (
    DEFAULT_PROHIBITED_INVENTORY,
    PROHIBITED_PATH,
    PROHIBITED_SMALL_SOURCE_PATH,
    ProhibitedDeliveryInventory,
    verify_delivery_history,
)


def _git(repo: Path, *arguments: str) -> None:
    subprocess.run(("git", *arguments), cwd=repo, check=True, capture_output=True, timeout=10)


def _repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.email", "reference-fixture@example.invalid")
    _git(repo, "config", "user.name", "Reference Fixture")
    (repo / "safe.txt").write_text("safe\n", encoding="utf-8")
    _git(repo, "add", "safe.txt")
    _git(repo, "commit", "--quiet", "-m", "safe")
    return repo


def test_delivery_history_accepts_safe_lineage(tmp_path: Path) -> None:
    verify_delivery_history(_repository(tmp_path), "HEAD")


def test_delivery_history_rejects_prohibited_path_even_after_deletion(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    target = repo / PROHIBITED_PATH
    target.parent.mkdir(parents=True)
    target.write_text("restricted fixture\n", encoding="utf-8")
    _git(repo, "add", PROHIBITED_PATH)
    _git(repo, "commit", "--quiet", "-m", "unsafe")
    target.unlink()
    _git(repo, "add", "-u")
    _git(repo, "commit", "--quiet", "-m", "delete")
    with pytest.raises(ValueError, match="prohibited County-derived path"):
        verify_delivery_history(repo, "HEAD")


def test_delivery_history_rejects_delivered_small_county_path(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    target = repo / PROHIBITED_SMALL_SOURCE_PATH
    target.parent.mkdir(parents=True)
    target.write_text("Small County fixture\n", encoding="utf-8")
    _git(repo, "add", PROHIBITED_SMALL_SOURCE_PATH)
    _git(repo, "commit", "--quiet", "-m", "unsafe Small source")
    with pytest.raises(ValueError, match="prohibited County-derived path"):
        verify_delivery_history(repo, "HEAD")


def test_delivery_history_rejects_renamed_derived_blob_by_digest(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    derived_bytes = b"synthetic County-derived geometry fixture\n"
    (repo / "renamed-safe-looking.json").write_bytes(derived_bytes)
    _git(repo, "add", "renamed-safe-looking.json")
    _git(repo, "commit", "--quiet", "-m", "renamed unsafe derived file")
    inventory = ProhibitedDeliveryInventory(
        exact_paths=(),
        path_prefixes=(),
        blob_sha256=(hashlib.sha256(derived_bytes).hexdigest(),),
    )
    with pytest.raises(ValueError, match="prohibited County-derived blob"):
        verify_delivery_history(repo, "HEAD", inventory=inventory)


def test_default_inventory_covers_small_and_reference_raw_and_derived_evidence() -> None:
    assert PROHIBITED_PATH in DEFAULT_PROHIBITED_INVENTORY.exact_paths
    assert PROHIBITED_SMALL_SOURCE_PATH in DEFAULT_PROHIBITED_INVENTORY.exact_paths
    assert "803a6c1200a2cdb54a0deec87b6627f7bc4edc58eee74a5b3a834cb176514710" in (
        DEFAULT_PROHIBITED_INVENTORY.blob_sha256
    )
    assert any("small_book" in prefix for prefix in DEFAULT_PROHIBITED_INVENTORY.path_prefixes)
    for digest in (
        "24dea31e8aee2337802c1f16477906c640d34e7626e92113751e329d13605915",
        "93de7a385e4b3838cb70991db9eb56446579e16125ea5050c8b5c1918bb3534e",
        "2254e6296ec0b24d10d91e722606e321da318dbc0e7b2d86a18a32645a7fdb8a",
    ):
        assert digest in DEFAULT_PROHIBITED_INVENTORY.blob_sha256


def test_delivery_history_rejects_renamed_frozen_small_manifest(tmp_path: Path) -> None:
    repo = _repository(tmp_path)
    source = (
        Path(__file__).resolve().parents[3]
        / "data/scenario/delta/provenance/v8_scientific_input_manifest_v3.json"
    )
    (repo / "renamed-frozen-evidence.json").write_bytes(source.read_bytes())
    _git(repo, "add", "renamed-frozen-evidence.json")
    _git(repo, "commit", "--quiet", "-m", "rename frozen Small manifest")
    with pytest.raises(ValueError, match="prohibited County-derived blob"):
        verify_delivery_history(repo, "HEAD")
