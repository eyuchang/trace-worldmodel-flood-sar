"""Shared paths and fixtures for instructor/release-only checks."""

from __future__ import annotations

import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[1]
STUDENT_ROOT = LAB_ROOT / "student"
for path in (STUDENT_ROOT, LAB_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
