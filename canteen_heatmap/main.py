"""Process entry point: wires capture → detector → heat engine → storage → UI (§8).

Run from the repo root:  python -m canteen_heatmap.main
Dev/testing uses the machine's default camera (MacBook built-in = index 0);
the same code path serves a USB webcam on the Pi.
"""
import argparse
import sys
import time
from collections import deque
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pygame

from . import config
from .capture import Camera, MotionGate
from .config import REF_INTERVAL_CHOICES, TIME_FRAME_CHOICES, Settings
from .demo import DemoSimulator
from .heatmap import HeatGrid
from .replay import HOUR_S, HourReplay
from .storage import SessionStore
from .ui import UI, cover_fit

DETECT_INTERVAL_S = 0.4     # max detector rate; motion gate can make it rarer
SPARKLINE_SAMPLES = 120     # ~1 minute of headcount history at 2 Hz
SPARKLINE_PERIOD_S = 0.5
REPLAY_SPEEDS = [1, 4, 16, 60]


class App:
    def __init__(self, settings: Settings, settings_dir: Path):
        self.settings = settings
        self.settings_dir = settings_dir
        self.ui = UI(settings.screen_w, settings.screen_h)
        self.store = SessionStore(Path(settings.data_dir))
        self.heat = HeatGrid(settings.grid_w, settings.grid_h, settings.time_frame_hours)
        self.demo = DemoSimulator()
        self.gate = MotionGate()

        self.view = "main"           # "main" | "settings"
        self.mode = "live"           # "live" | "replay"
        self.base_surface: Optional[pygame.Surface] = None
        self.last_frame: Optional[np.ndarray] = None
        self.count = 0
        self.spark: deque = deque(maxlen=SPARKLINE_SAMPLES)
        self._last_spark = 0.0
        self._last_detect = 0.0
        self._last_tick = time.time()

        # Replay state
        self.replay_hours: List[str] = []
        self.replay_index = 0
        self.replay_data: Optional[HourReplay] = None
        self.replay_pos = 0.0
        self.replay_playing = False
        self.replay_speed = REPLAY_SPEEDS[0]

        print("Opening camera…", flush=True)
        try:
            self.camera: Optional[Camera] = Camera(settings.camera_index)
        except RuntimeError as e:
            # Run anyway: demo mode and replay work without a camera, and this
            # keeps the Pi from crash-looping on an unplugged/blocked camera.
            print(f"warning: {e}", file=sys.stderr, flush=True)
            self.camera = None
            self.ui.flash("Camera unavailable — demo/replay only")
        print("Loading detector model…", flush=True)
        from .detector import PersonDetector
        self.detector = PersonDetector()
        print("Ready.", flush=True)

        latest = self.store.latest_session()
        if latest is not None:
            base = self.store.resume(latest)
            if base is not None:
                self.base_surface = cover_fit(base, self.ui.w, self.ui.h)
                self.ui.flash(f"Resumed session {latest.name}")

    # ---------------------------------------------------------------- UI facade

    def display_grid(self) -> Optional[np.ndarray]:
        if self.mode == "replay":
            return self.replay_data.at(self.replay_pos) if self.replay_data else None
        return self.heat.grid

    def current_count(self) -> int:
        if self.mode == "replay":
            return self.replay_data.count_at(self.replay_pos) if self.replay_data else 0
        return self.count

    def sparkline_values(self) -> List[int]:
        if self.mode == "replay":
            if not self.replay_data:
                return []
            i = int(self.replay_pos / HOUR_S * (len(self.replay_data) - 1))
            return self.replay_data.counts[: max(2, i + 1) : 4]
        return list(self.spark)

    def replay_hour_label(self) -> str:
        if not self.replay_hours:
            return "no data"
        return self.replay_hours[self.replay_index][-2:] + ":00"

    def on_button(self, bid: str) -> None:
        s = self.settings
        if bid == "capture":
            self.capture_base()
        elif bid == "mode_live":
            self.mode = "live"
            self.replay_playing = False
        elif bid == "mode_replay":
            self.enter_replay()
        elif bid == "settings":
            self.view = "settings"
        elif bid == "back":
            self.view = "main"
            self.save_settings()
        elif bid == "hour_prev":
            self.select_hour(self.replay_index - 1)
        elif bid == "hour_next":
            self.select_hour(self.replay_index + 1)
        elif bid == "play":
            self.replay_playing = not self.replay_playing
        elif bid == "speed":
            i = REPLAY_SPEEDS.index(self.replay_speed)
            self.replay_speed = REPLAY_SPEEDS[(i + 1) % len(REPLAY_SPEEDS)]
        elif bid == "toggle_log":
            s.save_heat_log = not s.save_heat_log
        elif bid == "toggle_demo":
            s.demo_mode = not s.demo_mode
        elif bid.startswith("tf_"):
            s.time_frame_hours = TIME_FRAME_CHOICES[int(bid[3:])][1]
            self.heat.set_time_frame(s.time_frame_hours)
        elif bid.startswith("ref_"):
            s.reference_interval_s = REF_INTERVAL_CHOICES[int(bid[4:])]

    def on_slider(self, sid: str, value: float) -> None:
        s = self.settings
        if sid == "conf":
            s.confidence_threshold = round(value, 2)
        elif sid == "demo_min":
            s.demo_min = int(round(value))
            s.demo_max = max(s.demo_max, s.demo_min)
        elif sid == "demo_max":
            s.demo_max = int(round(value))
            s.demo_min = min(s.demo_min, s.demo_max)
        elif sid == "scrub":
            self.replay_pos = value
            self.replay_playing = False

    # ---------------------------------------------------------------- actions

    def capture_base(self) -> None:
        if self.last_frame is None:
            self.ui.flash("No camera frame yet")
            return
        session = self.store.new_session(self.last_frame, self.settings)
        self.base_surface = cover_fit(self.last_frame, self.ui.w, self.ui.h)
        self.heat.reset()
        self.spark.clear()
        self.ui.flash(f"New session: {session.name}")

    def enter_replay(self) -> None:
        self.replay_hours = self.store.available_hours()
        if not self.replay_hours:
            self.ui.flash("No heatmap log recorded yet")
            return
        self.mode = "replay"
        self.select_hour(len(self.replay_hours) - 1)

    def select_hour(self, index: int) -> None:
        if not self.replay_hours:
            return
        self.replay_index = index % len(self.replay_hours)
        hour_key = self.replay_hours[self.replay_index]
        records = self.store.read_hour(hour_key)
        self.replay_data = HourReplay(
            hour_key, records, self.settings.grid_w, self.settings.grid_h,
            self.settings.time_frame_hours,
        )
        self.replay_pos = 0.0
        self.replay_playing = False

    def save_settings(self) -> None:
        config.save(self.settings.clamp(), self.settings_dir)

    # ---------------------------------------------------------------- main loop

    def tick_live(self, now: float, dt: float) -> None:
        if self.camera is not None:
            frame = self.camera.read()
            if frame is not None:
                self.last_frame = frame

        self.heat.decay(dt)

        if now - self._last_detect >= DETECT_INTERVAL_S:
            people: List[Tuple[float, float, float]] = []
            ran_detector = False
            if self.settings.demo_mode:
                people = self.demo.tick(self.settings.demo_min, self.settings.demo_max)
                ran_detector = True
            elif self.last_frame is not None and self.gate.triggered(self.last_frame):
                people = self.detector.detect(
                    self.last_frame, self.settings.confidence_threshold
                )
                ran_detector = True
            if ran_detector:
                self._last_detect = now
                self.count = len(people)
                self.heat.add_detections(people)
                if self.settings.save_heat_log and self.store.session_dir is not None:
                    self.store.log_detections(people, self.heat)

        if self.store.session_dir is not None and self.last_frame is not None:
            self.store.maybe_save_reference(
                self.last_frame, self.settings.reference_interval_s
            )

        if now - self._last_spark >= SPARKLINE_PERIOD_S:
            self._last_spark = now
            self.spark.append(self.count)

    def tick_replay(self, dt: float) -> None:
        if self.replay_playing:
            self.replay_pos += dt * self.replay_speed
            if self.replay_pos >= HOUR_S:
                self.replay_pos = HOUR_S
                self.replay_playing = False

    snapshot_path: Optional[str] = None

    def run(self) -> None:
        clock = pygame.time.Clock()
        running = True
        last_snap = 0.0
        while running:
            now = time.time()
            dt = min(0.5, now - self._last_tick)
            self._last_tick = now
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if self.view == "settings":
                        self.view = "main"
                        self.save_settings()
                    else:
                        running = False
                else:
                    self.ui.handle(self, event)

            if self.mode == "live":
                self.tick_live(now, dt)
            else:
                self.tick_replay(dt)

            self.ui.draw(self)
            if self.snapshot_path and now - last_snap >= 5.0:
                last_snap = now
                pygame.image.save(self.ui.screen, self.snapshot_path)
            clock.tick(30)

        self.save_settings()
        if self.camera is not None:
            self.camera.release()
        pygame.quit()


def main() -> None:
    parser = argparse.ArgumentParser(description="canteenHeatMap — occupancy heatmap")
    parser.add_argument("--camera", type=int, default=None,
                        help="camera index (0 = built-in/first camera)")
    parser.add_argument("--data-dir", type=str, default=None,
                        help="where session folders are written (default: ./data)")
    parser.add_argument("--demo", action="store_true",
                        help="start with demo mode enabled")
    parser.add_argument("--snapshot", type=str, default=None,
                        help="dev aid: save a PNG of the screen to this path every 5s")
    args = parser.parse_args()

    settings_dir = Path(args.data_dir) if args.data_dir else Path("data")
    settings = config.load(settings_dir)
    if args.camera is not None:
        settings.camera_index = args.camera
    if args.data_dir is not None:
        settings.data_dir = args.data_dir
    if args.demo:
        settings.demo_mode = True

    try:
        app = App(settings, settings_dir)
        app.snapshot_path = args.snapshot
        app.run()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
