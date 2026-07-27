# canteenHeatMap

A camera-based occupancy heatmap system, designed to run on a Raspberry Pi with an attached
camera. It watches a space (e.g. an office lobby or canteen), detects people in the frame,
and builds an accumulating heatmap showing which areas get used, and when — like a weather
map, but for foot traffic.

## How it's meant to work

1. **Capture a base image** of the empty space. This becomes the visual backdrop the heatmap
   is drawn over, and starts a new session folder on disk.
2. **Detect people, not pixels.** Rather than raw frame-differencing (which is easily fooled
   by lighting changes, shadows, and glare), detection runs a lightweight object detector
   (a nano YOLO model, e.g. YOLO11n) filtered to the `person` class. Each detection's
   foot-point (bottom-center of its bounding box) is the location fed into the heatmap.
3. **Accumulate with decay.** Every detection deposits a small amount of "heat" around its
   position (Gaussian falloff), and the whole grid decays exponentially every tick — the
   same math as a leaky bucket / RC-circuit discharge. This is what makes the heatmap a
   *smoothed, time-windowed density* rather than an instant snapshot: a spot visited
   repeatedly stays warm; a one-off pass-through fades quickly. The configured **time frame**
   (default 10 minutes; also selectable up to 24h for quieter, low-traffic spaces like a
   warehouse overnight, where even a brief pass-through should stay visible longer) controls
   how fast that decay happens.
4. **Two ways to view it:**
   - **Live** — the heatmap and a "people in frame" sparkline update continuously.
   - **Replay** — pick a specific hour and scrub through just that hour's data (see below).

## Current status

The repo contains both:

- **The real Python application** (`canteen_heatmap/`) — camera capture, YOLO person
  detection, heat engine, hourly logging, replay, and a native pygame UI. Run it with
  `python -m canteen_heatmap.main` (see Quick start below).
- **An interactive HTML/JS UI mockup** (`mockup/lobby-heatmap-mockup.html`) used to work out
  the interaction design, kept up to date so it can still be used for **quick demos without
  starting the Python app** — it runs entirely client-side with a simulated occupancy model;
  open it directly in a browser, no server required.

## Quick start (Python app)

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m canteen_heatmap.main
```

Useful flags: `--demo` (start in demo mode), `--camera N` (camera index),
`--data-dir PATH` (where session folders are written; default `./data`).

On macOS, run from the Terminal app the first time so the camera permission prompt can
appear (grant it when asked).

## The mockup

The mockup's base image is a stylized illustrated scene drawn on a canvas — a real sample
photo lives at `mockup/source/sample-01/baseImage/mybase.jpg` as sample data for the real
system. The mockup demonstrates:
- Live heatmap rendered over the captured base scene, with smooth accumulate/decay (no raw
  frame-diff jitter)
- A "people in frame" sparkline (per-frame headcount over time) as a smooth line + area chart,
  synced to the replay scrubber
- Live / Replay mode switching. Replay works **by the hour** — pick an hour from a dropdown
  (each one standing in for one `heatmapLog_HH.jsonl` file) and scrub within it, with a
  playback speed control. Cross-hour replay is intentionally out of scope for now, kept simple.
- A dedicated **Settings** page (gear icon) covering:
  - Base image capture (starts a new session folder each time)
  - **Environment presets** (Canteen / Lobby / Warehouse) — one tap applies the time frame +
    confidence tuning that fits the space
  - Time frame (10m default / 1h / 3h / 6h / 24h / custom)
  - Detection confidence threshold
  - Save-reference-photos toggle (off by default) + interval
  - **Presentation**: Demo mode toggle, plus a min–max dual-range slider (1–50) controlling
    the simulated headcount range while Demo mode is on
  - Save-heat-log-to-disk toggle
- Keyboard shortcuts (`B` capture base, `L`/`R` live/replay, `Space` start/stop, `[`/`]` nudge
  replay time, `Esc` close settings)

## On-disk layout

Two very different things are captured, at two different rates, and neither is derived from
the other:

- **Reference photos** — a plain JPEG saved on an interval (5 s default) purely for visual
  context when reviewing a session. **Off by default**: the heatmapLog alone supports replay,
  and periodic photos are the biggest disk consumer on an SD card, so they're opt-in.
- **heatmapLog** — the actual extracted heat/motion data (positions + confidence, not images),
  which is what Replay is built from. Much smaller than images, and purpose-built for
  presentation rather than storage. Detection events are **consolidated into one record per
  5 seconds** (each record carries all positions seen in the window plus the peak headcount) —
  about 12× fewer lines than per-frame logging with the same replay quality. **One log file per
  hour.** When a new hour's log starts, its first record carries over the last state from the
  previous hour's log, so the heatmap doesn't visually reset at the hour boundary — activity
  decays continuously, it just happens to be filed into hourly chunks on disk.

Each base-image capture starts a new session folder so a session's photos and logs stay
together:

```
/var/heatmap/
  sample-01/                        # session folder, named on base-image capture
    baseImage/
      mybase.jpg
    logPicture/                     # empty unless "Save reference photos" is on
    log/
      heatmapLog_08.jsonl           # one file per hour; first record continues from
      heatmapLog_09.jsonl           # the previous hour's last state; one record / 5s
      ...
    meta.json                       # time frame, confidence threshold, capture interval used
```

## Tech stack

- **Capture**: OpenCV `VideoCapture` (Mac built-in camera for dev, USB webcam on Pi);
  `picamera2` planned for the Pi Camera Module
- **Detection**: YOLO11n (nano), person class only, motion-gated so the model only runs when
  something in frame actually changed; NCNN/TFLite export planned for Pi CPU performance
- **UI**: native pygame rendering (not a web app) — no browser or HTTP server; single
  no-scroll screen sized for a small Pi panel (see `docs/technical-instructions.md`)

## Repo layout

```
canteen_heatmap/                    # the Python application (see Quick start)
docs/
  technical-instructions.md         # full requirements & design spec
mockup/
  lobby-heatmap-mockup.html         # interactive UI mockup — open directly in a browser,
                                    # useful for demos without starting the Python app
  source/sample-01/
    baseImage/mybase.jpg            # sample base photo (not embedded in the mockup)
camera_test.py                      # minimal camera-permission test (macOS)
requirements.txt
```
