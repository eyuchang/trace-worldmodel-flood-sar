"""Prove a Reference delivery lineage excludes non-redistributable County bytes."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import cast


@dataclass(frozen=True)
class ProhibitedDeliveryInventory:
    """Known raw and derived County artifacts that cannot enter public history."""

    exact_paths: tuple[str, ...]
    path_prefixes: tuple[str, ...]
    blob_sha256: tuple[str, ...]


PROHIBITED_REFERENCE_SOURCE_PATH = (
    "data/scenario/delta/reference/geography/sources/sacramento_county_andrus_brannan_v1.geojson"
)
PROHIBITED_SMALL_SOURCE_PATH = (
    "data/scenario/delta/geography/sources/sacramento_county_drainage_districts.geojson"
)
PROHIBITED_PATH = PROHIBITED_REFERENCE_SOURCE_PATH  # one-release compatibility alias
PROHIBITED_BLOB_SHA256 = "af9c9cb9ea6a79ae569ee156c1e5753df468697fe14cf9a2e3f7f15a97eaaca0"  # one-release compatibility alias

DEFAULT_PROHIBITED_INVENTORY = ProhibitedDeliveryInventory(
    exact_paths=(
        PROHIBITED_REFERENCE_SOURCE_PATH,
        PROHIBITED_SMALL_SOURCE_PATH,
        "data/scenario/delta/geography/build_manifest_v2.json",
        "data/scenario/delta/geography/build_manifest_v3.json",
        "data/scenario/delta/geography/delta_small_geography_v2.yaml",
        "data/scenario/delta/geography/delta_small_geography_v3.yaml",
        "data/scenario/delta/provenance/v8_scientific_input_manifest_v1.json",
        "data/scenario/delta/provenance/v8_scientific_input_manifest_v2.json",
        "data/scenario/delta/provenance/v8_scientific_input_manifest_v3.json",
        "data/scenario/delta/reference/geography/derived/reference_geography_build_manifest_v1.json",
        "data/scenario/delta/reference/geography/derived/reference_geography_build_manifest_v2.json",
        "data/scenario/delta/reference/geography/derived/reference_geography_catalog_v1.json",
        "data/scenario/delta/reference/geography/derived/reference_geography_catalog_v2.json",
    ),
    path_prefixes=(
        "data/scenario/delta/reference/wf_dfld_01_small_book_v1/",
        "data/scenario/delta/reference/wf_dfld_01_small_book_v2/",
        "data/scenario/delta/reference/wf_dfld_01_small_book_v6/",
        "docs/delta/figures/wf_dfld_01_small/",
        "docs/delta/figures/wf_dfld_01_small_v2/",
        "docs/delta/figures/wf_dfld_01_small_v6/",
    ),
    blob_sha256=(
        "af9c9cb9ea6a79ae569ee156c1e5753df468697fe14cf9a2e3f7f15a97eaaca0",
        "803a6c1200a2cdb54a0deec87b6627f7bc4edc58eee74a5b3a834cb176514710",
        "be3e57790e0b5550a95c8ce6517e86bb8db2668ada50f6894f117bf3bfae7977",
        "8d13e68bc1cd319d16854d19f147f7b40b960e548112f1b34612caed437b24b4",
        "dcf06ad149efdd0c606b53cbcc4c1fdc0dfa028c9ddb3018b6bcec578ec12540",
        "344b01a9bbe122712085225ee39ab6d7ffc47e964a98b094433375f6be9fdc32",
        "c66b02c7e6eb38f7110c3bd2cf48c01237f3dc0bb3a0974573de8da0e7abe88b",
        "8b1ba5e566ae5c79329c89aa710e1cd4c5ea5933731dd44c4d718b0162348db1",
        "28eb727ba05de4f1f6139eee30daed875eb2d6e1cb841d4cc892a47e4e66f57c",
        "6121aea138d7a9295a8d33ac83175ec98cd81f2d9f2aa46bf148b576dd13fddf",
        "5b3e10ff69f070fe674bd47c75d78cba8af14eb5ddb340233dee1c1dd41e8c6b",
        "03db933c44227711dedca096745ae80e8a5190ad9d7f9439207e0eb70bad86e5",
        "dcc26dbfb1df7605b333a5d942c1cee421cf02fbb9bcf30a3de4de45ad90d641",
        "bd24a3ac7cc7b835270279b3fe8b5e40a39688e035e5999047c365415e1f99fc",
    ),
)


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


def _prohibited_path(path: str, inventory: ProhibitedDeliveryInventory) -> bool:
    return path in inventory.exact_paths or any(
        path.startswith(prefix) for prefix in inventory.path_prefixes
    )


def verify_delivery_history(
    repo: Path,
    revision: str,
    *,
    inventory: ProhibitedDeliveryInventory = DEFAULT_PROHIBITED_INVENTORY,
) -> None:
    """Require every object reachable from a delivery revision to be license-safe."""

    paths = str(_git(repo, "log", "--format=", "--name-only", revision)).splitlines()
    if any(_prohibited_path(path, inventory) for path in paths):
        raise ValueError("delivery history contains a prohibited County-derived path")
    objects = str(_git(repo, "rev-list", "--objects", revision)).splitlines()
    for line in objects:
        object_id, _, object_path = line.partition(" ")
        if _prohibited_path(object_path, inventory):
            raise ValueError("delivery object graph contains a prohibited County-derived path")
        if not object_path:
            continue
        object_type = str(_git(repo, "cat-file", "-t", object_id)).strip()
        if object_type != "blob":
            continue
        blob = _git(repo, "cat-file", "blob", object_id, text=False)
        if not isinstance(blob, bytes):
            raise TypeError("Git blob inspection unexpectedly returned text")
        if hashlib.sha256(blob).hexdigest() in inventory.blob_sha256:
            raise ValueError("delivery object graph contains a prohibited County-derived blob")
