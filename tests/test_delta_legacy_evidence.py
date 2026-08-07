from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data/scenario/delta/legacy_evidence_sha256_v1.json"


def _evidence_digest(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
        return digest.hexdigest()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(item.read_bytes()).digest())
    return digest.hexdigest()


def test_inherited_delta_evidence_is_byte_immutable() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert registry["schema_version"] == "delta-legacy-evidence-integrity-v1"
    for relative_path, expected in registry["entries"].items():
        path = ROOT / relative_path
        assert path.exists(), relative_path
        assert _evidence_digest(path) == expected, relative_path
