"""Heat engine: low-res grid with Gaussian deposit and exponential decay (§4.3).

Pure in-memory state — knows nothing about cameras, files, or the UI. Positions are
normalized (0..1, 0..1) with origin top-left, matching detector foot-point output.
"""
import base64
from typing import List, Tuple

import numpy as np

# Fraction of deposited heat remaining after one full time-frame window.
RESIDUAL_AT_WINDOW = 0.05
# Gaussian deposit radius, in grid cells (sigma).
DEPOSIT_SIGMA = 1.6
# Heat added at the center of a confidence-1.0 detection, per deposit. At the
# ~2.5 Hz detection cadence this means roughly 10 s of continuous standing in one
# spot to reach full red — brief pass-throughs stay in the blue/green range.
DEPOSIT_AMOUNT = 0.05
GRID_CAP = 1.0


class HeatGrid:
    def __init__(self, w: int = 64, h: int = 36, time_frame_hours: float = 10 / 60):
        self.w = w
        self.h = h
        self.grid = np.zeros((h, w), dtype=np.float32)
        self.set_time_frame(time_frame_hours)
        # Precompute a deposit kernel patch once; deposits are patch adds, not full-grid ops.
        r = int(np.ceil(DEPOSIT_SIGMA * 3))
        ys, xs = np.mgrid[-r : r + 1, -r : r + 1]
        self._kernel = np.exp(-(xs**2 + ys**2) / (2 * DEPOSIT_SIGMA**2)).astype(np.float32)
        self._kr = r

    def set_time_frame(self, hours: float) -> None:
        self.window_s = max(60.0, hours * 3600.0)

    def decay(self, dt_s: float) -> None:
        if dt_s <= 0:
            return
        self.grid *= RESIDUAL_AT_WINDOW ** (dt_s / self.window_s)

    def deposit(self, x_norm: float, y_norm: float, conf: float) -> None:
        cx = int(round(x_norm * (self.w - 1)))
        cy = int(round(y_norm * (self.h - 1)))
        r = self._kr
        gy0, gy1 = max(0, cy - r), min(self.h, cy + r + 1)
        gx0, gx1 = max(0, cx - r), min(self.w, cx + r + 1)
        if gy0 >= gy1 or gx0 >= gx1:
            return
        ky0, kx0 = gy0 - (cy - r), gx0 - (cx - r)
        patch = self._kernel[ky0 : ky0 + (gy1 - gy0), kx0 : kx0 + (gx1 - gx0)]
        region = self.grid[gy0:gy1, gx0:gx1]
        np.minimum(region + patch * (DEPOSIT_AMOUNT * conf), GRID_CAP, out=region)

    def add_detections(self, people: List[Tuple[float, float, float]]) -> None:
        for x, y, conf in people:
            self.deposit(x, y, conf)

    def reset(self) -> None:
        self.grid.fill(0.0)

    # --- serialization for heatmapLog checkpoints (§6.2) ---

    def encode(self) -> str:
        return base64.b64encode(self.grid.astype(np.float16).tobytes()).decode("ascii")

    def load_encoded(self, encoded: str) -> None:
        raw = np.frombuffer(base64.b64decode(encoded), dtype=np.float16)
        if raw.size == self.w * self.h:
            self.grid = raw.reshape(self.h, self.w).astype(np.float32)


def render_overlay(grid: np.ndarray) -> np.ndarray:
    """Grid → RGBA uint8 image at grid resolution (upscaling/blur is the UI's job).

    Color ramp blue→green→yellow→red; alpha floor keeps mid-range values legible over
    a real photo (the low-contrast-blending failure mode called out in §4.3).
    """
    v = np.clip(grid, 0.0, 1.0)
    rgba = np.zeros((*v.shape, 4), dtype=np.uint8)

    # Piecewise-linear ramp over stops at t = 0, 1/3, 2/3, 1.
    stops = np.array(
        [[40, 90, 255], [40, 220, 130], [250, 220, 60], [255, 60, 40]], dtype=np.float32
    )
    t = v * 3.0
    idx = np.minimum(t.astype(np.int32), 2)
    frac = (t - idx)[..., None]
    color = stops[idx] * (1 - frac) + stops[idx + 1] * frac
    rgba[..., :3] = color.astype(np.uint8)

    alpha = np.where(v < 0.03, 0.0, np.minimum(250.0, 70.0 + v * 320.0))
    rgba[..., 3] = alpha.astype(np.uint8)
    return rgba
