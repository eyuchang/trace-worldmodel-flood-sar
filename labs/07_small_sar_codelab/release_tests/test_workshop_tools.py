"""Checks for the one-command interface and minimal student archive."""

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
STUDENT_ROOT = LAB_ROOT / "student"
WORKSHOP = STUDENT_ROOT / "workshop.py"
BUNDLE_ROOT = "trace-small-sar-workshop/"


def _load_builder() -> ModuleType:
    path = LAB_ROOT / "tools" / "make_student_bundle.py"
    spec = importlib.util.spec_from_file_location("student_bundle_builder", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_workshop(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(WORKSHOP), *arguments],
        cwd=STUDENT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_no_argument_command_prints_the_complete_numbered_route() -> None:
    completed = _run_workshop()

    assert completed.returncode == 0
    for number in range(1, 8):
        assert f"{number}." in completed.stdout
    assert "exercise/rescue_controller.py" in completed.stdout


def test_check_succeeds_without_network() -> None:
    completed = _run_workshop("check")

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.count("[PASS]") == 5
    assert "READY: continue to Step 2" in completed.stdout
    assert "http://" not in completed.stdout
    assert "https://" not in completed.stdout


def test_student_bundle_is_deterministic_and_minimal(tmp_path: Path) -> None:
    builder = _load_builder()
    first = tmp_path / "student-one.zip"
    second = tmp_path / "student-two.zip"

    builder.build_bundle(first)
    builder.build_bundle(second)

    assert _sha256(first) == _sha256(second)
    with zipfile.ZipFile(first) as archive:
        names = set(archive.namelist())
    assert f"{BUNDLE_ROOT}README.md" in names
    assert f"{BUNDLE_ROOT}workshop.py" in names
    assert f"{BUNDLE_ROOT}exercise/rescue_controller.py" in names
    assert f"{BUNDLE_ROOT}tests/test_rescue_controller.py" in names
    assert f"{BUNDLE_ROOT}.workshop-manifest.json" in names
    assert len(names) == 11
    assert not any("solution" in name.lower() for name in names)
    assert not any("instructor" in name.lower() for name in names)
    assert not any("release" in name.lower() for name in names)
    assert not any("video" in name.lower() for name in names)
    assert not any(name.startswith("labs/") for name in names)


def test_student_bundle_refuses_overwrite(tmp_path: Path) -> None:
    builder = _load_builder()
    output = tmp_path / "student.zip"
    builder.build_bundle(output)

    with pytest.raises(ValueError, match="overwrite"):
        builder.build_bundle(output)
    assert not list(tmp_path.glob(".*.tmp"))


def test_student_bundle_cleans_temporary_file_when_publish_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = _load_builder()

    def fail_publish(_source: Path, _destination: Path) -> None:
        raise OSError("simulated publish failure")

    monkeypatch.setattr(builder.os, "link", fail_publish)
    with pytest.raises(OSError, match="simulated publish failure"):
        builder.build_bundle(tmp_path / "student.zip")

    assert list(tmp_path.iterdir()) == []
