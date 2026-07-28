"""Native pygame UI (§5): single screen, layered overlays, no browser.

Visual language: dark "glass" panels (translucent, rounded, hairline border) floating
over the full-bleed camera/heatmap view, so the stream stays maximized. Layers on the
live screen, bottom to top:

  1. base image (captured backdrop)
  2. heat overlay
  3. chart strip — live line chart of detected people per second (last 60 s), with
     the current headcount as the KPI merged into the same strip
  4. mode pill, demo badge, control pills, transparent shortcut hints

In replay, the chart strip becomes the hour timeline: the whole hour's headcount as
a chart, click/drag anywhere on it to seek, with a playhead line.
Immediate-mode widgets: draw() rebuilds hit rects each frame; handle() tests them.
"""
import time
from typing import List, Optional, Tuple

import cv2
import numpy as np
import pygame

from .config import ENV_PRESETS, REF_INTERVAL_CHOICES, TIME_FRAME_CHOICES
from .heatmap import render_overlay
from .replay import HOUR_S

PAD = 14
STRIP_H = 96          # bottom chart strip
RADIUS = 14

C_BG = (11, 15, 21)
C_GLASS = (10, 14, 22, 158)          # translucent panel fill
C_GLASS_SOLID = (17, 22, 30, 236)    # settings cards
C_EDGE = (255, 255, 255, 26)         # hairline border
C_TEXT = (235, 240, 246)
C_FAINT = (148, 160, 174)
C_GHOST = (255, 255, 255, 90)        # transparent hint text
C_ACCENT = (77, 163, 255)
C_ACCENT_DIM = (77, 163, 255, 60)
C_OK = (74, 222, 128)
C_WARN = (251, 191, 36)
C_DANGER = (248, 113, 113)


def cover_fit(frame_bgr: np.ndarray, w: int, h: int) -> pygame.Surface:
    """Scale + center-crop a BGR frame to exactly (w, h) without distortion."""
    fh, fw = frame_bgr.shape[:2]
    scale = max(w / fw, h / fh)
    resized = cv2.resize(frame_bgr, (int(fw * scale) + 1, int(fh * scale) + 1))
    y0 = (resized.shape[0] - h) // 2
    x0 = (resized.shape[1] - w) // 2
    crop = resized[y0 : y0 + h, x0 : x0 + w]
    rgb = cv2.cvtColor(np.ascontiguousarray(crop), cv2.COLOR_BGR2RGB)
    return pygame.image.frombuffer(rgb.tobytes(), (w, h), "RGB")


