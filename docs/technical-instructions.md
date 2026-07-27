# Technical Instructions — canteenHeatMap

Status: **spec for the Python build.** Everything described here has been validated as an
interactive HTML/JS mockup (`mockup/lobby-heatmap-mockup.html`) — this document translates that
validated interaction design into requirements for the real, camera-driven implementation.

## 1. Purpose

Watch a space (canteen, lobby, warehouse aisle) with a camera on a Raspberry Pi, detect people in
frame, and build an accumulating heatmap of where activity concentrates and when — so someone can
answer "which areas actually get used, and at what times" without watching raw video. Not a
security/surveillance tool: no identity, no raw video retention, no recording of individuals —
only aggregated position density over time.

## 2. Deployment target & constraints

- **Hardware**: Raspberry Pi (assume Pi 4/5 class) with an attached camera (Pi Camera Module or
  USB webcam) and a **small local display**. *Open question: confirm exact screen — this doc
  assumes a compact landscape panel in the ~800×480–1024×600 range, touch-capable, no keyboard/
  mouse as the primary input.*
- **Consequence for compute**: no GPU to lean on. Detection must run a small model, at a modest
  rate, with headroom left for rendering the UI.
- **Not a web app.** The UI is a native Python process rendering directly to the attached screen —
  no browser, no HTTP server, no network round-trip in the render path. This keeps the whole stack
  a single local process and avoids a browser as an extra dependency on constrained hardware.
- **Consequence for storage**: SD card — writes should be minimized in both frequency and size
  (see §6). No assumption of network/cloud connectivity; the device should work fully offline.
- **Consequence for UI**: see §5. Screen space is scarce — no desktop-style multi-panel layout.

## 3. System architecture

```
┌─────────────┐    ┌──────────────┐    ┌────────────────┐    ┌──────────────┐
│   Capture   │ →  │   Detector   │ →  │  Heat Engine    │ →  │   Storage    │
│ (camera in) │    │ (YOLO,       │    │ (deposit+decay  │    │ (heatmapLog, │
│             │    │  person-only)│    │  grid, in-mem)  │    │  logPicture) │
└─────────────┘    └──────────────┘    └────────────────┘    └──────┬───────┘
                                               │                     │
                                               ▼                     ▼
                                        ┌─────────────────────────────────┐
                                        │        UI layer (local)         │
                                        │  Live view · Replay · Settings  │
                                        └─────────────────────────────────┘
```

Four independent concerns, each replaceable without touching the others:

1. **Capture** — pulls frames from the camera. Nothing else should know or care whether that's
   `picamera2` or OpenCV `VideoCapture`.
2. **Detector** — takes a frame, returns a list of `(x, y, confidence)` foot-points for detected
   people. Nothing else should know it's YOLO specifically.
3. **Heat engine** — pure in-memory state: a low-resolution grid, a deposit function, a decay
   function. Doesn't know about cameras, files, or the UI.
4. **Storage** — session folders, `heatmapLog` writing/reading, reference-photo saving, rotation.
   Doesn't know about detection internals, just consumes the same `(x, y, confidence)` events the
   heat engine consumes.

## 4. Functional requirements

### 4.1 Base image capture
- A user-triggered action captures one frame as the **base image** — the static visual backdrop
  the heatmap is drawn over for the rest of that session.
- Capturing a base image **starts a new session folder** (see §6) and **resets** the in-memory
  heat grid and any live agent/detection state. It does not affect previously written
  `heatmapLog` files — those stay as history.

### 4.2 Detection
- Runs a lightweight person detector (target: YOLO11n or YOLOv8n, "nano" tier) filtered to the
  `person` class only. Other COCO classes (chairs, tables, etc.) are not used for anything.
- Each detection contributes its **foot-point** — bottom-center of the bounding box — as the
  (x, y) fed to the heat engine. Bounding-box center is intentionally *not* used; foot-point maps
  to the floor plane much more accurately for a top-down-ish heatmap.
- Detection should be **motion-gated**: a cheap frame-difference check runs continuously as a
  trigger, and the heavier detector only runs when that trigger fires. This is a performance
  strategy for the Pi's CPU, not a data source — the motion-gate value itself is never stored or
  shown; only detector output feeds the heatmap.
