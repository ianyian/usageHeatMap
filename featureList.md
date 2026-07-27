# Feature List — Lobby Heatmap Console

Extracted from `mockup/lobby-heatmap-mockup.html`.  
Each section maps one-to-one to a planned Python/Flask module or component.

---

## 1. Top Bar

| Feature | HTML source | Python target |
|---|---|---|
| Device name & ID (camera name, IP, uptime) | `.device`, `.device-name`, `.device-id` | `config.py` — device name/IP; `system_info.py` — uptime |
| Stats readout: FPS, CPU °C, avg confidence | `#fpsVal`, `#cpuVal`, `#confVal` | `detector.py` exposes current fps + confidence; `system_info.py` exposes CPU temp |
| Live/Replay status pill + animated dot | `.status-pill`, `.status-dot`, `#statusText` | Flask SSE or WebSocket pushes `mode` state |
| Settings gear button | `#gearBtn` | Routes to `/settings` page or JS panel toggle |

---

## 2. Dashboard — Viewport

| Feature | HTML source | Python target |
|---|---|---|
| Live / Replay segmented button toggle | `#modeLiveBtn`, `#modeReplayBtn` | Client-side mode state; `/api/mode` endpoint to set backend mode |
| Keyboard shortcut hints (`L` `R` `Space`) | `.kbd-hint` | UI-only; no backend needed |

---

## 3. Dashboard — Heatmap Stage (Canvas)

| Feature | HTML source | Python target |
|---|---|---|
| Base image backdrop | `baseCanvas`, `drawBaseScene()` | `session.py` — load `baseImage/mybase.jpg` and serve via `/api/base-image` |
| Heatmap overlay (Gaussian deposit + exponential decay) | `deposit()`, `decay()`, `GW=64 GH=36` grid | `heat_engine.py` — `HeatGrid` class: `deposit(gx, gy, amount, radius)`, `decay(factor)` |
| Heat colour map (cool → warm, 5-stop gradient) | `colorForT()` | `heat_engine.py` — `color_for_t(t)` or rendered client-side from the raw grid data |
| Grid → blurred RGBA overlay | `paintGrid()`, `ctx.filter = 'blur(5px)'` | Client-side canvas rendering from grid data delivered via API |
| Stage badge (Live / Replay label) | `.stage-badge`, `#stageBadgeText` | Derived from mode state; pushed via SSE |
| Stage window label ("Accumulated · last 3h") | `#stageWindow`, `updateStageWindowLabel()` | Derived from `time_frame` config + current mode |
| Live timestamp clock | `#stageClock`, `tickClock()` | Client-side JS `Date`; no backend needed |
| Heat legend bar (Low → High) | `.stage-legend`, `.legend-bar` | Static CSS; no backend needed |

---

## 4. Dashboard — Sparkline Panel

| Feature | HTML source | Python target |
|---|---|---|
| "People in frame" live count | `#peopleNowVal` | `detector.py` — latest detection count; pushed via SSE |
| Per-frame headcount sparkline (smooth line + area) | `drawSparkline()`, `liveCounts[]` | `/api/counts` returns recent headcount list; rendered client-side |
| Playhead dot synced to replay scrubber | `playheadIdx` in `drawSparkline()` | Client-side; scrub position index into counts array returned by `/api/replay/<hour>` |

---

## 5. Dashboard — Hour Select Bar (Replay mode only)

| Feature | HTML source | Python target |
|---|---|---|
| Hour dropdown (one entry per `heatmapLog_HH.jsonl`) | `#hourSelect`, `populateHourSelect()` | `/api/replay/hours` — returns list of available hourly log files in the session folder |
| Log filename display | `#hourLogName` | Derived from selected hour; filename pattern `heatmapLog_HH.jsonl` |

---

## 6. Dashboard — Scrubber (Replay mode only)

| Feature | HTML source | Python target |
|---|---|---|
| Play / Pause button | `#playBtn`, `playing` flag | Client-side playback timer only |
| Scrub range slider + time labels (start, now, end) | `#scrubRange`, `#scrubStart`, `#scrubNow`, `#scrubEnd` | Client-side; position indexes into data from `/api/replay/<hour>` |
| Playback speed selector (1×, 4×, 15×, 60×) | `#speedSelect` | Client-side interval multiplier only |

