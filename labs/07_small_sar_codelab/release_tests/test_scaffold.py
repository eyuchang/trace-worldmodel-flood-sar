"""Guard the bounded size and separation of the student exercise."""

from __future__ import annotations

import ast
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[1]


def test_exercise_has_exactly_three_todos_and_one_edit_target() -> None:
    exercise = (LAB_ROOT / "student" / "exercise" / "rescue_controller.py").read_text(
        encoding="utf-8"
    )

    assert exercise.count("# TODO 1") == 1
    assert exercise.count("# TODO 2") == 1
    assert exercise.count("# TODO 3") == 1
    assert exercise.count("raise NotImplementedError") == 3
    assert len(list((LAB_ROOT / "student" / "exercise").glob("*.py"))) == 2


def test_solution_is_clearly_separate_and_complete() -> None:
    solution = (LAB_ROOT / "instructor" / "solution" / "rescue_controller.py").read_text(
        encoding="utf-8"
    )

    assert "NotImplementedError" not in solution
    assert "TODO" not in solution


def test_exercise_scaffold_is_explicit_and_uses_a_provided_helper() -> None:
    exercise = (LAB_ROOT / "student" / "exercise" / "rescue_controller.py").read_text(
        encoding="utf-8"
    )

    assert "def _decision_from_trace" in exercise
    assert "Build a collection containing only resources" in exercise
    assert "Return () when none qualify" in exercise
    assert "both call_id and belief_cluster_id match" in exercise
    assert "Raise ValueError unless" in exercise
    assert "Compare the update with history[-1]" in exercise
    assert "Use _decision_from_trace(...)" in exercise


def test_student_tests_cover_each_documented_error_condition() -> None:
    tests = (LAB_ROOT / "student" / "tests" / "test_rescue_controller.py").read_text(
        encoding="utf-8"
    )

    expected_tests = (
        "test_todo_2_rejects_a_mismatched_call",
        "test_todo_2_rejects_a_mismatched_situation",
        "test_todo_3_rejects_empty_history",
        "test_todo_3_rejects_a_different_situation",
        "test_todo_3_rejects_a_different_trace_record",
        "test_todo_3_requires_a_later_version",
        "test_todo_3_requires_visible_basis",
    )
    for name in expected_tests:
        assert f"def {name}(" in tests
    assert tests.count("with self.assertRaises(ValueError):") == len(expected_tests)


def test_student_visible_functions_remain_small_and_single_purpose() -> None:
    paths = (
        LAB_ROOT / "student" / "workshop.py",
        LAB_ROOT / "student" / "_support" / "runtime.py",
        LAB_ROOT / "student" / "exercise" / "rescue_controller.py",
    )
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.end_lineno is not None
                length = node.end_lineno - node.lineno + 1
                assert length <= 65, f"{path.name}:{node.name} is {length} lines"
