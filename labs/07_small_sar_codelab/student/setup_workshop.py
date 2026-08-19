"""Create the local Python environment used by the Flood Rescue Controller lab.

This setup tool deliberately installs nothing from the internet.  The workshop
uses only Python's standard library and the public teaching files included in
this folder.  Run it once after extracting the ZIP, then activate ``.venv`` as
shown in the README before using ``python workshop.py ...``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import venv
from pathlib import Path
from typing import Final

STUDENT_ROOT: Final = Path(__file__).resolve().parent
VENV_ROOT: Final = STUDENT_ROOT / ".venv"
MARKER: Final = VENV_ROOT / ".trace-small-sar-setup.json"
SUPPORTED_PYTHON_MIN: Final = (3, 11)
SUPPORTED_PYTHON_MAX: Final = (3, 14)


class SetupError(RuntimeError):
    """A short, student-actionable setup failure."""


def _supported_python() -> None:
    version = sys.version_info[:2]
    if SUPPORTED_PYTHON_MIN <= version <= SUPPORTED_PYTHON_MAX:
        return
    minimum = ".".join(str(value) for value in SUPPORTED_PYTHON_MIN)
    maximum = ".".join(str(value) for value in SUPPORTED_PYTHON_MAX)
    raise SetupError(f"Python {minimum} through {maximum} is required; found {version[0]}.{version[1]}.")


def _venv_python() -> Path:
    if os.name == "nt":
        return VENV_ROOT / "Scripts" / "python.exe"
    return VENV_ROOT / "bin" / "python"


def _ready_environment() -> bool:
    if not MARKER.is_file() or not _venv_python().is_file():
        return False
    try:
        marker = json.loads(MARKER.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(marker, dict):
        return False
    return marker == {
        "schema_version": "trace-small-sar-local-venv-v1",
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
    }


def _remove_broken_environment() -> None:
    resolved = VENV_ROOT.resolve()
    if VENV_ROOT.is_symlink() or resolved.name != ".venv" or resolved.parent != STUDENT_ROOT.resolve():
        raise SetupError("refusing to replace an unexpected virtual-environment path")
    shutil.rmtree(resolved)


def create_environment(*, repair: bool) -> bool:
    """Create one local environment, returning whether a new one was made."""

    _supported_python()
    if _ready_environment():
        return False
    if VENV_ROOT.exists() or VENV_ROOT.is_symlink():
        if not repair:
            raise SetupError(
                ".venv already exists but is not this workshop's environment. "
                "Run setup_workshop.py --repair only if you want to replace it."
            )
        _remove_broken_environment()
    try:
        venv.EnvBuilder(with_pip=False, symlinks=os.name != "nt").create(VENV_ROOT)
    except (OSError, ValueError) as exc:
        raise SetupError("Python could not create .venv. Ask an instructor for the first error line.") from exc
    MARKER.write_text(
        json.dumps(
            {
                "schema_version": "trace-small-sar-local-venv-v1",
                "python": f"{sys.version_info.major}.{sys.version_info.minor}",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return True


def _next_command() -> str:
    if os.name == "nt":
        return r".venv\Scripts\activate"
    return "source .venv/bin/activate"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repair", action="store_true", help="replace only a broken local .venv")
    args = parser.parse_args()
    try:
        created = create_environment(repair=args.repair)
    except SetupError as exc:
        print(f"SETUP STOP: {exc}", file=sys.stderr)
        return 2
    state = "created" if created else "already ready"
    print(f"SETUP READY: .venv {state}; no package or model download was needed.")
    print(f"Next: {_next_command()}")
    print("Then: python workshop.py check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
