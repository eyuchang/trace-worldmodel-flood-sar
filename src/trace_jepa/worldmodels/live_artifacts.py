from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path

import numpy as np
from pydantic import Field, model_validator

from trace_jepa.util import sha256_file, sha256_value
from trace_jepa.worldmodels.contracts import FrozenModel, SemanticWorldStatePrediction


_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_SAFE_ACTION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_MAX_NPZ_BYTES = 256 * 1024 * 1024
_MAX_NPY_BYTES = 512 * 1024 * 1024
_MAX_LATENT_ELEMENTS = 100_000_000


class ArtifactIntegrityError(RuntimeError):
    """Raised when a persisted inference artifact fails verification."""


class StoredInferenceArtifact(FrozenModel):
    artifact_schema_version: str = "live-inference-artifact-v2"
    artifact_sha256: str = Field(pattern=_SHA256_PATTERN)
    request_sha256: str = Field(pattern=_SHA256_PATTERN)
    model_bundle_sha256: str = Field(pattern=_SHA256_PATTERN)
    observation_sha256: str = Field(pattern=_SHA256_PATTERN)
    action_type: str
    semantic_state: SemanticWorldStatePrediction | None
    latent_sha256: str = Field(pattern=_SHA256_PATTERN)
    latent_shape: tuple[int, ...] = Field(min_length=1)
    latent_dtype: str = "float32"
    tensor_file: str
    tensor_file_sha256: str = Field(pattern=_SHA256_PATTERN)
    environment_manifest_sha256: str = Field(pattern=_SHA256_PATTERN)
    diagnostics: dict[str, float | int | str | bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_content_identity(self) -> "StoredInferenceArtifact":
        if not _SAFE_ACTION.fullmatch(self.action_type):
            raise ValueError("artifact action type is not path-safe")
        if any(item < 1 for item in self.latent_shape):
            raise ValueError("latent tensor shape must contain positive dimensions")
        if Path(self.tensor_file).name != self.tensor_file or not self.tensor_file.endswith(".npz"):
            raise ValueError("tensor file must be one local npz filename")
        expected = sha256_value(self.content_identity())
        if expected != self.artifact_sha256:
            raise ValueError("artifact hash does not match its logical content")
        return self

    def content_identity(self) -> dict[str, object]:
        return {
            "artifact_schema_version": self.artifact_schema_version,
            "request_sha256": self.request_sha256,
            "model_bundle_sha256": self.model_bundle_sha256,
            "observation_sha256": self.observation_sha256,
            "action_type": self.action_type,
            "semantic_state": (
                self.semantic_state.model_dump(mode="json")
                if self.semantic_state is not None
                else None
            ),
            "latent_sha256": self.latent_sha256,
            "latent_shape": list(self.latent_shape),
            "latent_dtype": self.latent_dtype,
            "environment_manifest_sha256": self.environment_manifest_sha256,
            "diagnostics": self.diagnostics,
        }


class ContentAddressedInferenceStore:
    """Atomic, verified storage for live inference outputs.

    The logical artifact digest is independent of ZIP container bytes.  A
    separate file digest detects on-disk tampering.  Request pointers contain
    no mutable model data and are also written atomically.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        if self.root.exists() and self.root.is_symlink():
            raise ValueError("inference-store root cannot be a symlink")
        self.artifacts_root = self.root / "artifacts"
        self.requests_root = self.root / "requests"
        self.request_manifests_root = self.root / "request-manifests"
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        self.requests_root.mkdir(parents=True, exist_ok=True)
        self.request_manifests_root.mkdir(parents=True, exist_ok=True)
        if (
            self.artifacts_root.is_symlink()
            or self.requests_root.is_symlink()
            or self.request_manifests_root.is_symlink()
        ):
            raise ValueError("inference-store directories cannot be symlinks")

    def register_request(
        self,
        request_sha256: str,
        payload: dict[str, object],
    ) -> None:
        """Persist the complete canonical request before cache lookup or execution."""

        self._require_hash(request_sha256, "request hash")
        if payload.get("request_sha256") != request_sha256:
            raise ArtifactIntegrityError("request payload and digest disagree")
        expected = sha256_value(
            {key: value for key, value in payload.items() if key != "request_sha256"}
        )
        if expected != request_sha256:
            raise ArtifactIntegrityError("request payload does not reproduce its digest")
        path = self.request_manifests_root / f"{request_sha256}.json"
        if path.is_symlink():
            raise ArtifactIntegrityError("request manifest is a symlink")
        if path.exists():
            if self._read_json(path) != payload:
                raise ArtifactIntegrityError(
                    "request digest is already bound to different content"
                )
            return
        self._write_json_atomic(path, payload)

    def get_request(self, request_sha256: str) -> dict[str, object]:
        self._require_hash(request_sha256, "request hash")
        path = self.request_manifests_root / f"{request_sha256}.json"
        payload = self._read_json(path)
        if payload.get("request_sha256") != request_sha256:
            raise ArtifactIntegrityError("request manifest digest field disagrees")
        expected = sha256_value(
            {key: value for key, value in payload.items() if key != "request_sha256"}
        )
        if expected != request_sha256:
            raise ArtifactIntegrityError("request manifest content hash mismatch")
        return payload

    @staticmethod
    def _require_hash(value: str, label: str) -> None:
        if not re.fullmatch(_SHA256_PATTERN[1:-1], value):
            raise ValueError(f"{label} must be a lowercase SHA-256 digest")

    @staticmethod
    def _latent_digest(latent: np.ndarray) -> str:
        return hashlib.sha256(np.ascontiguousarray(latent).tobytes()).hexdigest()

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            mode="w",
            encoding="utf-8",
            suffix=".json.tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    @staticmethod
    def _write_tensor_atomic(path: Path, latent: np.ndarray) -> None:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            suffix=".npz.tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            np.savez_compressed(handle, latent=latent)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    def put(
        self,
        *,
        request_sha256: str,
        model_bundle_sha256: str,
        observation_sha256: str,
        action_type: str,
        semantic_state: SemanticWorldStatePrediction | None,
        latent_tokens: np.ndarray,
        environment_manifest_sha256: str,
        diagnostics: dict[str, float | int | str | bool] | None = None,
    ) -> StoredInferenceArtifact:
        for value, label in (
            (request_sha256, "request hash"),
            (model_bundle_sha256, "model bundle hash"),
            (observation_sha256, "observation hash"),
            (environment_manifest_sha256, "environment manifest hash"),
        ):
            self._require_hash(value, label)
        if not _SAFE_ACTION.fullmatch(action_type):
            raise ValueError("action type is not artifact-safe")
        latent = np.asarray(latent_tokens, dtype=np.float32)
        if (
            latent.ndim < 1
            or latent.ndim > 5
            or latent.size == 0
            or latent.size > _MAX_LATENT_ELEMENTS
            or not np.isfinite(latent).all()
        ):
            raise ValueError("latent tokens must be a finite tensor with one to five dimensions")
        diagnostics = diagnostics or {}
        try:
            json.dumps(diagnostics, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("artifact diagnostics must be finite JSON scalars") from exc

        content = {
            "artifact_schema_version": "live-inference-artifact-v2",
            "request_sha256": request_sha256,
            "model_bundle_sha256": model_bundle_sha256,
            "observation_sha256": observation_sha256,
            "action_type": action_type,
            "semantic_state": (
                semantic_state.model_dump(mode="json")
                if semantic_state is not None
                else None
            ),
            "latent_sha256": self._latent_digest(latent),
            "latent_shape": list(latent.shape),
            "latent_dtype": "float32",
            "environment_manifest_sha256": environment_manifest_sha256,
            "diagnostics": diagnostics,
        }
        artifact_sha256 = sha256_value(content)
        directory = self.artifacts_root / artifact_sha256[:2]
        if directory.exists() and directory.is_symlink():
            raise ArtifactIntegrityError("artifact shard directory is a symlink")
        directory.mkdir(parents=True, exist_ok=True)
        tensor_path = directory / f"{artifact_sha256}.npz"
        metadata_path = directory / f"{artifact_sha256}.json"
        if tensor_path.is_symlink() or metadata_path.is_symlink():
            raise ArtifactIntegrityError("artifact destination is a symlink")
        if tensor_path.exists() or metadata_path.exists():
            existing, _ = self.get(artifact_sha256)
            if existing.request_sha256 != request_sha256:
                raise ArtifactIntegrityError("artifact hash collision with a different request")
            self._write_request_pointer(request_sha256, artifact_sha256)
            return existing

        self._write_tensor_atomic(tensor_path, latent)
        metadata = StoredInferenceArtifact(
            **content,
            artifact_sha256=artifact_sha256,
            tensor_file=tensor_path.name,
            tensor_file_sha256=sha256_file(tensor_path),
        )
        self._write_json_atomic(metadata_path, metadata.model_dump(mode="json"))
        self._write_request_pointer(request_sha256, artifact_sha256)
        return metadata

    def _write_request_pointer(self, request_sha256: str, artifact_sha256: str) -> None:
        pointer = self.requests_root / f"{request_sha256}.json"
        if pointer.is_symlink():
            raise ArtifactIntegrityError("request pointer is a symlink")
        if pointer.exists():
            payload = self._read_json(pointer)
            if payload != {
                "request_sha256": request_sha256,
                "artifact_sha256": artifact_sha256,
            }:
                raise ArtifactIntegrityError("request already points to a different artifact")
            return
        self._write_json_atomic(
            pointer,
            {"request_sha256": request_sha256, "artifact_sha256": artifact_sha256},
        )

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        if not path.is_file() or path.is_symlink():
            raise ArtifactIntegrityError(f"artifact file is missing or unsafe: {path.name}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ArtifactIntegrityError(f"artifact JSON is unreadable: {path.name}") from exc
        if not isinstance(payload, dict):
            raise ArtifactIntegrityError("artifact JSON root must be an object")
        return payload

    def get(self, artifact_sha256: str) -> tuple[StoredInferenceArtifact, np.ndarray]:
        self._require_hash(artifact_sha256, "artifact hash")
        directory = self.artifacts_root / artifact_sha256[:2]
        if directory.is_symlink():
            raise ArtifactIntegrityError("artifact shard directory is a symlink")
        metadata_path = directory / f"{artifact_sha256}.json"
        payload = self._read_json(metadata_path)
        try:
            metadata = StoredInferenceArtifact.model_validate(payload)
        except ValueError as exc:
            raise ArtifactIntegrityError("artifact metadata failed schema verification") from exc
        if metadata.artifact_sha256 != artifact_sha256:
            raise ArtifactIntegrityError("artifact path and content hash disagree")
        tensor_path = directory / metadata.tensor_file
        if not tensor_path.is_file() or tensor_path.is_symlink():
            raise ArtifactIntegrityError("artifact tensor is missing or unsafe")
        if sha256_file(tensor_path) != metadata.tensor_file_sha256:
            raise ArtifactIntegrityError("artifact tensor file hash mismatch")
        self._verify_npz_limits(tensor_path, expected_member="latent.npy")
        try:
            with np.load(tensor_path, allow_pickle=False) as payload_np:
                if set(payload_np.files) != {"latent"}:
                    raise ArtifactIntegrityError("artifact tensor archive has unexpected fields")
                latent = payload_np["latent"].astype(np.float32, copy=False)
        except (OSError, ValueError) as exc:
            raise ArtifactIntegrityError("artifact tensor archive is unreadable") from exc
        if tuple(latent.shape) != metadata.latent_shape:
            raise ArtifactIntegrityError("artifact tensor shape mismatch")
        if not np.isfinite(latent).all() or self._latent_digest(latent) != metadata.latent_sha256:
            raise ArtifactIntegrityError("artifact tensor content hash mismatch")
        return metadata, latent

    @staticmethod
    def _verify_npz_limits(path: Path, *, expected_member: str) -> None:
        if path.stat().st_size > _MAX_NPZ_BYTES:
            raise ArtifactIntegrityError("artifact tensor archive exceeds its byte limit")
        try:
            with zipfile.ZipFile(path) as archive:
                members = archive.infolist()
        except (OSError, zipfile.BadZipFile) as exc:
            raise ArtifactIntegrityError("artifact tensor archive is unreadable") from exc
        if len(members) != 1 or members[0].filename != expected_member:
            raise ArtifactIntegrityError("artifact tensor archive has unexpected members")
        member = members[0]
        if member.file_size > _MAX_NPY_BYTES:
            raise ArtifactIntegrityError("artifact tensor payload exceeds its byte limit")

    def get_for_request(self, request_sha256: str) -> tuple[StoredInferenceArtifact, np.ndarray] | None:
        self._require_hash(request_sha256, "request hash")
        pointer = self.requests_root / f"{request_sha256}.json"
        if not pointer.exists():
            return None
        payload = self._read_json(pointer)
        if payload.get("request_sha256") != request_sha256:
            raise ArtifactIntegrityError("request pointer hash mismatch")
        artifact_sha256 = payload.get("artifact_sha256")
        if not isinstance(artifact_sha256, str):
            raise ArtifactIntegrityError("request pointer omits artifact hash")
        artifact = self.get(artifact_sha256)
        if artifact[0].request_sha256 != request_sha256:
            raise ArtifactIntegrityError("request pointer targets a different request")
        return artifact