---

## 7. Settings — Base Image Card

| Feature | HTML source | Python target |
|---|---|---|
| Base image thumbnail (captured / uncaptured state) | `.base-thumb`, `.base-thumb.captured` | `/api/base-image` — GET returns JPEG; captured state from `meta.json` |
| Capture timestamp + session folder name | `#baseTs`, `#sessionFolderLabel` | `session.py` — read from `meta.json` |
| "Recapture base image" button | `#captureBtn` | `POST /api/capture-base` — grabs a frame, saves `baseImage/mybase.jpg`, creates new session folder, writes `meta.json`, resets heat grid |

---

## 8. Settings — Session Card

| Feature | HTML source | Python target |
|---|---|---|
| Time frame selector (10m / 1h / 3h / 6h / 24h / custom) | `#timeframeSelect`, `currentTimeframeHours` | `POST /api/settings` with `time_frame_hours`; recalculates `decay_factor` in `heat_engine.py` |
| Custom date-range inputs | `#customFrom`, `#customTo` | Same endpoint; `custom_from` / `custom_to` ISO datetime strings |
| Detection confidence threshold slider (10–90%) | `#sensRange`, `depositScale` | `POST /api/settings` with `confidence_threshold`; applied in `detector.py` filter |
| Reference image interval selector (0.5s – 10s) | `#captureIntervalSelect` | `POST /api/settings` with `capture_interval_seconds`; controls `logPicture/` write timer in `capture_loop.py` |
| Save heat log to disk toggle | `#saveToggle` | `POST /api/settings` with `save_log: bool`; enables/disables `heatmapLog` writes in `log_writer.py` |

---

## 9. Settings — Presentation Card

| Feature | HTML source | Python target |
|---|---|---|
| Demo mode toggle | `#demoToggle`, `demoMode` flag | `POST /api/settings` with `demo_mode: bool`; backend switches between real detector output and simulated agent output |
| Demo headcount dual-range slider (1–50, min + max) | `#demoMinRange`, `#demoMaxRange`, `demoMin`, `demoMax` | `POST /api/settings` with `demo_min`, `demo_max`; consumed by `demo_agent.py` occupancy target |

---

## 10. Settings — Keyboard Shortcuts Card

| Shortcut | Action | Python target |
|---|---|---|
| `B` | Capture base image | Triggers same as `POST /api/capture-base` |
| `L` | Switch to Live | Client-side mode switch |
| `R` | Switch to Replay | Client-side mode switch |
| `Space` | Start / stop playback | Client-side scrubber play/pause |
| `[` / `]` | Nudge replay time | Client-side scrub position ±1 |
| `Esc` | Close settings | Client-side panel close |

---

## 11. Footer / Bottom Bar

| Feature | HTML source | Python target |
|---|---|---|
| Detector info (model, class, min confidence) | `footer.bottombar`, `#threshEcho` | Populated from `meta.json` / live settings |
| Session path + reference photo count | `#footerRight` | `/api/session-status` — returns `session_folder`, `photo_count` |

---

## 12. Toast Notifications

| Feature | HTML source | Python target |
|---|---|---|
| Short auto-dismiss toast on actions | `#toast`, `showToast()` | Client-side only; triggered by API response messages |

---

## 13. Heat Accumulation Engine

| Feature | HTML source | Python target |
|---|---|---|
| Low-resolution heat grid (64 × 36 cells) | `GW=64`, `GH=36`, `newGrid()` | `heat_engine.py` — `HeatGrid(width=64, height=36)`, internal `numpy.ndarray float32` |
| Gaussian deposit at detection foot-point | `deposit(grid, gx, gy, amount, radius)` | `HeatGrid.deposit(gx, gy, amount=0.012, radius=3.1)` |
| Exponential decay per tick | `decay(grid, factor)` | `HeatGrid.decay(factor)` — `grid *= factor` |
| Decay factor derived from time frame | `hoursToTau(hours)`: `60 + 360 * sqrt(hours)` | `heat_engine.compute_decay_factor(time_frame_hours, fps)` |
| Grid → colour RGBA image for overlay | `paintGrid()`, `colorForT()` | `heat_engine.to_rgba_image(grid)` — returns `numpy uint8 (H, W, 4)` |
| Bilinear interpolation between snapshots (replay scrub) | `lerpGrids(a, b, f)` | `heat_engine.lerp_grids(a, b, f)` |