- **Detection confidence threshold** is a user setting (default 45%, range 10–90%). Detections
  below threshold are discarded before reaching the heat engine.

### 4.3 Heat accumulation model
- A low-resolution grid (mockup uses 64×36; tune to taste, doesn't need to match camera
  resolution) holds a scalar "heat" value per cell.
- **Deposit**: each detection adds a small amount of heat in a Gaussian falloff around its
  foot-point, weighted by confidence.
- **Decay**: every tick, every cell's value is multiplied by a decay factor slightly below 1 —
  exponential decay, same math as a leaky bucket / RC-discharge. This is what makes the heatmap a
  time-windowed density rather than an instant snapshot.
- **Time frame** setting controls the decay rate — how long detected activity stays "remembered"
  before fading. Default **10 minutes**; also selectable: 1h, 3h, 6h, 24h, or custom. Shorter
  windows suit a canteen/lobby; a longer window suits a quiet space (e.g. a warehouse overnight)
  where even a brief, faint pass-through should stay visible longer rather than decaying away
  before anyone reviews it.
- Rendering: heat value → color (blue→green→yellow→red ramp) and → opacity, so zero heat is fully
  transparent (base image shows through untouched) and high heat is vivid. Keep the opacity floor
  high enough that mid-range values stay legible against a real photo's own colors — a real photo
  isn't a neutral backdrop like an illustration; low-contrast blending is a real failure mode to
  design against, not just an edge case (see mockup commit history for a concrete instance of
  this going wrong and the fix).

### 4.4 Live view
- Shows the current heat grid over the base image, updating continuously.
- Shows a **live headcount KPI** — current number of people in frame — updating in real time.
  This must **not** be a separate panel/section on the production screen (see §5): it merges into
  the same screen as the heatmap itself.

### 4.5 Replay
- Deliberately **scoped to a single hour at a time** — no cross-hour playback in this version.
  Simpler to build, simpler to reason about, and matches the storage model (§6) directly: one
  `heatmapLog` file = one hour = one replayable unit.
- User picks an hour (from whatever hourly log files actually exist on disk for the current
  session), then scrubs within it, with a play/pause and a playback-speed control.
- Background for replay is the **same base image**; the moving heat overlay is reconstructed from
  the selected hour's `heatmapLog`, not from stored images.

### 4.6 Demo mode
- A **Presentation** setting, off by default in real operation, on by default for demos: when
  enabled, the displayed activity is synthetic (guaranteed lively) rather than derived from actual
  camera detections — for presenting the tool to stakeholders in a room that may be empty or quiet
  at demo time.
- Synthetic headcount is drawn from a **configurable min–max range, 1 to 50**, adjustable via a
  dual-handle range control. Simulated positions should distribute across multiple zones (not one
  spot), and change smoothly over time rather than jumping — consistent with how the heat engine
  is designed to render everywhere else.
- Demo mode must be visually distinguishable from real data on-screen (the mockup uses a status
  toggle + explicit copy — carry that principle forward so nobody mistakes a demo run for a real
  reading).

### 4.7 Settings

| Setting | Default | Range / options | Notes |
|---|---|---|---|
| Environment preset | — | Canteen / Lobby / Warehouse | One-tap tuning bundle, see below |
| Time frame | 10 minutes | 10m / 1h / 3h / 6h / 24h / custom | Decay window (§4.3) |
| Detection confidence | 45% | 10–90% | Min confidence to accept a detection |
| Save reference photos | **off** | on/off | Off by default to save disk — see §6.1 |
| Reference image interval | 5s | 0.5s / 1s / 2s / 5s / 10s | Only applies when photos are on |
| Demo mode | off (real use) | on/off | See §4.6 |
| Demo headcount range | 3–9 | 1–50 (dual range) | Only active while Demo mode is on |
| Save heat log to disk | on | on/off | Turning off stops `heatmapLog` writes (Replay then has nothing new to show) |

**Environment presets** — the same engine serves very different spaces, differing mainly in
tuning. A preset applies a bundle in one tap rather than asking the operator to reason about
decay math:

