from __future__ import annotations

from pathlib import Path

import numpy as np


def sample_video(path: Path, num_frames: int = 64) -> tuple[np.ndarray, list[int]]:
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Install the 'jepa' optional dependencies to decode video") from exc

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"could not open video: {path}")
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        raise ValueError("video contains no readable frames")
    indices = np.linspace(0, max(0, total - 1), num_frames).round().astype(int).tolist()
    frames: list[np.ndarray] = []
    for index in indices:
        capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = capture.read()
        if not ok:
            capture.release()
            raise ValueError(f"failed to read frame {index}")
        frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    capture.release()
    return np.stack(frames), indices
