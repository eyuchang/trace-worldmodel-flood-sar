"""One command surface for the Flood Rescue Controller workshop."""

from __future__ import annotations

import argparse
import importlib
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

STUDENT_ROOT = Path(__file__).resolve().parent
WORK_ROOT = STUDENT_ROOT / ".workshop"
TEST_FILE = STUDENT_ROOT / "tests" / "test_rescue_controller.py"

MENU = """Flood Rescue Controller Workshop

1. Check setup             python workshop.py check
2. Run the scenario        python workshop.py scenario
3. See four decisions      python workshop.py walkthrough
4. Test your TODOs         python workshop.py test 1
5. Run your controller     python workshop.py run
6. Change capacity         python workshop.py what-if
7. Replay and explain      python workshop.py replay

Open exercise/rescue_controller.py when Step 4 tells you to start coding.
"""


class WorkshopError(RuntimeError):
    """A short, actionable workshop failure."""


def _runtime() -> ModuleType:
    try:
        return importlib.import_module("_support.runtime")
    except (ImportError, RuntimeError) as exc:
        raise WorkshopError(str(exc)) from exc


def _run_command(arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(arguments),
        cwd=STUDENT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise WorkshopError(detail or "the workshop command did not complete")
    return completed


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
    version = sys.version_info
    if (version.major, version.minor) not in {(3, 11), (3, 12)}:
        raise WorkshopError("Python 3.11 or 3.12 is required on the prepared machine.")
    return "python", f"Python {version.major}.{version.minor} is ready"


def _check_files() -> tuple[str, str]:
    required = (
        STUDENT_ROOT / "README.md",
        STUDENT_ROOT / "exercise" / "rescue_controller.py",
        TEST_FILE,
        STUDENT_ROOT / "_support" / "cases.json",
    )
    if not all(path.is_file() for path in required):
        raise WorkshopError("The workshop folder is incomplete. Ask for a fresh copy.")
    return "workshop-files", "guide, exercise, tests, and examples found"


def _check_packages() -> tuple[str, str]:
    for package in ("pydantic", "pytest", "trace_jepa"):
        importlib.import_module(package)
    return "packages", "required Python packages are available"


def _check_examples() -> tuple[str, str]:
    runtime = _runtime()
    cases = runtime.build_cases()
    if set(cases) != {"allocation", "evidence_hold", "capacity_refusal", "visible_repair"}:
        raise WorkshopError("The four supplied rescue examples are not available.")
    return "examples", "four rescue examples are ready"


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
        _check_packages(),
        _check_examples(),
        _check_workspace(),
    )

    for label, detail in checks:
        print(f"[PASS] {label}: {detail}")
    print("READY: continue to Step 2 with 'python workshop.py scenario'.")


def run_scenario() -> None:
    _runtime()  # Confirm that the prepared TRACE installation is available.
    output = _new_output("run")
    _run_command(
        (
            sys.executable,
            "-m",
            "trace_jepa.scenario.delta.cli",
            "run",
            "--output",
            str(output),
        )
    )
    expected = (
        "calls.json",
        "evidence_ledger.json",
        "trace_records.json",
        "controller_decisions.json",
        "commitments.json",
        "outcomes.json",
    )
    missing = [name for name in expected if not (output / name).is_file()]
    if missing:
        raise WorkshopError(f"The scenario did not save the expected file: {missing[0]}")
    print("Scenario complete: 8 allocated, 12 refused, 8 repaired.")
    print("Saved decision path:")
    print("  call -> evidence -> TRACE record -> controller decision -> commitment -> outcome")
    print(f"Practice output: {output}")
    print("Next: python workshop.py walkthrough")


def show_walkthrough() -> None:
    runtime = _runtime()
    report = runtime.run_lab("book", "all")
    print(runtime.format_report(report))
    print("\nNext: open exercise/rescue_controller.py and complete TODO 1.")


def run_tests(selection: str) -> None:
    expressions = {
        "1": "eligible_resources",
        "2": "clear_plus_capacity or hold_refuses or clear_without_capacity or mismatched",
        "3": "visible_repair or repair_requires",
        "all": "",
    }
    expression = expressions[selection]
    command = [sys.executable, "-m", "pytest", "-q", str(TEST_FILE)]
    if expression:
        command.extend(("-k", expression))
    completed = subprocess.run(command, cwd=STUDENT_ROOT, timeout=30, check=False)
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
    runtime = _runtime()
    report = runtime.run_lab("exercise", "all")
    print(runtime.format_report(report))
    print("\nNext: python workshop.py what-if")


def run_what_if() -> None:
    runtime = _runtime()
    print("WHAT IF 1: all welfare-check units are busy?")
    first = runtime.run_lab("exercise", "allocation", "no-capacity")
    print(runtime.format_report(first))
    print("\nWHAT IF 2: a medical-response unit becomes available?")
    second = runtime.run_lab("exercise", "capacity_refusal", "restore-capacity")
    print(runtime.format_report(second))
    print("\nNotice: capacity changed the action while TRACE stayed CLEAR.")
    print("Next: python workshop.py replay")


def _replay(reference: Path, output_name: str, validation_report: Path | None = None) -> None:
    output = _new_output(output_name)
    command = [
        sys.executable,
        "-m",
        "trace_jepa.scenario.delta.cli",
        "replay",
        "--reference",
        str(reference),
        "--output",
        str(output),
    ]
    if validation_report is not None:
        command.extend(("--validation-report", str(validation_report)))
    _run_command(command)


def replay_scenario() -> None:
    runtime = _runtime()
    fresh = WORK_ROOT / "run"
    if not fresh.is_dir():
        raise WorkshopError("Run Step 2 first: python workshop.py scenario")
    _replay(fresh, "replay")

    repo = runtime.REPO_ROOT
    saved = repo / "data/scenario/delta/reference/wf_dfld_01_small_book_v6"
    report = repo / "docs/delta/validation/WF_DFLD_01_SMALL_VALIDATION_V6.json"
    _replay(saved, "saved-class-replay", report)
    print("Fresh replay: byte-identical.")
    print("Saved class replay: byte-identical.")
    print("COMPLETE: explain why CLEAR is not the same as allocation.")


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
    actions = {
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
    except (OSError, WorkshopError, ValueError) as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