| Preset | Time frame | Confidence | Rationale |
|---|---|---|---|
| Canteen | 10 min | 45% | Busy at meal times; short memory shows *current* usage |
| Lobby | 10 min | 50% | Crowded all day; slightly stricter to cut false positives |
| Warehouse | 6 h | 35% | Quiet overnight; a brief, faint pass-through must stay visible until security reviews it, and lower confidence catches partial/shadowed figures |

## 5. UI requirements — single-screen, Pi-appropriate

The desktop mockup spreads Live view, the "people in frame" sparkline, and Replay controls across
a tall, scrollable layout — appropriate for a browser window, **not appropriate for the Pi's
screen**. For the real build:

- **The heatmap and the people-in-frame KPI must live on the same screen, together, with no
  scrolling required.** Treat the KPI as an overlay/badge on the heatmap view itself (e.g. a
  compact stat chip in a corner showing the current count, optionally with a minimal inline
  sparkline), not a separate section stacked below the fold.
- Keep a persistent, compact status/mode strip (Live vs Replay, current hour when in Replay) —
  but as a thin strip, not the multi-row header the desktop mockup uses.
- Replay's hour-picker and scrubber should collapse into that same single screen when Replay is
  active, replacing (not stacking under) the live KPI — screen space is shared, not additive.
- Settings can remain a separate screen — it's not needed during normal glance-monitoring, so
  navigating away from the live view for it is acceptable, matching the mockup's gear-icon
  pattern.
- Design for touch as the primary input (tap targets sized accordingly), not for keyboard
  shortcuts — the mockup's `B`/`L`/`R`/`Space` shortcuts were a desktop-testing convenience, not a
  requirement to carry forward as the primary interaction model. Whether hardware buttons or
  touch-only is worth confirming once the actual screen/enclosure is decided.

## 6. Data & storage design

Two different things are captured, at two different rates, and neither is derived from the other:

### 6.1 Reference photos — off by default
Plain JPEGs saved on the **reference image interval** setting (default 5s), purely for visual
context when a person later reviews a session. **Saving them is off by default**: the heatmapLog
alone fully supports replay, so periodic photos are optional context, not required data — and on
an SD card they are by far the largest disk consumer, so the default favors disk life. When
enabled, the interval only controls what gets *written to disk* — detection itself runs
continuously in memory regardless. These images are never read back by the heat engine or Replay.

### 6.2 heatmapLog
The actual data Replay is built from — extracted detection events, not images. Much smaller than
photos, and purpose-built for the heat engine to reconstruct a grid, not for human viewing.

- **One file per hour**: `heatmapLog_HH.jsonl`.
- **Continuity across the hour boundary**: the first record of a new hour's log is a *checkpoint*
  carrying forward the grid/decay state from the end of the previous hour's log, so Replay of an
  hour never shows an artificial reset to zero at `:00` — activity decays continuously; it's only
  filed into hourly chunks on disk for manageability.
- **Consolidated records**: detection events are *not* written per detector tick (which could be
  several per second). They are buffered and written as **one record per 5-second window**: the
  record carries every foot-point observed in the window plus the peak concurrent headcount.
  This is ~12× fewer log lines than per-tick logging with no loss of replay quality, since Replay
  reconstructs at 5-second snapshot resolution anyway. Record shape (JSON Lines):

  ```json
  {"type": "checkpoint", "t": "2026-07-27T14:00:00Z", "grid": "<compact encoding of carried-over state>"}
  {"type": "sample", "t": "2026-07-27T14:00:05Z", "count": 3, "people": [{"x": 0.23, "y": 0.61, "conf": 0.82}, {"x": 0.24, "y": 0.6, "conf": 0.8}]}
  {"type": "sample", "t": "2026-07-27T14:00:10Z", "count": 0, "people": []}
  ```
  `count` is the peak *concurrent* headcount in the window (the `people` list holds all positions
  accumulated across the window, so its length overstates concurrency). Storing raw
  `(x, y, confidence)` events rather than pre-rendered dense grids keeps the log small and lets
  rendering parameters (decay rate, color ramp, grid resolution) change later without needing to
  have been baked in at capture time.

### 6.3 Session folder layout
Every base-image capture starts a new session folder, keeping a session's photos and logs
together:

