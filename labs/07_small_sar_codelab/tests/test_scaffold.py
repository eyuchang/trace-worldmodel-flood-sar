"""Guard the bounded size and separation of the student exercise."""

from __future__ import annotations

from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[1]


def test_starter_has_exactly_three_todos() -> None:
    starter = (LAB_ROOT / "starter" / "rescue_controller.py").read_text(encoding="utf-8")

    assert starter.count("TODO 1:") == 2
    assert starter.count("TODO 2:") == 2
    assert starter.count("TODO 3:") == 2
    assert starter.count("raise NotImplementedError") == 3


def test_solution_is_clearly_separate_and_complete() -> None:
    solution = (LAB_ROOT / "solution" / "rescue_controller.py").read_text(encoding="utf-8")

    assert "NotImplementedError" not in solution
    assert "TODO" not in solution
