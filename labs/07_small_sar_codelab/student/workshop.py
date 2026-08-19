"""One command surface for the Flood Rescue Controller student workshop."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from _support import runtime

STUDENT_ROOT = Path(__file__).resolve().parent
WORK_ROOT = STUDENT_ROOT / ".workshop"
TEST_FILE = STUDENT_ROOT / "tests" / "test_rescue_controller.py"
SUPPORTED_PYTHON_MIN = (3, 11)
SUPPORTED_PYTHON_MAX = (3, 14)

MENU = """Flood Rescue Controller Workshop

1. Check setup             python workshop.py check
2. Run the scenario        python workshop.py scenario
3. See four decisions      python workshop.py walkthrough
4. Test your TODOs         python workshop.py test 1
5. Run your controller     python workshop.py run
6. Change capacity         python workshop.py what-if
7. Replay saved history    python workshop.py replay

Open exercise/rescue_controller.py when Step 4 tells you to start coding.
"""


class WorkshopError(RuntimeError):
    """A short, actionable workshop failure."""


def _new_output(name: str) -> Path:
    WORK_ROOT.mkdir(exist_ok=True)
    output = WORK_ROOT / name
    if output.exists():
        raise WorkshopError(
            f"{name} already exists. Continue to the next step, or run "
            "'python workshop.py reset' to start over."
        )
    return output


def _check_python() -> tuple[str, str]:
    version = sys.version_info[:2]
    if not SUPPORTED_PYTHON_MIN <= version <= SUPPORTED_PYTHON_MAX:
        minimum = ".".join(str(value) for value in SUPPORTED_PYTHON_MIN)
        maximum = ".".join(str(value) for value in SUPPORTED_PYTHON_MAX)
        raise WorkshopError(f"Python {minimum} through {maximum} is required.")
    return "python", f"Python {version[0]}.{version[1]} is ready"


def _check_files() -> tuple[str, str]:
    required = (
        STUDENT_ROOT / "README.md",
        STUDENT_ROOT / "setup_workshop.py",
        STUDENT_ROOT / "exercise" / "rescue_controller.py",
        TEST_FILE,
        STUDENT_ROOT / "_support" / "teaching_fixture.json",
    )
    if not all(path.is_file() for path in required):
        raise WorkshopError("The workshop folder is incomplete. Ask for a fresh ZIP.")
    return "workshop-files", "guide, setup tool, exercise, tests, and teaching data found"


def _check_teaching_data() -> tuple[str, str]:
    cases = runtime.build_cases()
    summary = runtime.scenario_summary()
    if tuple(cases) != ("allocation", "evidence_hold", "capacity_refusal", "visible_repair"):
        raise WorkshopError("The four teaching cases are not available.")
    if summary != {"allocated": 1, "refused": 2, "repaired": 1}:
        raise WorkshopError("The bundled scenario summary is not the expected teaching case.")
    return "teaching-data", "four public teaching cases are ready"


def _check_tests() -> tuple[str, str]:
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except OSError as exc:
        raise WorkshopError("Python could not start its built-in test runner.") from exc
    if completed.returncode != 0:
        raise WorkshopError("Python's built-in test runner is unavailable.")
    return "tests", "Python's built-in test runner is ready"


def _check_workspace() -> tuple[str, str]:
    WORK_ROOT.mkdir(exist_ok=True)
    probe = WORK_ROOT / ".write-check"
    probe.write_text("ready\n", encoding="utf-8")
    probe.unlink()
    return "workspace", "practice output is writable"


def check_setup() -> None:
    checks = (
        _check_python(),
        _check_files(),
        _check_teaching_data(),
        _check_tests(),
        _check_workspace(),
    )
    for label, detail in checks:
        print(f"[PASS] {label}: {detail}")
    print("READY: continue to Step 2 with 'python workshop.py scenario'.")


def run_scenario() -> None:
    output = _new_output("run")
    runtime.write_scenario(output)
    summary = runtime.scenario_summary()
    print(
        "Scenario complete: "
        f"{summary['allocated']} allocated, {summary['refused']} refused, "
        f"{summary['repaired']} repaired."
    )
    print("Saved decision path:")
    print("  call -> evidence -> TRACE record -> controller decision -> commitment -> outcome")
    print(f"Practice output: {output}")
    print("Next: python workshop.py walkthrough")


def show_walkthrough() -> None:
    print(runtime.format_report(runtime.run_lab("book", "all")))
    print("\nNext: open exercise/rescue_controller.py and complete TODO 1.")


def run_tests(selection: str) -> None:
    completed = subprocess.run(
        [sys.executable, str(TEST_FILE), "--todo", selection],
        cwd=STUDENT_ROOT,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise WorkshopError(f"TODO {selection} still needs work. Read the first failure above.")
    next_step = {
        "1": "Complete TODO 2, then run: python workshop.py test 2",
        "2": "Complete TODO 3, then run: python workshop.py test 3",
        "3": "Run every check: python workshop.py test all",
        "all": "Run your controller: python workshop.py run",
    }[selection]
    print(f"PASS: {next_step}")


def run_controller() -> None:
    print(runtime.format_report(runtime.run_lab("exercise", "all")))
    print("\nNext: python workshop.py what-if")


def run_what_if() -> None:
    print("WHAT IF 1: all welfare-check units are busy?")
    first = runtime.run_lab("exercise", "allocation", "no-capacity")
    print(runtime.format_report(first))
    print("\nWHAT IF 2: a medical-response unit becomes available?")
    second = runtime.run_lab("exercise", "capacity_refusal", "restore-capacity")
    print(runtime.format_report(second))
    print("\nNotice: capacity changed the action while TRACE stayed CLEAR.")
    print("Next: python workshop.py replay")


def replay_scenario() -> None:
    original = WORK_ROOT / "run"
    if not original.is_dir():
        raise WorkshopError("Run Step 2 first: python workshop.py scenario")
    replay = _new_output("replay")
    runtime.write_scenario(replay)
    if not runtime.scenario_directories_match(original, replay):
        raise WorkshopError("The saved scenario and replay did not match exactly.")
    print("Replay: byte-identical.")
    print("COMPLETE: CLEAR permits a resource check; allocation also requires capacity.")


def reset_workshop() -> None:
    resolved = WORK_ROOT.resolve()
    if resolved.name != ".workshop" or resolved.parent != STUDENT_ROOT.resolve():
        raise WorkshopError("Refusing to reset an unexpected path.")
    if not resolved.exists():
        print("Nothing to reset.")
        return
    shutil.rmtree(resolved)
    print("Practice outputs removed. Your exercise code was kept.")
    print("Restart with: python workshop.py check")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command")
    for name in ("check", "scenario", "walkthrough", "run", "what-if", "replay", "reset"):
        commands.add_parser(name)
    tests = commands.add_parser("test")
    tests.add_argument("selection", choices=("1", "2", "3", "all"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command is None:
        print(MENU)
        return 0
    actions: dict[str, Callable[[], None]] = {
        "check": check_setup,
        "scenario": run_scenario,
        "walkthrough": show_walkthrough,
        "run": run_controller,
        "what-if": run_what_if,
        "replay": replay_scenario,
        "reset": reset_workshop,
    }
    try:
        if args.command == "test":
            run_tests(args.selection)
        else:
            actions[args.command]()
    except (OSError, WorkshopError, ValueError, runtime.LabDataError) as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
