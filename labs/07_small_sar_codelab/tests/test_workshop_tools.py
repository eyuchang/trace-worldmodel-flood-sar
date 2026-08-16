"""Checks for offline setup and safe student handout creation."""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

LAB_ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str) -> ModuleType:
    path = LAB_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_preflight_succeeds_without_network() -> None:
    completed = subprocess.run(
        [sys.executable, str(LAB_ROOT / "scripts" / "preflight.py")],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.count("[PASS]") == 5
    assert "READY: no GPU, model checkpoint, or live data connection is needed." in completed.stdout
    assert "http://" not in completed.stdout
    assert "https://" not in completed.stdout


def test_student_bundle_is_deterministic_and_excludes_restricted_material(
    tmp_path: Path,
) -> None:
    builder = _load_script("make_student_bundle")
    first = tmp_path / "student-one.zip"
    second = tmp_path / "student-two.zip"

    builder.build_bundle(first)
    builder.build_bundle(second)

    assert _sha256(first) == _sha256(second)
    with zipfile.ZipFile(first) as archive:
        names = set(archive.namelist())
    assert "BUNDLE_MANIFEST.json" in names
    assert any(name.endswith("starter/rescue_controller.py") for name in names)
    assert not any("solution/" in name for name in names)
    assert not any("instructor" in name.lower() for name in names)
    assert not any("youtube/" in name for name in names)
    assert not any(name.startswith("data/") for name in names)


def test_student_bundle_refuses_overwrite(tmp_path: Path) -> None:
    builder = _load_script("make_student_bundle")
    output = tmp_path / "student.zip"
    builder.build_bundle(output)

    with pytest.raises(ValueError, match="overwrite"):
        builder.build_bundle(output)
    assert not list(tmp_path.glob(".*.tmp"))


def test_student_bundle_cleans_temporary_file_when_publish_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = _load_script("make_student_bundle")

    def fail_publish(_source: Path, _destination: Path) -> None:
        raise OSError("simulated publish failure")

    monkeypatch.setattr(builder.os, "link", fail_publish)
    with pytest.raises(OSError, match="simulated publish failure"):
        builder.build_bundle(tmp_path / "student.zip")

    assert list(tmp_path.iterdir()) == []