```
/var/heatmap/
  <session-name>/                 # named on base-image capture, e.g. a timestamp
    baseImage/
      <base-image>.jpg
    logPicture/                   # empty unless "Save reference photos" is turned on
      2026-07-27_14-00-05.jpg     # reference photo on the configured interval, when enabled
      ...
    log/
      heatmapLog_14.jsonl         # one file per hour; first record continues
      heatmapLog_15.jsonl         # from the previous hour's last state
      ...
    meta.json                     # time frame, confidence threshold, capture interval used
```

### 6.4 Retention
Out of scope for this version beyond "don't let the disk fill silently": no cross-hour replay, no
automatic rollup/aggregation, no defined retention window yet. A disk-space guardrail (prune
oldest sessions if free space gets low) is a reasonable minimum before calling this
production-ready, even though the detailed policy isn't specified here.

## 7. Non-functional requirements

- Runs fully offline; no assumed network dependency for core operation.
- Detection + heat accumulation must keep pace on Pi CPU alone — motion-gating (§4.2) is the
  primary lever if the nano model alone isn't fast enough; an accelerator (Coral/Hailo) is a
  possible future addition, not assumed here.
- No raw video is retained; reference photos are periodic stills, not a video stream, and are not
  the basis for any detection or replay logic.
- UI must render acceptably on constrained Pi graphics — simple 2D compositing (base image + heat
  overlay + a handful of text/shape widgets), no GPU-heavy effects, no browser engine in the loop.

## 8. Proposed Python module layout

```
canteen_heatmap/
  capture.py       # camera frame acquisition (picamera2 / OpenCV), motion-gate check
  detector.py      # YOLO wrapper — load model, run inference, filter to person class + confidence
  heatmap.py       # grid state, deposit(), decay(), independent of camera/detector specifics
  storage.py       # session folder mgmt, heatmapLog read/write + hourly rotation/checkpointing,
                    # reference-photo saving on interval
  demo.py          # synthetic occupancy generator for Demo mode (port of the mockup's agent sim)
  config.py        # settings schema + defaults (table in §4.7), persisted to settings.json
  ui.py            # native on-screen rendering + touch/input handling — Live/Replay/Settings
                    # screens (§5), drawn directly to the display, no browser/HTTP involved
  main.py          # process entry point: wires capture → detector → heat engine → storage → ui.py
                    # into one loop
```

**UI toolkit choice (native, not web):** since `capture.py`/`detector.py` already work in terms of
raw frames (numpy arrays via OpenCV), the natural fit is a toolkit that can composite an image
buffer plus a few overlay widgets and read touch input directly, without pulling in a full desktop
widget stack:

- **Recommended: Pygame.** Draws the composited base+heat image plus KPI badge, mode strip, and
  Settings controls straight to the framebuffer/display; handles touch as pointer events; runs
  fullscreen kiosk-style with no window manager or browser required; easy to hand-roll the small,
  fixed set of widgets §5 actually needs (a handful of buttons/toggles/sliders, not a general
  form library).
- **Alternative: PyQt/PySide or Kivy** if the Settings screen ends up needing more polished,
  numerous widgets than is comfortable to hand-roll — heavier dependency, more setup on Pi, but
  real widget toolkits. Worth revisiting only if Pygame's hand-rolled controls start feeling
  limiting during implementation, not a blocker to starting.

## 9. Out of scope (this version)

- Cross-hour / multi-hour continuous replay
- Defined long-term retention/rollup policy
- Multi-camera support or any central aggregation server
- Cloud sync or remote access
- Hardware AI accelerator support (design should not preclude adding one later)

## 10. Open questions to confirm before/during implementation

1. Exact display hardware (size, resolution, touch vs. buttons) — assumed ~800×480–1024×600
   touch panel in §2/§5; confirm or correct.
2. Camera hardware: Pi Camera Module vs. USB webcam.
3. UI toolkit for the native renderer — Pygame is recommended (see §8) as the default; confirm or
   switch to PyQt/Kivy if Settings screen complexity outgrows hand-rolled widgets.
4. Disk retention policy specifics (§6.4) — needs a decision before this is production-ready, even
   though it's out of scope for the first implementation pass.