---

## 14. Simulated Agent Model (Demo Mode)

| Feature | HTML source | Python target |
|---|---|---|
| Agent state machine: `toCounter → atCounter → toTable → atTable → toExit → done` | `makeAgent()`, `stepAgent()` | `demo_agent.py` — `Agent` dataclass + `step_agent(agent, grid, rnd)` |
| Smooth easing toward target (no teleport) | `agent.gx += (agent.tx - agent.gx) * 0.035` | Same easing in `step_agent()` |
| Seeded random for reproducibility | `seededRandom(seed)` | `random.Random(seed)` or `numpy.random.default_rng(seed)` |
| Occupancy target waveform (two-frequency wobble) | `occupancyTarget(t)` | `demo_agent.occupancy_target(t, demo_min, demo_max, demo_mode)` |
| Configurable headcount range (min, max) | `demoMin`, `demoMax` | `demo_agent.py` — `DemoConfig(min=3, max=9)` |

---

## 15. Replay Engine

| Feature | HTML source | Python target |
|---|---|---|
| 6 hourly buckets, one per `heatmapLog_HH.jsonl` | `REPLAY_HOURS=6`, `hourBuckets[]` | `replay.py` — `list_hourly_logs(session_folder)` returns sorted list |
| Snapshot interpolation within an hour | `currentGrid()`, `lerpGrids()` | `replay.py` — `load_hour(path)` returns list of grid snapshots; interpolation is client-side or via `/api/replay/<hour>?pct=<0-100>` |
| History pre-roll; last state carries over to next hour | `generateHistory()` | `log_writer.py` — first record of each new hourly log copies last grid state from previous log |
| 25 snapshots per hour stored | `SNAPSHOTS_PER_HOUR=25` | `log_writer.py` — configurable snapshot interval |

---

## 16. On-Disk Layout

```
/var/heatmap/                          # root data directory (configurable)
  <session_folder>/                    # named on base-image capture: session_YYYY-MM-DD_HH-MM-SS
    baseImage/
      mybase.jpg                       # captured base photo
    logPicture/
      YYYY-MM-DD_HH-MM-SS.jpg          # reference photo, every N seconds (default 5s)
    log/
      heatmapLog_HH.jsonl              # one file per hour; first record = last state of prev hour
    meta.json                          # time_frame_hours, confidence_threshold, capture_interval_s
```

---

## 17. Flask API Endpoints (planned)

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serve dashboard HTML |
| `GET` | `/api/base-image` | Return current session's base JPEG |
| `POST` | `/api/capture-base` | Capture frame → save base image, create session folder, reset grid |
| `GET` | `/api/session-status` | Return `session_folder`, `photo_count`, `mode`, `meta` |
| `GET` | `/api/counts` | Return recent per-frame headcount list (live window) |
| `GET` | `/api/replay/hours` | Return list of available hourly log files |
| `GET` | `/api/replay/<hour>` | Return grid snapshots + counts for specified hour |
| `POST` | `/api/settings` | Update time frame, confidence, capture interval, save toggle, demo mode |
| `GET` | `/api/stream` | SSE stream: live grid state, current headcount, fps, cpu, status |

---

## 18. Theme / UI

| Feature | HTML source | Python target |
|---|---|---|
| Dark theme (default) + light theme | CSS `--bg`, `--panel`, etc. + `data-theme` attribute | Static CSS in Flask `static/`; theme toggle is client-side only |
| `prefers-color-scheme` auto-detect | `@media (prefers-color-scheme: light)` | CSS only |
| Reduced-motion respect | `@media (prefers-reduced-motion: no-preference)` | CSS only |
