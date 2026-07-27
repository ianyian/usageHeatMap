"""Camera frame acquisition + motion gate (§4.2).

Uses OpenCV VideoCapture, which covers both the MacBook built-in camera (dev/testing,
index 0) and a USB webcam on the Pi. Swapping to picamera2 later only touches this file.
"""
from typing import Optional

import cv2
import numpy as np

# Mean absolute per-pixel difference (0..255) above which "something moved".
MOTION_THRESHOLD = 4.0
# Motion is checked on a tiny grayscale thumbnail — cheap by construction.
MOTION_THUMB_W = 80


class Camera:
    def __init__(self, index: int = 0, width: int = 1280, height: int = 720):
        self.cap = cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if not self.cap.isOpened():
            raise RuntimeError(
                f"Could not open camera index {index}. On macOS, grant camera "
                "permission to the terminal app (System Settings → Privacy & Security "
                "→ Camera) and retry."
            )

    def read(self) -> Optional[np.ndarray]:
        ok, frame = self.cap.read()
        return frame if ok else None

    def release(self) -> None:
        self.cap.release()


class MotionGate:
    """Cheap frame-diff trigger. Only decides *whether* to run the detector — its
    value is never stored or shown (§4.2)."""

    def __init__(self, threshold: float = MOTION_THRESHOLD):
        self.threshold = threshold
        self._prev: Optional[np.ndarray] = None

    def _thumb(self, frame: np.ndarray) -> np.ndarray:
        h = int(MOTION_THUMB_W * frame.shape[0] / frame.shape[1])
        small = cv2.resize(frame, (MOTION_THUMB_W, h), interpolation=cv2.INTER_AREA)
        return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)

    def triggered(self, frame: np.ndarray) -> bool:
        thumb = self._thumb(frame)
        if self._prev is None or self._prev.shape != thumb.shape:
            self._prev = thumb
            return True  # first frame: let the detector establish a baseline
        diff = float(np.mean(np.abs(thumb - self._prev)))
        self._prev = thumb
        return diff >= self.threshold
