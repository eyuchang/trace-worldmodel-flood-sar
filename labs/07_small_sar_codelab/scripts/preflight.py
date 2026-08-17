"""Fast, offline readiness check for the TRACE Small SAR code lab."""

from __future__ import annotations

import importlib
import sys
import tempfile
from pathlib import Path
from typing import Final

LAB_ROOT: Final = Path(__file__).resolve().parents[1]
REPO_ROOT: Final = LAB_ROOT.parents[1]
if str(LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(LAB_ROOT))

import lab_runtime


class PreflightFailure(RuntimeError):
    """A concise setup problem that the student can act on."""


def _check_python() -> str:
    version = sys.version_info[:2]
    if version not in {(3, 10), (3, 11), (3, 12)}:
        raise PreflightFailure(
            "use Python 3.11 (preferred) or the tested Python 3.10/3.12 contingency"
        )
    suffix = "preferred workshop version" if version == (3, 11) else "tested contingency"
    return f"Python {version[0]}.{version[1]} ({suffix})"


def _check_checkout() -> str:
    expected = {
        REPO_ROOT / "pyproject.toml",
        REPO_ROOT / "requirements-delta-python311.lock",
        LAB_ROOT / "starter" / "rescue_controller.py",
        LAB_ROOT / "fixtures" / "public_case_manifest.json",
    }
    missing = sorted(str(path.relative_to(REPO_ROOT)) for path in expected if not path.is_file())
    if missing:
        raise PreflightFailure("missing checkout files: " + ", ".join(missing))
    return "starter code and workshop data found"


def _check_dependencies() -> str:
    required = ("numpy", "pydantic", "yaml", "rasterio", "pyproj", "shapely")
    missing: list[str] = []
    for module_name in required:
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing.append(module_name)
    if missing:
        raise PreflightFailure(
            "missing dependencies: "
            + ", ".join(missing)
            + "; reinstall requirements-delta-python311.lock"
        )
    return "required Python packages are available"


def _check_public_data() -> str:
    cases = lab_runtime.build_cases()
    if set(cases) != {"allocation", "evidence_hold", "capacity_refusal", "visible_repair"}:
        raise PreflightFailure("the four rescue examples are incomplete")
    return "four rescue examples are ready"


def _check_temporary_output() -> str:
    with tempfile.TemporaryDirectory(prefix="trace-small-sar-preflight-") as directory:
        path = Path(directory) / "write-check.txt"
        path.write_text("ok\n", encoding="utf-8")
        if path.read_text(encoding="utf-8") != "ok\n":
            raise PreflightFailure("temporary output round trip failed")
    return "private practice output is writable"


def run_preflight() -> list[tuple[str, str]]:
    """Run checks without network access or scientific artifact writes."""

    return [
        ("python", _check_python()),
        ("lab-files", _check_checkout()),
        ("packages", _check_dependencies()),
        ("examples", _check_public_data()),
        ("scratch-space", _check_temporary_output()),
    ]


def main() -> int:
    try:
        results = run_preflight()
    except (lab_runtime.LabDataError, PreflightFailure) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2
    for name, detail in results:
        print(f"[PASS] {name}: {detail}")
    print("READY: no GPU, model checkpoint, or live data connection is needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