def heat_surface(grid: np.ndarray, w: int, h: int) -> pygame.Surface:
    rgba = render_overlay(grid)
    half = cv2.resize(rgba, (w // 2, h // 2), interpolation=cv2.INTER_CUBIC)
    half = cv2.GaussianBlur(half, (9, 9), 0)
    surf = pygame.image.frombuffer(np.ascontiguousarray(half).tobytes(),
                                   (w // 2, h // 2), "RGBA")
    return pygame.transform.smoothscale(surf, (w, h))


class UI:
    def __init__(self, w: int, h: int):
        pygame.init()
        pygame.display.set_caption("canteenHeatMap")
        self.w, self.h = w, h
        self.screen = pygame.display.set_mode((w, h))
        base = "avenirnext,helveticaneue,segoeui,dejavusans,arial"
        self.font = pygame.font.SysFont(base, 16)
        self.font_sm = pygame.font.SysFont(base, 13)
        self.font_label = pygame.font.SysFont(base, 12, bold=True)
        self.font_big = pygame.font.SysFont(base, 42, bold=True)
        self.font_h1 = pygame.font.SysFont(base, 26, bold=True)
        self._buttons: List[Tuple[pygame.Rect, str]] = []
        self._sliders: List[Tuple[pygame.Rect, str, float, float]] = []
        self._drag: Optional[str] = None
        self._flash: Optional[Tuple[str, float]] = None

    # ------------------------------------------------------------------ helpers

    def flash(self, msg: str) -> None:
        self._flash = (msg, time.time() + 2.5)

    def _text(self, s, font, color, pos, anchor="topleft"):
        img = font.render(s, True, color[:3])
        if len(color) == 4:  # emulate alpha for ghost text
            img.set_alpha(color[3])
        r = img.get_rect(**{anchor: pos})
        self.screen.blit(img, r)
        return r

    def _glass(self, rect: pygame.Rect, fill=C_GLASS, radius=RADIUS, edge=True):
        s = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(s, fill, s.get_rect(), border_radius=radius)
        if edge:
            pygame.draw.rect(s, C_EDGE, s.get_rect(), 1, border_radius=radius)
        self.screen.blit(s, rect)

    def _pill(self, rect: pygame.Rect, label: str, bid: str, active=False,
              accent=False):
        radius = rect.h // 2
        if active or accent:
            fill = (31, 76, 128, 235) if active else (38, 48, 62, 200)
        else:
            fill = (20, 26, 35, 165)
        s = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(s, fill, s.get_rect(), border_radius=radius)
        pygame.draw.rect(s, (C_ACCENT if active else C_EDGE[:3]) + ((150,) if active else (C_EDGE[3],)),
                         s.get_rect(), 1, border_radius=radius)
        self.screen.blit(s, rect)
        self._text(label, self.font_sm, C_TEXT if active else C_FAINT,
                   rect.center, "center")
        self._buttons.append((rect, bid))

    def _slider(self, rect: pygame.Rect, sid: str, value: float, lo: float, hi: float,
                label: str, fmt: str):
        self._text(label, self.font_sm, C_FAINT, (rect.x, rect.y - 20))
        self._text(fmt, self.font_sm, C_TEXT, (rect.right, rect.y - 20), "topright")
        track = pygame.Rect(rect.x, rect.centery - 2, rect.w, 4)
        pygame.draw.rect(self.screen, (44, 54, 66), track, border_radius=2)
        t = (value - lo) / (hi - lo)
        pygame.draw.rect(self.screen, C_ACCENT,
                         pygame.Rect(rect.x, rect.centery - 2, int(rect.w * t), 4),
                         border_radius=2)
        knob = (rect.x + int(rect.w * t), rect.centery)
        pygame.draw.circle(self.screen, C_TEXT, knob, 8)
        pygame.draw.circle(self.screen, C_ACCENT, knob, 8, 2)
        self._sliders.append((rect.inflate(0, 26), sid, lo, hi))

    def _chart(self, rect: pygame.Rect, values: List[int], playhead: Optional[float],
               vmax_floor: int = 4):
        """Area + line chart inside rect; playhead is 0..1 across the width."""
        if len(values) >= 2:
            vmax = max(vmax_floor, max(values))
            pts = [
                (rect.x + i * rect.w / (len(values) - 1),
                 rect.bottom - 4 - (v / vmax) * (rect.h - 10))
                for i, v in enumerate(values)
            ]
            s = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            pygame.draw.polygon(
                s, C_ACCENT_DIM,
                [(rect.x, rect.bottom)] + pts + [(pts[-1][0], rect.bottom)],
            )
            self.screen.blit(s, (0, 0))
            if len(pts) >= 2:
                pygame.draw.aalines(self.screen, C_ACCENT, False, pts)
                pygame.draw.aalines(self.screen, C_ACCENT, False,
                                    [(x, y - 1) for x, y in pts])
        if playhead is not None:
            px = rect.x + int(rect.w * playhead)
            pygame.draw.line(self.screen, C_TEXT, (px, rect.y + 2),
                             (px, rect.bottom - 2), 2)

    # ------------------------------------------------------------------ drawing

    def draw(self, app) -> None:
        self._buttons.clear()
        self._sliders.clear()
        self.screen.fill(C_BG)
        if app.view == "settings":
            self._draw_settings(app)
        else:
            self._draw_main(app)
        self._draw_flash()
        pygame.display.flip()

    def _draw_main(self, app) -> None:
        # Layer 1 + 2: backdrop and heat
        if app.base_surface is not None:
            self.screen.blit(app.base_surface, (0, 0))
        grid = app.display_grid()
        if grid is not None:
            self.screen.blit(heat_surface(grid, self.w, self.h), (0, 0))

        # Layer 3: chart strip
        strip = pygame.Rect(PAD, self.h - STRIP_H - PAD, self.w - PAD * 2, STRIP_H)
        self._glass(strip)
        if app.mode == "live":
            self._draw_live_strip(app, strip)
        else:
            self._draw_replay_strip(app, strip)

        # Layer 4: pills and hints
        self._draw_top_bar(app)
        if app.base_surface is None:
            self._text("No base image — press B or open Settings to capture one",
                       self.font, C_TEXT, (self.w // 2, self.h // 2 - 30), "center")
        status = getattr(app, "startup_status", None)
        if status:
            r = pygame.Rect(0, 0, 260, 34)
            r.midtop = (self.w // 2, PAD + 44)
            self._glass(r, radius=17)
            self._text(status, self.font_sm, C_FAINT, r.center, "center")
        hint = ("B base   L live   R replay   D demo   S settings   ESC quit"
                if app.mode == "live" else
                "SPACE play/pause   < > keys seek 1 min   L live   ESC quit")
        self._text(hint, self.font_sm, C_GHOST, (PAD + 6, strip.y - 24))

    def _draw_top_bar(self, app) -> None:
        # Mode pill
        live = app.mode == "live"
        label = "LIVE" if live else "REPLAY " + app.replay_hour_label()
        pw = 96 if live else 176
        pill = pygame.Rect(PAD, PAD, pw, 36)
        self._glass(pill, radius=18)
        pygame.draw.circle(self.screen, C_OK if live else C_WARN,
                           (pill.x + 19, pill.centery), 5)
        self._text(label, self.font_sm, C_TEXT, (pill.x + 34, pill.centery), "midleft")
        x = pill.right + 8
        if app.settings.demo_mode and live:
            badge = pygame.Rect(x, PAD, 118, 36)
            self._glass(badge, (120, 82, 20, 190), radius=18)
            self._text("DEMO DATA", self.font_label, C_WARN, badge.center, "center")

        # Control pills, top-right
        bx = self.w - PAD
        for label2, bid in (("Settings", "settings"),
                            ("Live", "mode_live") if not live else ("Replay", "mode_replay")):
            r = pygame.Rect(0, PAD, 96, 36)
            r.right = bx
            self._pill(r, label2, bid)
            bx = r.left - 8

    def _draw_live_strip(self, app, strip: pygame.Rect) -> None:
        # KPI merged into the strip (§5): big current count on the right
        num_w = 118
        chart = pygame.Rect(strip.x + 14, strip.y + 26, strip.w - num_w - 40,
                            strip.h - 36)
        self._text("PEOPLE DETECTED · LAST 60 S", self.font_label, C_FAINT,
                   (chart.x, strip.y + 9))
        self._chart(chart, app.sparkline_values(), None)
        nx = strip.right - 14
        self._text(str(app.current_count()), self.font_big, C_TEXT,
                   (nx, strip.y + 8), "topright")
        self._text("in frame", self.font_sm, C_FAINT, (nx, strip.y + 62), "topright")

    def _draw_replay_strip(self, app, strip: pygame.Rect) -> None:
        # Controls row inside the strip header
        y = strip.y + 8
        self._pill(pygame.Rect(strip.x + 12, y, 40, 30), "<", "hour_prev")
        hr = pygame.Rect(strip.x + 56, y, 92, 30)
        self._glass(hr, radius=15)
        self._text(app.replay_hour_label(), self.font_sm, C_TEXT, hr.center, "center")
        self._pill(pygame.Rect(hr.right + 4, y, 40, 30), ">", "hour_next")
        self._pill(pygame.Rect(hr.right + 52, y, 62, 30),
                   "Pause" if app.replay_playing else "Play", "play",
                   active=app.replay_playing)
        self._pill(pygame.Rect(hr.right + 118, y, 52, 30),
                   f"{app.replay_speed}x", "speed")
        mins = int(app.replay_pos // 60)
        secs = int(app.replay_pos % 60)
        self._text(f"{app.replay_hour_label()[:2]}:{mins:02d}:{secs:02d}",
                   self.font_sm, C_TEXT, (strip.right - 14, y + 6), "topright")

        # Timeline chart: whole hour of counts, click/drag to seek
        chart = pygame.Rect(strip.x + 14, strip.y + 44, strip.w - 28, strip.h - 52)
        counts = app.replay_data.counts if app.replay_data else []
        self._chart(chart, counts, app.replay_pos / HOUR_S)
        self._sliders.append((chart.inflate(0, 10), "scrub", 0.0, HOUR_S))

    def _draw_settings(self, app) -> None:
        s = app.settings
        self._text("Settings", self.font_h1, C_TEXT, (PAD + 10, PAD + 6))
        self._pill(pygame.Rect(self.w - 96 - PAD, PAD + 6, 96, 36), "Done", "back",
                   active=True)
        self._pill(pygame.Rect(self.w - 96 - PAD - 190, PAD + 6, 182, 36),
                   "Capture base image", "capture", accent=True)

        colw = (self.w - PAD * 3) // 2
        lx, rx = PAD, PAD * 2 + colw

        # --- left column ---
        card = pygame.Rect(lx, 64, colw, 236)
        self._glass(card, C_GLASS_SOLID)
        x, y = card.x + 18, card.y + 14
        self._text("DETECTION & HEAT", self.font_label, C_ACCENT, (x, y))
        y += 28
        self._text("Environment preset", self.font_sm, C_FAINT, (x, y))
        bx = x
        for name in ENV_PRESETS:
            r = pygame.Rect(bx, y + 22, 118, 36)
            self._pill(r, name.capitalize(), f"preset_{name}")
            bx = r.right + 8
        y += 76
        self._text("Time frame", self.font_sm, C_FAINT, (x, y))
        bx = x
        for i, (label, hours) in enumerate(TIME_FRAME_CHOICES):
            r = pygame.Rect(bx, y + 22, 80, 36)
            self._pill(r, label, f"tf_{i}",
                       active=abs(s.time_frame_hours - hours) < 1e-6)
            bx = r.right + 8
        y += 84
        self._slider(pygame.Rect(x, y + 18, card.w - 60, 18), "conf",
                     s.confidence_threshold, 0.1, 0.9,
                     "Detection confidence", f"{int(s.confidence_threshold * 100)}%")

        card2 = pygame.Rect(lx, card.bottom + 14, colw, 176)
        self._glass(card2, C_GLASS_SOLID)
        x, y = card2.x + 18, card2.y + 14
        self._text("STORAGE", self.font_label, C_ACCENT, (x, y))
        y += 28
        self._text("Reference photos (off saves disk space)", self.font_sm, C_FAINT,
                   (x, y))
        self._pill(pygame.Rect(x, y + 22, 78, 36),
                   "On" if s.save_reference_photos else "Off",
                   "toggle_photos", active=s.save_reference_photos)
        bx = x + 88
        for i, iv in enumerate(REF_INTERVAL_CHOICES):
            r = pygame.Rect(bx, y + 22, 58, 36)
            self._pill(r, f"{iv:g}s", f"ref_{i}",
                       active=abs(s.reference_interval_s - iv) < 1e-6)
            bx = r.right + 6
        y += 76
        self._text("Heat log (needed for Replay)", self.font_sm, C_FAINT, (x, y))
        self._pill(pygame.Rect(x, y + 22, 78, 36),
                   "On" if s.save_heat_log else "Off",
                   "toggle_log", active=s.save_heat_log)

        # --- right column ---
        card3 = pygame.Rect(rx, 64, colw, 236)
        self._glass(card3, C_GLASS_SOLID)
        x, y = card3.x + 18, card3.y + 14
        self._text("PRESENTATION", self.font_label, C_ACCENT, (x, y))
        y += 28
        self._text("Demo mode — synthetic activity for presentations",
                   self.font_sm, C_FAINT, (x, y))
        self._pill(pygame.Rect(x, y + 22, 78, 36),
                   "On" if s.demo_mode else "Off",
                   "toggle_demo", active=s.demo_mode)
        y += 80
        self._slider(pygame.Rect(x, y + 18, card3.w - 60, 18), "demo_min",
                     s.demo_min, 1, 50, "Demo headcount min", str(s.demo_min))
        y += 62
        self._slider(pygame.Rect(x, y + 18, card3.w - 60, 18), "demo_max",
                     s.demo_max, 1, 50, "Demo headcount max", str(s.demo_max))

        card4 = pygame.Rect(rx, card3.bottom + 14, colw, 176)
        self._glass(card4, C_GLASS_SOLID)
        x, y = card4.x + 18, card4.y + 14
        self._text("SHORTCUTS", self.font_label, C_ACCENT, (x, y))
        y += 30
        for keys, desc in (("B", "Capture base image"), ("L / R", "Live / Replay"),
                           ("D", "Toggle demo mode"), ("S", "Open settings"),
                           ("SPACE", "Play / pause replay"), ("ESC", "Back / quit")):
            self._text(keys, self.font_sm, C_TEXT, (x, y))
            self._text(desc, self.font_sm, C_FAINT, (x + 80, y))
            y += 23

    def _draw_flash(self) -> None:
        if self._flash and time.time() < self._flash[1]:
            msg = self._flash[0]
            r = pygame.Rect(0, 0, 24 + len(msg) * 9, 40)
            r.midtop = (self.w // 2, PAD)
            self._glass(r, (31, 76, 128, 235), radius=20)
            self._text(msg, self.font_sm, C_TEXT, r.center, "center")

    # ------------------------------------------------------------------ events

    def handle(self, app, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for rect, sid, lo, hi in self._sliders:
                if rect.collidepoint(event.pos):
                    self._drag = sid
                    self._drag_slider(app, event.pos)
                    return
            for rect, bid in self._buttons:
                if rect.collidepoint(event.pos):
                    app.on_button(bid)
                    return
        elif event.type == pygame.MOUSEMOTION and self._drag:
            self._drag_slider(app, event.pos)
        elif event.type == pygame.MOUSEBUTTONUP:
            self._drag = None

    def _drag_slider(self, app, pos) -> None:
        for rect, sid, lo, hi in self._sliders:
            if sid == self._drag:
                t = min(1.0, max(0.0, (pos[0] - rect.x) / rect.w))
                app.on_slider(sid, lo + t * (hi - lo))
                return
