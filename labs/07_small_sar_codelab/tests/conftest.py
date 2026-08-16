"""Shared fixtures for the focused student-facing lab tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

LAB_ROOT = Path(__file__).resolve().parents[1]
if str(LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(LAB_ROOT))

import lab_runtime


@pytest.fixture(scope="session")
def controller_name() -> str:
    """Select the starter by default or the solution during instructor checks."""

    return os.environ.get("TRACE_SMALL_SAR_CONTROLLER", "starter")


@pytest.fixture(scope="session")
def controller(controller_name: str) -> ModuleType:
    """Load the selected lab controller."""

    return lab_runtime.load_controller(controller_name)


@pytest.fixture(scope="session")
def public_cases() -> dict[str, lab_runtime.PublicCase]:
    """Return the hash-checked public teaching cases."""

    return lab_runtime.build_cases()
