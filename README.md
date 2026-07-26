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
   repeatedly stays warm; a one-off pass-through fades quickly. The configured time frame
   (default 3h) controls how fast that decay happens.
4. **Two ways to view it:**
   - **Live** — the heatmap and a "people in frame" sparkline update continuously.
   - **Replay** — scrub back through the configured time window to see how the space filled
     up and emptied out over time.

## Current status

This repo currently contains an **interactive HTML/JS UI mockup** (`mockup/lobby-heatmap-mockup.html`)
used to work out the interaction design before writing the Python backend. It runs entirely
client-side with a simulated occupancy model standing in for real camera/detector input —
open it directly in a browser, no server required.

The mockup demonstrates:
- Live heatmap rendered over a captured base image, with smooth accumulate/decay (no raw
  frame-diff jitter)
- A "people in frame" sparkline (per-frame headcount over time), synced to the replay scrubber
- Live / Replay mode switching, with a scrubber + playback speed control for replay
- A dedicated **Settings** page (gear icon) covering:
  - Base image capture (starts a new session folder each time)
  - Time frame (1h / 3h / 6h / 24h / custom)
  - Detection confidence threshold
  - Image capture interval (how often a frame gets written to disk — see below)
  - **Demo mode** — forces lively simulated activity for presentations, regardless of actual
    room occupancy
  - Save-heat-log-to-disk toggle
- Keyboard shortcuts (`B` capture base, `L`/`R` live/replay, `Space` start/stop, `[`/`]` nudge
  replay time, `Esc` close settings)

The Python capture/detection engine has not been started yet.

## Planned on-disk layout

Detection runs continuously in memory, but only one photo is written to disk per the
configured capture interval (default 1s) — a lobby doesn't move fast enough to need finer
resolution, and it keeps the session folder from filling up with near-duplicate frames.
Each base-image capture starts a new session folder so a session's photos and logs stay
together:

```
/var/heatmap/
  session_2026-07-25_08-02-14/
    base.jpg
    frame_2026-07-25_08-02-15.jpg
    frame_2026-07-25_08-02-16.jpg
    ...
    heat_log.jsonl      # accumulated heat grid snapshots, for Replay
    meta.json           # time frame, confidence threshold, capture interval used
```

## Planned tech stack

- **Capture**: `picamera2` (Pi Camera Module) or OpenCV `VideoCapture` (USB webcam)
- **Detection**: nano YOLO model (YOLO11n / YOLOv8n), exported to NCNN or TFLite for
  reasonable CPU performance on a Pi; motion-gated so the model only runs when something in
  frame actually changed, rather than continuously
- **Web UI**: Flask, serving the same Live/Replay/Settings interface prototyped in the mockup

## Repo layout

```
mockup/
  lobby-heatmap-mockup.html   # interactive UI mockup, open directly in a browser
```
