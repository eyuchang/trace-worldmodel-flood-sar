from __future__ import annotations

import hashlib
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol, runtime_checkable

import numpy as np
from pydantic import Field, model_validator

from trace_jepa.util import sha256_value
from trace_jepa.worldmodels.contracts import (
    FrozenModel,
    ModelArtifactIdentity,
    ObservationProvenance,
    RouteWorldModelRequestV2,
    SemanticWorldStatePrediction,
)
from trace_jepa.worldmodels.live_artifacts import (
    ArtifactIntegrityError,
    ContentAddressedInferenceStore,
    StoredInferenceArtifact,
)


class LiveInferenceError(RuntimeError):
    """Base class for fail-closed live-inference failures."""


class LiveInferenceBackpressure(LiveInferenceError):
    """Raised when the bounded inference queue cannot accept more work."""


class LiveInferenceState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class LiveInferenceFailureCode(str, Enum):
    OBSERVATION_INTEGRITY = "observation_integrity"
    BACKEND_FAILURE = "backend_failure"
    OUTPUT_INVALID = "output_invalid"
    ARTIFACT_INTEGRITY = "artifact_integrity"
    SERVICE_CLOSED = "service_closed"


class LiveInferenceRequest(FrozenModel):
    """Typed request containing only controller-visible data."""

    request_schema_version: str = "live-inference-request-v2"
    route_request: RouteWorldModelRequestV2
    observation: ObservationProvenance
    model: ModelArtifactIdentity
    request_sha256: str = ""

    @model_validator(mode="after")
    def validate_and_hash(self) -> "LiveInferenceRequest":
        if self.route_request.expected_model_bundle_sha256 != self.model.bundle_sha256:
            raise ValueError("route request expects a different model bundle")
        if self.route_request.visual_observation_id != self.observation.observation_id:
            raise ValueError("route request and observation identifiers disagree")
        if self.route_request.visual_observation_hash != self.observation.observation_sha256:
            raise ValueError("route request and observation hashes disagree")
        if self.route_request.visual_frames_sha256 != self.observation.frames_sha256:
            raise ValueError("route request and frame hashes disagree")
        if self.route_request.visual_sensor_version != self.observation.sensor_model_version:
            raise ValueError("route request and sensor versions disagree")
        if self.route_request.visual_observed_at != self.observation.observed_at:
            raise ValueError("route request and observation times disagree")
        if self.route_request.action_type not in self.model.supported_action_types:
            raise ValueError("requested action is not supported by the model bundle")
        expected = sha256_value(self.model_dump(mode="json", exclude={"request_sha256"}))
        if not self.request_sha256:
            object.__setattr__(self, "request_sha256", expected)
        elif self.request_sha256 != expected:
            raise ValueError("live inference request hash mismatch")
        return self


class LiveInferenceReceipt(FrozenModel):
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    state: LiveInferenceState
    submitted_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    cache_hit: bool = False
    wall_duration_ms: float | None = Field(default=None, ge=0.0)
    queue_wait_ms: float | None = Field(default=None, ge=0.0)
    backend_duration_ms: float | None = Field(default=None, ge=0.0)
    persistence_duration_ms: float | None = Field(default=None, ge=0.0)
    total_service_ms: float | None = Field(default=None, ge=0.0)
    device_type: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.:-]+$")
    precision: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.:-]+$")
    environment_manifest_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    failure_code: LiveInferenceFailureCode | None = None
    failure_type: str | None = None


@dataclass(frozen=True)
class LiveBackendOutput:
    semantic_state: SemanticWorldStatePrediction | None
    latent_tokens: np.ndarray
    diagnostics: dict[str, float | int | str | bool]


@runtime_checkable
class ControllerObservationReader(Protocol):
    def read_frames(self, observation: ObservationProvenance) -> np.ndarray: ...


@runtime_checkable
class LiveInferenceBackend(Protocol):
    @property
    def identity(self) -> ModelArtifactIdentity: ...

    @property
    def environment_manifest_sha256(self) -> str: ...

    def infer(
        self,
        *,
        frames: np.ndarray,
        request: RouteWorldModelRequestV2,
    ) -> LiveBackendOutput: ...


