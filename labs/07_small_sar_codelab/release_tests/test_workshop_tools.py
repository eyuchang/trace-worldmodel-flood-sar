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


def _load_demo_workspace_tool() -> ModuleType:
    path = LAB_ROOT / "instructor" / "tools" / "demo_workspace.py"
    spec = importlib.util.spec_from_file_location("instructor_demo_workspace", path)
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
    assert names == {
        f"{BUNDLE_ROOT}.gitignore",
        f"{BUNDLE_ROOT}README.md",
        f"{BUNDLE_ROOT}setup_workshop.py",
        f"{BUNDLE_ROOT}workshop.py",
        f"{BUNDLE_ROOT}exercise/__init__.py",
        f"{BUNDLE_ROOT}exercise/rescue_controller.py",
        f"{BUNDLE_ROOT}tests/test_rescue_controller.py",
        f"{BUNDLE_ROOT}_support/__init__.py",
        f"{BUNDLE_ROOT}_support/runtime.py",
        f"{BUNDLE_ROOT}_support/teaching_fixture.json",
        f"{BUNDLE_ROOT}_support/types.py",
        f"{BUNDLE_ROOT}.workshop-manifest.json",
    }
    assert not any("solution" in name.lower() for name in names)
    assert not any("instructor" in name.lower() for name in names)
    assert not any("release" in name.lower() for name in names)
    assert not any("video" in name.lower() for name in names)
    assert not any("viewer" in name.lower() for name in names)
    assert not any("cases.json" in name.lower() for name in names)
    assert not any(name.startswith("labs/") for name in names)


def test_extracted_bundle_sets_up_and_checks_with_only_its_own_python(tmp_path: Path) -> None:
    builder = _load_builder()
    archive_path = tmp_path / "student.zip"
    builder.build_bundle(archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(tmp_path)
    workspace = tmp_path / BUNDLE_ROOT.rstrip("/")

    setup = subprocess.run(
        [sys.executable, "setup_workshop.py"],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert setup.returncode == 0, setup.stderr
    assert "no package or model download was needed" in setup.stdout
    venv_python = workspace / ".venv" / (
        "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    )
    checked = subprocess.run(
        [str(venv_python), "workshop.py", "check"],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert checked.returncode == 0, checked.stderr
    assert checked.stdout.count("[PASS]") == 5
    assert "READY:" in checked.stdout


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


def test_instructor_reveal_uses_the_same_student_filename_and_commands(tmp_path: Path) -> None:
    demo_tool = _load_demo_workspace_tool()
    workspace = tmp_path / "instructor-demo"

    demo_tool.prepare(workspace)
    exercise = workspace / "exercise" / "rescue_controller.py"
    assert exercise.read_bytes() == (STUDENT_ROOT / "exercise" / "rescue_controller.py").read_bytes()
    assert not (workspace / "_support" / "cases.json").exists()
    with pytest.raises(demo_tool.DemoWorkspaceError, match="reveal TODO 1 first"):
        demo_tool.reveal(workspace, "2")

    for todo in ("1", "2", "3"):
        demo_tool.reveal(workspace, todo)
    source = exercise.read_text(encoding="utf-8")
    assert "TODO 1:" not in source
    assert "TODO 2:" not in source
    assert "TODO 3:" not in source

    completed = subprocess.run(
        [sys.executable, "workshop.py", "test", "all"],
        cwd=workspace,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Ran 12 tests" in completed.stderr
    assert "PASS: Run your controller" in completed.stdout


def test_instructor_reveal_refuses_an_ordinary_student_workspace() -> None:
    demo_tool = _load_demo_workspace_tool()

    with pytest.raises(demo_tool.DemoWorkspaceError, match="not a prepared instructor demo workspace"):
        demo_tool.reveal(STUDENT_ROOT, "1")
