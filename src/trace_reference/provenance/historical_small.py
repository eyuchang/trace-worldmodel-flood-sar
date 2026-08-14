"""Integrity verification for the immutable Small scientific-input receipt."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path

from trace_jepa.scenario.delta.provenance.scientific_inputs import (
    ScientificInputError,
    ScientificInputManifest,
    ScientificInputMember,
)
from trace_jepa.support import ArtifactLocator

_MAX_HISTORICAL_SMALL_MANIFEST_BYTES = 2_000_000


def _aggregate_digest(members: Iterable[ScientificInputMember]) -> str:
    digest = hashlib.sha256()
    for member in members:
        path_bytes = member.path.encode("utf-8")
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(member.byte_length.to_bytes(8, "big"))
        digest.update(bytes.fromhex(member.sha256))
    return digest.hexdigest()


def verify_historical_small_scientific_manifest(
    repository_root: Path,
    relative_path: Path,
) -> ScientificInputManifest:
    """Verify the immutable Small receipt without comparing it to current source.

    The receipt describes a historical Small source freeze. Reference development
    legitimately evolves the checkout, so current-source comparison belongs to the
    independent Reference freeze verifier. This verifier instead checks the
    historical receipt's schema, canonical member inventory, and aggregate bindings.
    """

    try:
        path = ArtifactLocator(
            root=repository_root,
            relative_name=relative_path,
            maximum_bytes=_MAX_HISTORICAL_SMALL_MANIFEST_BYTES,
            label="historical Small scientific-input manifest",
        ).resolve()
        manifest = ScientificInputManifest.model_validate_json(path.read_text("utf-8"))
    except (OSError, ValueError) as exc:
        raise ScientificInputError("invalid historical Small scientific input manifest") from exc

    core_members = tuple(
        member for member in manifest.members if member.path != manifest.acceptance_member_path
    )
    if _aggregate_digest(core_members) != manifest.core_aggregate_sha256:
        raise ScientificInputError("invalid historical Small scientific input manifest")
    if _aggregate_digest(manifest.members) != manifest.aggregate_sha256:
        raise ScientificInputError("invalid historical Small scientific input manifest")
    return manifest
