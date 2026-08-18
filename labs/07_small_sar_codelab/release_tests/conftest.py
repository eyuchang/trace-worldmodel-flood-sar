"""Shared paths and fixtures for instructor/release-only checks."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

LAB_ROOT = Path(__file__).resolve().parents[1]
STUDENT_ROOT = LAB_ROOT / "student"
for path in (STUDENT_ROOT, LAB_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from _support import runtime


@pytest.fixture(scope="session")
def controller_name() -> str:
    """Release checks always exercise the separate instructor solution."""

    return "solution"


@pytest.fixture(scope="session")
def controller() -> ModuleType:
    """Load the instructor solution through the same runtime contract."""

    return runtime.load_controller("solution")


@pytest.fixture(scope="session")
def public_cases() -> dict[str, runtime.PublicCase]:
    """Return the hash-checked public teaching cases."""

    return runtime.build_cases()