class LiveWorldModelService:
    """Single-worker, bounded, fail-closed inference service.

    A service is bound to exactly one verified model bundle.  The worker is
    serialized because concurrent access to the same GPU/model state is not
    assumed safe.  Exact requests are deduplicated by their complete content
    hash and may be replayed from the verified artifact store.
    """

    def __init__(
        self,
        *,
        backend: LiveInferenceBackend,
        observation_reader: ControllerObservationReader,
        artifact_store: ContentAddressedInferenceStore,
        queue_capacity: int = 8,
    ):
        if queue_capacity < 1:
            raise ValueError("live inference queue capacity must be positive")
        self.backend = backend
        self.observation_reader = observation_reader
        self.artifact_store = artifact_store
        self._queue: queue.Queue[LiveInferenceRequest | None] = queue.Queue(queue_capacity)
        self._receipts: dict[str, LiveInferenceReceipt] = {}
        self._submitted_counters: dict[str, float] = {}
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._closed = False

    @property
    def identity(self) -> ModelArtifactIdentity:
        return self.backend.identity

    def start(self) -> None:
        with self._lock:
            if self._closed:
                raise LiveInferenceError("live inference service is closed")
            if self._worker is not None:
                return
            self._worker = threading.Thread(
                target=self._run,
                name=f"worldmodel-{self.identity.family}",
                daemon=True,
            )
            self._worker.start()

    def submit(self, request: LiveInferenceRequest) -> LiveInferenceReceipt:
        submit_counter = time.perf_counter()
        if request.model.bundle_sha256 != self.identity.bundle_sha256:
            raise LiveInferenceError("request model bundle does not match the live backend")
        now = datetime.now(timezone.utc)
        with self._lock:
            if self._closed:
                raise LiveInferenceError("live inference service is closed")
            existing_receipt = self._receipts.get(request.request_sha256)
            if existing_receipt is not None:
                return existing_receipt
            try:
                self.artifact_store.register_request(
                    request.request_sha256,
                    request.model_dump(mode="json"),
                )
                cached = self.artifact_store.get_for_request(request.request_sha256)
            except ArtifactIntegrityError:
                receipt = self._integrity_failure_receipt(
                    request.request_sha256,
                    now,
                    "ArtifactIntegrityError",
                )
                self._receipts[request.request_sha256] = receipt
                return receipt
            if cached is not None:
                if (
                    cached[0].environment_manifest_sha256
                    != self.backend.environment_manifest_sha256
                ):
                    receipt = self._integrity_failure_receipt(
                        request.request_sha256,
                        now,
                        "ProducerEnvironmentMismatch",
                    )
                    self._receipts[request.request_sha256] = receipt
                    return receipt
                receipt = LiveInferenceReceipt(
                    request_sha256=request.request_sha256,
                    state=LiveInferenceState.COMPLETED,
                    submitted_at=now,
                    started_at=now,
                    completed_at=now,
                    artifact_sha256=cached[0].artifact_sha256,
                    cache_hit=True,
                    wall_duration_ms=0.0,
                    queue_wait_ms=0.0,
                    backend_duration_ms=0.0,
                    persistence_duration_ms=0.0,
                    total_service_ms=(time.perf_counter() - submit_counter) * 1000.0,
                    device_type=self._backend_device_type(),
                    precision=self._backend_precision(),
                    environment_manifest_sha256=(
                        cached[0].environment_manifest_sha256
                    ),
                )
                self._receipts[request.request_sha256] = receipt
                return receipt
            receipt = LiveInferenceReceipt(
                request_sha256=request.request_sha256,
                state=LiveInferenceState.QUEUED,
                submitted_at=now,
            )
            self._receipts[request.request_sha256] = receipt
            self._submitted_counters[request.request_sha256] = submit_counter
            try:
                self._queue.put_nowait(request)
            except queue.Full as exc:
                del self._receipts[request.request_sha256]
                del self._submitted_counters[request.request_sha256]
                raise LiveInferenceBackpressure("live inference queue is full") from exc
            return receipt

    def poll(self, request_sha256: str) -> LiveInferenceReceipt | None:
        with self._lock:
            return self._receipts.get(request_sha256)

    def artifact(
        self, request_sha256: str
    ) -> tuple[StoredInferenceArtifact, np.ndarray] | None:
        receipt = self.poll(request_sha256)
        if receipt is None or receipt.state != LiveInferenceState.COMPLETED:
            return None
        return self.artifact_store.get_for_request(request_sha256)

    def close(self, *, timeout_s: float = 30.0) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            worker = self._worker
        if worker is None:
            return
        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                raise LiveInferenceError(
                    "live inference worker could not accept a shutdown sentinel"
                )
            try:
                self._queue.put(None, timeout=min(0.1, remaining))
                break
            except queue.Full:
                continue
        worker.join(timeout=max(0.0, deadline - time.monotonic()))
        if worker.is_alive():
            raise LiveInferenceError("live inference worker did not stop within the timeout")

    def _run(self) -> None:
        while True:
            request = self._queue.get()
            if request is None:
                self._queue.task_done()
                return
            self._execute(request)
            self._queue.task_done()

    def _execute(self, request: LiveInferenceRequest) -> None:
        started_at = datetime.now(timezone.utc)
        started_counter = time.perf_counter()
        with self._lock:
            submitted_at = self._receipts[request.request_sha256].submitted_at
            submitted_counter = self._submitted_counters[request.request_sha256]
            self._receipts[request.request_sha256] = LiveInferenceReceipt(
                request_sha256=request.request_sha256,
                state=LiveInferenceState.RUNNING,
                submitted_at=submitted_at,
                started_at=started_at,
            )
        try:
            frames = np.asarray(self.observation_reader.read_frames(request.observation))
            self._verify_frames(frames, request.observation)
        except Exception as exc:  # boundary converts provider errors into typed failure receipts
            self._fail(request, started_at, LiveInferenceFailureCode.OBSERVATION_INTEGRITY, exc)
            return
        try:
            self._synchronize_backend()
            backend_started_counter = time.perf_counter()
            output = self.backend.infer(frames=frames, request=request.route_request)
            self._synchronize_backend()
            backend_completed_counter = time.perf_counter()
        except Exception as exc:  # backend internals are not exposed to the controller
            self._fail(request, started_at, LiveInferenceFailureCode.BACKEND_FAILURE, exc)
            return
        try:
            if not isinstance(output, LiveBackendOutput):
                raise TypeError("backend returned the wrong output type")
            if (
                output.semantic_state is not None
                and output.semantic_state.horizons_s
                != request.route_request.prediction_horizons_s
            ):
                raise ValueError("backend semantic horizons do not match the request")
            persistence_started_counter = time.perf_counter()
            artifact = self.artifact_store.put(
                request_sha256=request.request_sha256,
                model_bundle_sha256=request.model.bundle_sha256,
                observation_sha256=request.observation.observation_sha256,
                action_type=request.route_request.action_type,
                semantic_state=output.semantic_state,
                latent_tokens=output.latent_tokens,
                environment_manifest_sha256=self.backend.environment_manifest_sha256,
                diagnostics=output.diagnostics,
            )
            persistence_completed_counter = time.perf_counter()
        except Exception as exc:
            self._fail(request, started_at, LiveInferenceFailureCode.OUTPUT_INVALID, exc)
            return
        completed_at = datetime.now(timezone.utc)
        elapsed_ms = (persistence_completed_counter - started_counter) * 1000.0
        with self._lock:
            self._receipts[request.request_sha256] = LiveInferenceReceipt(
                request_sha256=request.request_sha256,
                state=LiveInferenceState.COMPLETED,
                submitted_at=submitted_at,
                started_at=started_at,
                completed_at=completed_at,
                artifact_sha256=artifact.artifact_sha256,
                cache_hit=False,
                wall_duration_ms=elapsed_ms,
                queue_wait_ms=max(0.0, (started_counter - submitted_counter) * 1000.0),
                backend_duration_ms=max(
                    0.0, (backend_completed_counter - backend_started_counter) * 1000.0
                ),
                persistence_duration_ms=max(
                    0.0,
                    (persistence_completed_counter - persistence_started_counter) * 1000.0,
                ),
                total_service_ms=max(
                    0.0, (persistence_completed_counter - submitted_counter) * 1000.0
                ),
                device_type=self._backend_device_type(),
                precision=self._backend_precision(),
                environment_manifest_sha256=(
                    self.backend.environment_manifest_sha256
                ),
            )

    def _fail(
        self,
        request: LiveInferenceRequest,
        started_at: datetime,
        code: LiveInferenceFailureCode,
        exc: Exception,
    ) -> None:
        completed_at = datetime.now(timezone.utc)
        with self._lock:
            submitted_at = self._receipts[request.request_sha256].submitted_at
            self._receipts[request.request_sha256] = LiveInferenceReceipt(
                request_sha256=request.request_sha256,
                state=LiveInferenceState.FAILED,
                submitted_at=submitted_at,
                started_at=started_at,
                completed_at=completed_at,
                wall_duration_ms=max(
                    0.0, (completed_at - started_at).total_seconds() * 1000.0
                ),
                device_type=self._backend_device_type(),
                precision=self._backend_precision(),
                environment_manifest_sha256=(
                    self.backend.environment_manifest_sha256
                ),
                failure_code=code,
                failure_type=type(exc).__name__,
            )

    def _integrity_failure_receipt(
        self,
        request_sha256: str,
        now: datetime,
        failure_type: str,
    ) -> LiveInferenceReceipt:
        return LiveInferenceReceipt(
            request_sha256=request_sha256,
            state=LiveInferenceState.FAILED,
            submitted_at=now,
            started_at=now,
            completed_at=now,
            device_type=self._backend_device_type(),
            precision=self._backend_precision(),
            environment_manifest_sha256=self.backend.environment_manifest_sha256,
            failure_code=LiveInferenceFailureCode.ARTIFACT_INTEGRITY,
            failure_type=failure_type,
        )

    def _backend_device_type(self) -> str:
        value = str(getattr(self.backend, "device_type", "cpu"))
        if value not in {"cpu", "cuda", "mps"}:
            raise LiveInferenceError("backend declared an unsupported device type")
        return value

    def _backend_precision(self) -> str:
        value = str(getattr(self.backend, "precision", "float32"))
        if not value or len(value) > 64:
            raise LiveInferenceError("backend declared an invalid precision")
        return value

    def _synchronize_backend(self) -> None:
        synchronize = getattr(self.backend, "synchronize", None)
        if synchronize is not None:
            synchronize()

    @staticmethod
    def _verify_frames(frames: np.ndarray, observation: ObservationProvenance) -> None:
        if frames.ndim != 4 or frames.shape[-1] != 3 or frames.dtype != np.uint8:
            raise ValueError("controller observation must be an uint8 [T,H,W,3] tensor")
        if frames.size == 0:
            raise ValueError("controller observation contains no frames")
        digest = hashlib.sha256(np.ascontiguousarray(frames).tobytes()).hexdigest()
        if digest != observation.frames_sha256:
            raise ValueError("controller observation frame hash mismatch")
