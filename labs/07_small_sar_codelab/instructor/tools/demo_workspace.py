"""Prepare and reveal a safe instructor-only Flood Rescue Controller demo copy.

Students never receive this tool or the solution it reads.  It creates a fresh
copy of the student workspace with the same TODO file students see.  After a
pause, ``reveal`` replaces exactly one TODO function in that same filename, so
the following workshop commands are identical to student commands.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

LAB_ROOT: Final = Path(__file__).resolve().parents[2]
STUDENT_ROOT: Final = LAB_ROOT / "student"
SOLUTION_FILE: Final = LAB_ROOT / "instructor" / "solution" / "rescue_controller.py"
EXERCISE_RELATIVE: Final = Path("exercise") / "rescue_controller.py"
MARKER_NAME: Final = ".instructor-demo.json"
TODO_FUNCTIONS: Final = (
    "eligible_resources",
    "decide_rescue",
    "apply_visible_repair",
)


def _todo_marker(todo: int) -> str:
    """Return the starter-only marker that disappears when one TODO is revealed."""

    return f'raise NotImplementedError("TODO {todo}:'


class DemoWorkspaceError(RuntimeError):
    """Raised for an unsafe or inconsistent instructor demo operation."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _exercise_path(workspace: Path) -> Path:
    candidate = workspace / EXERCISE_RELATIVE
    if candidate.is_symlink() or not candidate.is_file():
        raise DemoWorkspaceError("the demo workspace has no regular exercise file")
    return candidate


def _marker_path(workspace: Path) -> Path:
    marker = workspace / MARKER_NAME
    if marker.is_symlink() or not marker.is_file():
        raise DemoWorkspaceError("this is not a prepared instructor demo workspace")
    return marker


def _marker(workspace: Path) -> dict[str, str]:
    try:
        value = json.loads(_marker_path(workspace).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DemoWorkspaceError("the instructor demo marker is unreadable") from exc
    if not isinstance(value, dict):
        raise DemoWorkspaceError("the instructor demo marker is malformed")
    required = {"schema_version", "starter_sha256"}
    if set(value) != required or value["schema_version"] != "trace-small-sar-instructor-demo-v1":
        raise DemoWorkspaceError("the instructor demo marker has an unsupported version")
    if not isinstance(value["starter_sha256"], str):
        raise DemoWorkspaceError("the instructor demo marker is malformed")
    return value


def _function_ranges(source: str) -> dict[str, tuple[int, int]]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise DemoWorkspaceError("the exercise file is not valid Python") from exc
    ranges: dict[str, tuple[int, int]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in TODO_FUNCTIONS:
            if node.end_lineno is None:
                raise DemoWorkspaceError(f"cannot locate the end of {node.name}")
            ranges[node.name] = (node.lineno, node.end_lineno)
    if tuple(ranges) != TODO_FUNCTIONS:
        raise DemoWorkspaceError("the exercise file no longer has the three expected TODO functions")
    return ranges


def _replace_function(source: str, solution: str, function_name: str) -> str:
    source_ranges = _function_ranges(source)
    solution_ranges = _function_ranges(solution)
    start, end = source_ranges[function_name]
    solution_start, solution_end = solution_ranges[function_name]
    source_lines = source.splitlines(keepends=True)
    solution_lines = solution.splitlines(keepends=True)
    replacement = solution_lines[solution_start - 1 : solution_end]
    return "".join((*source_lines[: start - 1], *replacement, *source_lines[end:]))


def _write_atomically(destination: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def prepare(workspace: Path) -> None:
    """Create one clean, non-overwriting instructor demo workspace."""

    destination = workspace.expanduser().resolve()
    if destination.exists() or destination.is_symlink():
        raise DemoWorkspaceError("the requested demo workspace already exists")
    if destination.parent.is_symlink() or not destination.parent.is_dir():
        raise DemoWorkspaceError("the demo workspace parent must be a regular existing directory")
    ignore = shutil.ignore_patterns(
        ".venv",
        ".workshop",
        "__pycache__",
        ".pytest_cache",
        "cases.json",
    )
    shutil.copytree(STUDENT_ROOT, destination, ignore=ignore)
    exercise = _exercise_path(destination)
    starter = STUDENT_ROOT / EXERCISE_RELATIVE
    if _sha256(exercise) != _sha256(starter):
        raise DemoWorkspaceError("the copied starter exercise does not match the student file")
    marker = {
        "schema_version": "trace-small-sar-instructor-demo-v1",
        "starter_sha256": _sha256(starter),
    }
    (destination / MARKER_NAME).write_text(
        json.dumps(marker, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def reveal(workspace: Path, todo: str) -> None:
    """Reveal one solution function in the demo copy's real student filename."""

    if todo not in {"1", "2", "3"}:
        raise DemoWorkspaceError("TODO must be 1, 2, or 3")
    resolved = workspace.expanduser().resolve()
    marker = _marker(resolved)
    exercise = _exercise_path(resolved)
    source = exercise.read_text(encoding="utf-8")
    solution = SOLUTION_FILE.read_text(encoding="utf-8")
    target = TODO_FUNCTIONS[int(todo) - 1]
    if _todo_marker(int(todo)) not in source:
        raise DemoWorkspaceError(f"TODO {todo} is already revealed or has been edited")
    if "NotImplementedError" not in source:
        raise DemoWorkspaceError("the demo exercise no longer contains the expected starter TODOs")
    for earlier in range(1, int(todo)):
        if _todo_marker(earlier) in source:
            raise DemoWorkspaceError(f"reveal TODO {earlier} first")
    updated = _replace_function(source, solution, target)
    if updated == source or _todo_marker(int(todo)) in updated:
        raise DemoWorkspaceError(f"could not reveal TODO {todo}")
    _write_atomically(exercise, updated)
    _marker_path(resolved).write_text(
        json.dumps(marker, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def reset(workspace: Path) -> None:
    """Restore the original student TODO file in a prepared demo workspace."""

    resolved = workspace.expanduser().resolve()
    marker = _marker(resolved)
    starter = STUDENT_ROOT / EXERCISE_RELATIVE
    if _sha256(starter) != marker["starter_sha256"]:
        raise DemoWorkspaceError("the source starter file changed; refusing to reset the demo copy")
    _write_atomically(_exercise_path(resolved), starter.read_text(encoding="utf-8"))


def status(workspace: Path) -> str:
    """Return a concise state report for the three reveal steps."""

    _marker(workspace.expanduser().resolve())
    source = _exercise_path(workspace.expanduser().resolve()).read_text(encoding="utf-8")
    states = [
        f"TODO {index}: {'not yet revealed' if _todo_marker(index) in source else 'revealed'}"
        for index in range(1, 4)
    ]
    return "\n".join(states)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "status", "reset"):
        command = commands.add_parser(name)
        command.add_argument("--workspace", required=True, type=Path)
    reveal_command = commands.add_parser("reveal")
    reveal_command.add_argument("--workspace", required=True, type=Path)
    reveal_command.add_argument("--todo", required=True, choices=("1", "2", "3"))
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            prepare(args.workspace)
            print(f"Instructor demo ready: {args.workspace}")
        elif args.command == "reveal":
            reveal(args.workspace, args.todo)
            print(f"Revealed TODO {args.todo} in exercise/rescue_controller.py")
        elif args.command == "reset":
            reset(args.workspace)
            print("Restored the three student TODOs in exercise/rescue_controller.py")
        else:
            print(status(args.workspace))
    except (DemoWorkspaceError, OSError) as exc:
        print(f"DEMO STOP: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
