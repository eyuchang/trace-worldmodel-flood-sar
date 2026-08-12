"""Prove a Reference delivery lineage excludes non-redistributable County bytes."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import cast

PROHIBITED_PATH = (
    "data/scenario/delta/reference/geography/sources/sacramento_county_andrus_brannan_v1.geojson"
)
PROHIBITED_BLOB_SHA256 = "af9c9cb9ea6a79ae569ee156c1e5753df468697fe14cf9a2e3f7f15a97eaaca0"


def _git(repo: Path, *arguments: str, text: bool = True) -> str | bytes:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=repo,
        check=True,
        capture_output=True,
        text=text,
        timeout=30,
    )
    return cast(str | bytes, completed.stdout)


def verify_delivery_history(repo: Path, revision: str) -> None:
    """Require every object reachable from a delivery revision to be license-safe."""

    paths = str(_git(repo, "log", "--format=", "--name-only", revision)).splitlines()
    if PROHIBITED_PATH in paths:
        raise ValueError("delivery history contains the prohibited County source path")
    objects = str(_git(repo, "rev-list", "--objects", revision)).splitlines()
    for line in objects:
        object_id, _, object_path = line.partition(" ")
        if object_path == PROHIBITED_PATH:
            raise ValueError("delivery object graph contains the prohibited County source path")
        if not object_path:
            continue
        object_type = str(_git(repo, "cat-file", "-t", object_id)).strip()
        if object_type != "blob":
            continue
        blob = _git(repo, "cat-file", "blob", object_id, text=False)
        if not isinstance(blob, bytes):
            raise TypeError("Git blob inspection unexpectedly returned text")
        if hashlib.sha256(blob).hexdigest() == PROHIBITED_BLOB_SHA256:
            raise ValueError("delivery object graph contains the prohibited County source blob")
