from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from trace_reference.delivery_history import (
    PROHIBITED_PATH,
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
    with pytest.raises(ValueError, match="prohibited County source path"):
        verify_delivery_history(repo, "HEAD")
