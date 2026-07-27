"""Session folders, heatmapLog write/read with hourly rotation, reference photos (§6).

Layout per session (one session per base-image capture):

    <data_dir>/<session-name>/
      baseImage/base.jpg
      logPicture/YYYY-MM-DD_HH-MM-SS.jpg     # reference photo, on interval
      log/heatmapLog_HH.jsonl                # one file per hour, checkpoint-first
      meta.json
"""
import dataclasses
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .config import Settings
from .heatmap import HeatGrid

Detection = Tuple[float, float, float]


class SessionStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.session_dir: Optional[Path] = None
        self._log_hour: Optional[str] = None  # "YYYY-MM-DD_HH" of the open log file
        self._last_ref_save = 0.0

    # --- session lifecycle ---

    def new_session(self, base_frame: np.ndarray, settings: Settings) -> Path:
        name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.session_dir = self.data_dir / name
        for sub in ("baseImage", "logPicture", "log"):
            (self.session_dir / sub).mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(self.session_dir / "baseImage" / "base.jpg"), base_frame)
        (self.session_dir / "meta.json").write_text(
            json.dumps(dataclasses.asdict(settings), indent=2) + "\n"
        )
        self._log_hour = None
        self._last_ref_save = 0.0
        return self.session_dir

    def latest_session(self) -> Optional[Path]:
        if not self.data_dir.exists():
            return None
        sessions = sorted(d for d in self.data_dir.iterdir() if d.is_dir())
        return sessions[-1] if sessions else None

    def resume(self, session_dir: Path) -> Optional[np.ndarray]:
        """Attach to an existing session; returns its base image if readable."""
        self.session_dir = session_dir
        self._log_hour = None
        base = session_dir / "baseImage" / "base.jpg"
        return cv2.imread(str(base)) if base.exists() else None

    # --- reference photos (§6.1) ---

    def maybe_save_reference(self, frame: np.ndarray, interval_s: float) -> bool:
        if self.session_dir is None:
            return False
        now = time.time()
        if now - self._last_ref_save < interval_s:
            return False
        self._last_ref_save = now
        name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".jpg"
        cv2.imwrite(
            str(self.session_dir / "logPicture" / name),
            frame,
            [cv2.IMWRITE_JPEG_QUALITY, 80],
        )
        return True

    # --- heatmapLog (§6.2) ---

    def _log_path(self, hour_key: str) -> Path:
        assert self.session_dir is not None
        return self.session_dir / "log" / f"heatmapLog_{hour_key}.jsonl"

    def log_detections(self, people: List[Detection], grid: HeatGrid) -> None:
        """Append a detection record; on entering a new hour, write a checkpoint
        record first so each hourly file replays standalone with continuity."""
        if self.session_dir is None:
            return
        now = datetime.now()
        hour_key = now.strftime("%Y-%m-%d_%H")
        path = self._log_path(hour_key)
        with path.open("a") as f:
            if hour_key != self._log_hour:
                self._log_hour = hour_key
                f.write(
                    json.dumps(
                        {
                            "type": "checkpoint",
                            "t": now.isoformat(timespec="milliseconds"),
                            "grid": grid.encode(),
                        }
                    )
                    + "\n"
                )
            f.write(
                json.dumps(
                    {
                        "type": "detection",
                        "t": now.isoformat(timespec="milliseconds"),
                        "people": [
                            {"x": round(x, 4), "y": round(y, 4), "conf": round(c, 3)}
                            for x, y, c in people
                        ],
                    }
                )
                + "\n"
            )

    # --- replay reads (§4.5) ---

    def available_hours(self) -> List[str]:
        if self.session_dir is None:
            return []
        log_dir = self.session_dir / "log"
        if not log_dir.exists():
            return []
        return sorted(
            p.stem.replace("heatmapLog_", "") for p in log_dir.glob("heatmapLog_*.jsonl")
        )

    def read_hour(self, hour_key: str) -> List[dict]:
        path = self._log_path(hour_key)
        records = []
        if path.exists():
            for line in path.read_text().splitlines():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # tolerate a torn final line from an unclean shutdown
        return records
