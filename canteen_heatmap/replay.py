"""Hour-scoped replay (§4.5): rebuild heat-grid state from one heatmapLog file.

On load, the hour's records are walked once and grid snapshots are stored on a fixed
step, so scrubbing is an array index, not a recompute. One hour at 5s steps is 720
snapshots of a 64×36 float grid (~6 MB) — cheap.
"""
from datetime import datetime
from typing import List, Optional

import numpy as np

from .heatmap import HeatGrid

SNAPSHOT_STEP_S = 5.0
HOUR_S = 3600.0


class HourReplay:
    def __init__(self, hour_key: str, records: List[dict], grid_w: int, grid_h: int,
                 time_frame_hours: float):
        self.hour_key = hour_key
        self.hour_start = datetime.strptime(hour_key, "%Y-%m-%d_%H")
        self.snapshots: List[np.ndarray] = []
        self.counts: List[int] = []
        self._build(records, grid_w, grid_h, time_frame_hours)

    def _t_offset(self, iso: str) -> float:
        t = datetime.fromisoformat(iso)
        return (t - self.hour_start).total_seconds()

    def _build(self, records: List[dict], w: int, h: int, time_frame_hours: float) -> None:
        grid = HeatGrid(w, h, time_frame_hours)
        cursor = 0.0  # seconds into the hour that `grid` currently represents
        n_steps = int(HOUR_S / SNAPSHOT_STEP_S)
        last_count = 0
        rec_i = 0

        for step in range(n_steps + 1):
            snap_t = step * SNAPSHOT_STEP_S
            # Consume all records up to this snapshot time.
            while rec_i < len(records):
                rec = records[rec_i]
                try:
                    rt = self._t_offset(rec["t"])
                except (KeyError, ValueError):
                    rec_i += 1
                    continue
                if rt > snap_t:
                    break
                grid.decay(rt - cursor)
                cursor = max(cursor, rt)
                if rec.get("type") == "checkpoint" and "grid" in rec:
                    grid.load_encoded(rec["grid"])
                elif rec.get("type") in ("sample", "detection"):
                    people = rec.get("people", [])
                    # "sample" records aggregate a window: "count" is the peak
                    # concurrent headcount, while "people" holds every foot-point.
                    last_count = rec.get("count", len(people))
                    for p in people:
                        grid.deposit(p["x"], p["y"], p.get("conf", 0.5))
                rec_i += 1
            grid.decay(snap_t - cursor)
            cursor = snap_t
            self.snapshots.append(grid.grid.copy())
            self.counts.append(last_count)

    def __len__(self) -> int:
        return len(self.snapshots)

    def at(self, seconds_into_hour: float) -> Optional[np.ndarray]:
        if not self.snapshots:
            return None
        i = int(round(seconds_into_hour / SNAPSHOT_STEP_S))
        i = min(len(self.snapshots) - 1, max(0, i))
        return self.snapshots[i]

    def count_at(self, seconds_into_hour: float) -> int:
        if not self.counts:
            return 0
        i = int(round(seconds_into_hour / SNAPSHOT_STEP_S))
        return self.counts[min(len(self.counts) - 1, max(0, i))]
