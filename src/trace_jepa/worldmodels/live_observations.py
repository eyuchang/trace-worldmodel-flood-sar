from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

import numpy as np

from trace_jepa.util import sha256_value
from trace_jepa.worldmodels.contracts import ObservationProvenance


_SAFE_OBSERVATION_ID = re.compile(r"^simobs-[0-9a-f]{24}$")
_MAX_MANIFEST_BYTES = 1024 * 1024
_MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
_MAX_UNCOMPRESSED_BYTES = 256 * 1024 * 1024


class ObservationIntegrityError(RuntimeError):
    """Raised when a delivered controller observation cannot be verified."""


class VerifiedSimulatorObservationRepository:
    """Read verified simulator clips without exposing audit-only truth.

    The simulator manifest contains an audit snapshot for reproducibility.  This
    repository verifies that envelope at the ingestion boundary, then returns
    only frames and a controller-safe provenance record to live inference.
    """

    def __init__(
        self,
        root: Path,
        *,
        allowed_partitions: tuple[str, ...] = ("development",),
    ):
        self.root = Path(root)
        if not self.root.is_dir() or self.root.is_symlink():
            raise ValueError("observation repository must be a real directory")
        if not allowed_partitions or len(set(allowed_partitions)) != len(
            allowed_partitions
        ):
            raise ValueError("allowed observation partitions must be nonempty and unique")
        self.allowed_partitions = frozenset(allowed_partitions)

    def provenance(
        self,
        observation_id: str,
        *,
        expected_observation_sha256: str,
    ) -> ObservationProvenance:
        manifest, frames = self._load(observation_id)
        if manifest["observation_hash"] != expected_observation_sha256:
            raise ObservationIntegrityError(
                "delivered observation does not match the controller belief hash"
            )
        controller_manifest = self._controller_manifest(manifest, frames)
        return ObservationProvenance(
            observation_id=observation_id,
            observation_sha256=str(manifest["observation_hash"]),
            frames_sha256=str(manifest["frames_sha256"]),
            controller_manifest_sha256=sha256_value(controller_manifest),
            sensor_model_version=str(manifest["sensor_model_version"]),
            observed_at=float(manifest["sampled_at"]),
            study_partition=str(manifest["study_partition"]),
        )

    def read_frames(self, observation: ObservationProvenance) -> np.ndarray:
        manifest, frames = self._load(observation.observation_id)
        controller_manifest = self._controller_manifest(manifest, frames)
        expected_links = {
            "observation_sha256": str(manifest["observation_hash"]),
            "frames_sha256": str(manifest["frames_sha256"]),
            "controller_manifest_sha256": sha256_value(controller_manifest),
            "sensor_model_version": str(manifest["sensor_model_version"]),
            "observed_at": float(manifest["sampled_at"]),
            "study_partition": str(manifest["study_partition"]),
        }
        actual_links = observation.model_dump(
            mode="json",
            exclude={"provenance_schema_version", "observation_id"},
        )
        if actual_links != expected_links:
            raise ObservationIntegrityError(
                "observation provenance no longer matches the stored artifact"
            )
        return frames.copy()

    def _load(self, observation_id: str) -> tuple[dict[str, object], np.ndarray]:
        if not _SAFE_OBSERVATION_ID.fullmatch(observation_id):
            raise ObservationIntegrityError("observation identifier is unsafe")
        manifest_path = self.root / f"{observation_id}.json"
        frames_path = self.root / f"{observation_id}.npz"
        for path in (manifest_path, frames_path):
            if not path.is_file() or path.is_symlink():
                raise ObservationIntegrityError("observation artifact is missing or unsafe")
        if manifest_path.stat().st_size > _MAX_MANIFEST_BYTES:
            raise ObservationIntegrityError("observation manifest exceeds its byte limit")
        if frames_path.stat().st_size > _MAX_ARCHIVE_BYTES:
            raise ObservationIntegrityError("observation archive exceeds its byte limit")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ObservationIntegrityError("observation manifest is unreadable") from exc
        if not isinstance(manifest, dict):
            raise ObservationIntegrityError("observation manifest root must be an object")
        required = {
            "manifest_version",
            "observation_id",
            "observation_hash",
            "frames_file",
            "frames_sha256",
            "frame_shape",
            "frame_dtype",
            "controller_usable",
            "study_partition",
            "sampled_at",
            "sensor_model_version",
            "audit_snapshot_sha256",
            "audit_snapshot",
        }
        if required - manifest.keys():
            raise ObservationIntegrityError("observation manifest is incomplete")
        if manifest["manifest_version"] != "simulator-visual-observation-v1":
            raise ObservationIntegrityError("unsupported observation manifest version")
        if manifest["observation_id"] != observation_id:
            raise ObservationIntegrityError("observation manifest identifier mismatch")
        if manifest["frames_file"] != frames_path.name:
            raise ObservationIntegrityError("observation manifest references an unsafe tensor")
        if manifest["controller_usable"] is not True:
            raise ObservationIntegrityError("observation was not delivered to the controller")
        if str(manifest["study_partition"]) not in self.allowed_partitions:
            raise ObservationIntegrityError("observation partition is not authorized")
        frame_shape = manifest["frame_shape"]
        if (
            not isinstance(frame_shape, list)
            or len(frame_shape) != 4
            or any(not isinstance(item, int) or item < 1 for item in frame_shape)
            or frame_shape[0] > 64
            or frame_shape[1] > 1024
            or frame_shape[2] > 1024
            or frame_shape[3] != 3
        ):
            raise ObservationIntegrityError("observation frame shape exceeds protocol limits")

        audit_snapshot = manifest["audit_snapshot"]
        if not isinstance(audit_snapshot, dict):
            raise ObservationIntegrityError("audit snapshot is malformed")
        audit_sha256 = sha256_value(audit_snapshot)
        if audit_sha256 != manifest["audit_snapshot_sha256"]:
            raise ObservationIntegrityError("audit snapshot hash mismatch")
        try:
            with zipfile.ZipFile(frames_path) as archive:
                members = archive.infolist()
            if {item.filename for item in members} != {
                "frames.npy",
                "observation_id.npy",
                "observation_hash.npy",
            } or sum(item.file_size for item in members) > _MAX_UNCOMPRESSED_BYTES:
                raise ObservationIntegrityError(
                    "observation archive members exceed protocol limits"
                )
            with np.load(frames_path, allow_pickle=False) as payload:
                if set(payload.files) != {"frames", "observation_id", "observation_hash"}:
                    raise ObservationIntegrityError(
                        "observation archive has unexpected fields"
                    )
                frames = payload["frames"]
                archive_id = str(payload["observation_id"].item())
                archive_hash = str(payload["observation_hash"].item())
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            raise ObservationIntegrityError("observation archive is unreadable") from exc
        if archive_id != observation_id or archive_hash != manifest["observation_hash"]:
            raise ObservationIntegrityError("observation archive identity mismatch")
        if (
            frames.dtype != np.uint8
            or frames.ndim != 4
            or frames.shape[-1] != 3
            or list(frames.shape) != manifest["frame_shape"]
            or str(frames.dtype) != manifest["frame_dtype"]
        ):
            raise ObservationIntegrityError("observation frame schema mismatch")
        frames_sha256 = hashlib.sha256(
            np.ascontiguousarray(frames).tobytes()
        ).hexdigest()
        if frames_sha256 != manifest["frames_sha256"]:
            raise ObservationIntegrityError("observation frame hash mismatch")
        expected_observation_hash = sha256_value(
            {
                "snapshot_sha256": audit_sha256,
                "frames_sha256": frames_sha256,
                "shape": list(frames.shape),
                "dtype": str(frames.dtype),
            }
        )
        if expected_observation_hash != manifest["observation_hash"]:
            raise ObservationIntegrityError("observation content hash mismatch")
        if not observation_id.endswith(expected_observation_hash[:24]):
            raise ObservationIntegrityError("observation identifier is not content-derived")
        return manifest, frames

    @staticmethod
    def _controller_manifest(
        manifest: dict[str, object], frames: np.ndarray
    ) -> dict[str, object]:
        return {
            "manifest_version": "controller-visual-observation-v2",
            "observation_id": manifest["observation_id"],
            "observation_hash": manifest["observation_hash"],
            "frames_sha256": manifest["frames_sha256"],
            "frame_shape": list(frames.shape),
            "frame_dtype": str(frames.dtype),
            "study_partition": manifest["study_partition"],
            "sampled_at": manifest["sampled_at"],
            "sensor_model_version": manifest["sensor_model_version"],
        }
