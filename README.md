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

This repo currently contains an **interactive HTML/JS UI mockup** (`mockup/lobby-heatmap-mockup.html`)
used to work out the interaction design before writing the Python backend. It runs entirely
client-side with a simulated occupancy model standing in for real camera/detector input —
open it directly in a browser, no server required. The base image it renders is a stylized
illustrated scene, drawn on a canvas — a real sample photo was tried
(`mockup/source/sample-01/baseImage/mybase.jpg`) but swapped back out for now; that photo is
kept on disk as sample data for the real system.

The mockup demonstrates:
- Live heatmap rendered over the captured base scene, with smooth accumulate/decay (no raw
  frame-diff jitter)
- A "people in frame" sparkline (per-frame headcount over time) as a smooth line + area chart,
  synced to the replay scrubber
- Live / Replay mode switching. Replay works **by the hour** — pick an hour from a dropdown
  (each one standing in for one `heatmapLog_HH.jsonl` file) and scrub within it, with a
  playback speed control. Cross-hour replay is intentionally out of scope for now, kept simple.
- A dedicated **Settings** page (gear icon) covering:
  - Base image capture (starts a new session folder each time)
  - Time frame (10m default / 1h / 3h / 6h / 24h / custom)
  - Detection confidence threshold
  - Reference image interval (how often a plain photo gets written to disk — see below)
  - **Presentation**: Demo mode toggle, plus a min–max dual-range slider (1–50) controlling
    the simulated headcount range while Demo mode is on
  - Save-heat-log-to-disk toggle
- Keyboard shortcuts (`B` capture base, `L`/`R` live/replay, `Space` start/stop, `[`/`]` nudge
  replay time, `Esc` close settings)

The Python capture/detection engine has not been started yet.

## Planned on-disk layout

Two very different things are captured, at two different rates, and neither is derived from
the other:

- **Reference photos** — a plain JPEG saved every **5 seconds** (configurable) purely for
  visual context when reviewing a session. Detection itself compares frames continuously in
  memory at a much faster rate; this interval only controls what gets written to disk, so the
  folder doesn't fill up with near-duplicate images.
- **heatmapLog** — the actual extracted heat/motion data (positions + confidence, not images),
  which is what Replay is built from. Much smaller than images, and purpose-built for
  presentation rather than storage. **One log file per hour.** When a new hour's log starts,
  its first record carries over the last state from the previous hour's log, so the heatmap
  doesn't visually reset at the hour boundary — activity decays continuously, it just happens
  to be filed into hourly chunks on disk.

Each base-image capture starts a new session folder so a session's photos and logs stay
together:

```
/var/heatmap/
  sample-01/                        # session folder, named on base-image capture
    baseImage/
      mybase.jpg
    logPicture/
      2026-07-26_08-02-15.jpg       # reference photo, every 5s (default)
      2026-07-26_08-02-20.jpg
      ...
    log/
      heatmapLog_08.jsonl           # one file per hour; first record continues from
      heatmapLog_09.jsonl           # the previous hour's last state
      ...
    meta.json                       # time frame, confidence threshold, capture interval used
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
  lobby-heatmap-mockup.html         # interactive UI mockup, open directly in a browser
  source/sample-01/
    baseImage/mybase.jpg            # sample base photo (not currently embedded in the mockup)
    logPicture/                     # (empty — sample layout for reference photos)
    log/                            # (empty — sample layout for heatmapLog files)
```
