"""Settings schema, defaults and JSON persistence (technical-instructions §4.7)."""
import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILENAME = "settings.json"

TIME_FRAME_CHOICES = [
    ("10 min", 10 / 60),
    ("1 h", 1.0),
    ("3 h", 3.0),
    ("6 h", 6.0),
    ("24 h", 24.0),
]

REF_INTERVAL_CHOICES = [0.5, 1.0, 2.0, 5.0, 10.0]

# Per-environment presets: one tap in Settings applies the tuning that fits the
# space. Warehouse keeps a long time frame so an overnight pass-through stays
# visible until security reviews it; lobby/canteen use short memory.
ENV_PRESETS = {
    "canteen": {"time_frame_hours": 10 / 60, "confidence_threshold": 0.45},
    "lobby": {"time_frame_hours": 10 / 60, "confidence_threshold": 0.50},
    "warehouse": {"time_frame_hours": 6.0, "confidence_threshold": 0.35},
}


@dataclass
class Settings:
    # Heat decay window, in hours. After this long, deposited heat is down to ~5%.
    time_frame_hours: float = 10 / 60
    # Detections below this confidence are discarded before the heat engine.
    confidence_threshold: float = 0.45
    # Reference photos are OFF by default — the heatmapLog alone supports replay,
    # and periodic JPEGs are the biggest disk consumer on an SD card.
    save_reference_photos: bool = False
    # How often a reference JPEG is written to logPicture/ (seconds), when enabled.
    reference_interval_s: float = 5.0
    save_heat_log: bool = True
    demo_mode: bool = False
    demo_min: int = 3
    demo_max: int = 9
    # Camera index: 0 = MacBook built-in / first camera.
    camera_index: int = 0
    # Where session folders are created. /var/heatmap on the Pi; local dir for dev.
    data_dir: str = "data"
    grid_w: int = 64
    grid_h: int = 36
    # Screen size the native UI targets (Pi panel class; also fine as a Mac window).
    screen_w: int = 1024
    screen_h: int = 600

    def clamp(self) -> "Settings":
        self.confidence_threshold = min(0.9, max(0.1, self.confidence_threshold))
        self.demo_min = min(50, max(1, self.demo_min))
        self.demo_max = min(50, max(self.demo_min, self.demo_max))
        self.time_frame_hours = max(1 / 60, self.time_frame_hours)
        return self


def config_path(settings_dir: Path) -> Path:
    return settings_dir / CONFIG_FILENAME


def load(settings_dir: Path) -> Settings:
    path = config_path(settings_dir)
    s = Settings()
    if path.exists():
        try:
            data = json.loads(path.read_text())
            known = {f.name for f in dataclasses.fields(Settings)}
            for k, v in data.items():
                if k in known:
                    setattr(s, k, v)
        except (json.JSONDecodeError, OSError):
            pass  # fall back to defaults rather than refusing to start
    return s.clamp()


def save(settings: Settings, settings_dir: Path) -> None:
    settings_dir.mkdir(parents=True, exist_ok=True)
    config_path(settings_dir).write_text(
        json.dumps(dataclasses.asdict(settings), indent=2) + "\n"
    )
