"""Native pygame UI (§5): single screen, no scrolling, no browser.

The heatmap and the people-in-frame KPI share one screen — the KPI is a corner chip
over the heatmap, not a separate section. Replay controls replace the live bottom bar
rather than stacking. Settings is its own screen (gear), matching the mockup pattern.
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

BAR_H = 64
PAD = 10

C_BG = (13, 17, 23)
# Overlay chips are translucent so they cost as little live-view as possible.
C_PANEL = (16, 21, 27, 150)
C_PANEL_SOLID = (22, 28, 36, 235)
C_TEXT = (225, 232, 240)
C_FAINT = (140, 152, 165)
C_ACCENT = (64, 156, 255)
C_OK = (63, 185, 121)
C_WARN = (240, 180, 60)
C_LINE = (52, 62, 74)


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
        self.font = pygame.font.SysFont("menlo,dejavusansmono,monospace", 15)
        self.font_small = pygame.font.SysFont("menlo,dejavusansmono,monospace", 12)
        self.font_big = pygame.font.SysFont("menlo,dejavusansmono,monospace", 34, bold=True)
        self._buttons: List[Tuple[pygame.Rect, str]] = []
        self._sliders: List[Tuple[pygame.Rect, str, float, float]] = []
        self._drag: Optional[str] = None
        self._flash: Optional[Tuple[str, float]] = None

    # ------------------------------------------------------------------ helpers

    def flash(self, msg: str) -> None:
        self._flash = (msg, time.time() + 2.5)

    def _text(self, s, font, color, pos, anchor="topleft"):
        img = font.render(s, True, color)
        r = img.get_rect(**{anchor: pos})
        self.screen.blit(img, r)
        return r

    def _panel(self, rect: pygame.Rect, color=C_PANEL):
        s = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(s, color, s.get_rect(), border_radius=10)
        self.screen.blit(s, rect)

    def _button(self, rect: pygame.Rect, label: str, bid: str, active=False,
                color=None):
        self._panel(rect, (38, 48, 60, 170) if not active else (31, 61, 94, 210))
        pygame.draw.rect(self.screen, C_ACCENT if active else C_LINE, rect, 1,
                         border_radius=10)
        self._text(label, self.font, color or (C_TEXT if active else C_FAINT),
                   rect.center, "center")
        self._buttons.append((rect, bid))

    def _slider(self, rect: pygame.Rect, sid: str, value: float, lo: float, hi: float,
                label: str, fmt: str):
        self._text(label, self.font, C_FAINT, (rect.x, rect.y - 22))
        self._text(fmt, self.font, C_TEXT, (rect.right, rect.y - 22), "topright")
        track = pygame.Rect(rect.x, rect.centery - 2, rect.w, 4)
        pygame.draw.rect(self.screen, C_LINE, track, border_radius=2)
        t = (value - lo) / (hi - lo)
        fill = pygame.Rect(rect.x, rect.centery - 2, int(rect.w * t), 4)
        pygame.draw.rect(self.screen, C_ACCENT, fill, border_radius=2)
        knob = (rect.x + int(rect.w * t), rect.centery)
        pygame.draw.circle(self.screen, C_TEXT, knob, 9)
        self._sliders.append((rect.inflate(0, 24), sid, lo, hi))

    def _sparkline(self, rect: pygame.Rect, values: List[int]):
        if len(values) < 2:
            return
        vmax = max(4, max(values))
        pts = [
            (rect.x + i * rect.w / (len(values) - 1),
             rect.bottom - (v / vmax) * rect.h)
            for i, v in enumerate(values)
        ]
        area = [(rect.x, rect.bottom)] + pts + [(rect.right, rect.bottom)]
        s = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(s, (64, 156, 255, 45), area)
        self.screen.blit(s, (0, 0))
        pygame.draw.aalines(self.screen, C_ACCENT, False, pts)

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
        if app.base_surface is not None:
            self.screen.blit(app.base_surface, (0, 0))
        grid = app.display_grid()
        if grid is not None:
            self.screen.blit(heat_surface(grid, self.w, self.h), (0, 0))

        # Mode chip (top-left) + demo badge — §4.6: demo must be unmistakable.
        mode_label = "REPLAY " + app.replay_hour_label() if app.mode == "replay" else "LIVE"
        chip = pygame.Rect(PAD, PAD, 150 if app.mode == "replay" else 92, 34)
        self._panel(chip)
        dot = C_WARN if app.mode == "replay" else C_OK
        pygame.draw.circle(self.screen, dot, (chip.x + 16, chip.centery), 5)
        self._text(mode_label, self.font, C_TEXT, (chip.x + 30, chip.centery - 9))
        if app.settings.demo_mode and app.mode == "live":
            badge = pygame.Rect(chip.right + 8, PAD, 128, 34)
            self._panel(badge, (94, 61, 20, 245))
            self._text("DEMO DATA", self.font, C_WARN, badge.center, "center")

        # KPI chip (top-right): count + sparkline, merged onto the heatmap screen (§5).
        kpi = pygame.Rect(self.w - 218 - PAD, PAD, 218, 92)
        self._panel(kpi)
        self._text(str(app.current_count()), self.font_big, C_TEXT,
                   (kpi.x + 14, kpi.y + 8))
        self._text("in frame", self.font_small, C_FAINT, (kpi.x + 14, kpi.y + 48))
        self._sparkline(pygame.Rect(kpi.x + 96, kpi.y + 12, kpi.w - 110, kpi.h - 24),
                        app.sparkline_values())

        if app.base_surface is None:
            self._text("No base image — open Settings and capture one to start",
                       self.font, C_TEXT, (self.w // 2, self.h // 2), "center")

        if app.mode == "live":
            # No bottom bar in live mode: just two small corner chips, so the
            # camera/heatmap view stays as large as possible.
            y = self.h - 46 - PAD
            self._button(pygame.Rect(self.w - 214 - PAD, y, 100, 46), "Replay",
                         "mode_replay")
            self._button(pygame.Rect(self.w - 104 - PAD, y, 104, 46), "Settings",
                         "settings")
        else:
            bar = pygame.Rect(0, self.h - BAR_H, self.w, BAR_H)
            self._panel(bar, (16, 21, 27, 190))
            self._draw_replay_bar(app, bar)

    def _draw_replay_bar(self, app, bar: pygame.Rect) -> None:
        y = bar.y + 12
        self._button(pygame.Rect(PAD, y, 44, 40), "<", "hour_prev")
        hr = pygame.Rect(PAD + 50, y, 120, 40)
        self._panel(hr)
        self._text(app.replay_hour_label(), self.font, C_TEXT, hr.center, "center")
        self._button(pygame.Rect(hr.right + 6, y, 44, 40), ">", "hour_next")

        self._button(pygame.Rect(hr.right + 60, y, 52, 40),
                     "II" if app.replay_playing else ">", "play")
        self._button(pygame.Rect(hr.right + 118, y, 62, 40),
                     f"{app.replay_speed}x", "speed")

        scrub = pygame.Rect(hr.right + 195, bar.y + 24, self.w - hr.right - 195 - 240, 16)
        pygame.draw.rect(self.screen, C_LINE, scrub, border_radius=8)
        t = app.replay_pos / HOUR_S
        pygame.draw.rect(self.screen,
                         C_ACCENT,
                         pygame.Rect(scrub.x, scrub.y, max(8, int(scrub.w * t)), 16),
                         border_radius=8)
        self._sliders.append((scrub.inflate(0, 24), "scrub", 0.0, HOUR_S))
        mins = int(app.replay_pos // 60)
        self._text(f":{mins:02d}", self.font, C_FAINT, (scrub.right + 10, scrub.y))

        self._button(pygame.Rect(self.w - 180, y, 60, 40), "Live", "mode_live")
        self._button(pygame.Rect(self.w - 114, y, 104, 40), "Settings", "settings")

    def _draw_settings(self, app) -> None:
        s = app.settings
        self._text("Settings", self.font_big, C_TEXT, (PAD + 10, PAD + 4))
        self._button(pygame.Rect(self.w - 110, PAD + 8, 100, 40), "Back", "back")
        self._button(pygame.Rect(self.w - 330, PAD + 8, 210, 40),
                     "Capture base image", "capture")
        x, colw = PAD + 10, (self.w - 60) // 2
        y = 80

        self._text("Environment preset", self.font, C_FAINT, (x, y))
        bx = x
        for name in ENV_PRESETS:
            r = pygame.Rect(bx, y + 26, 130, 40)
            self._button(r, name.capitalize(), f"preset_{name}")
            bx = r.right + 8
        y += 92

        self._text("Time frame (heat decay window)", self.font, C_FAINT, (x, y))
        bx = x
        for i, (label, hours) in enumerate(TIME_FRAME_CHOICES):
            r = pygame.Rect(bx, y + 26, 88, 40)
            self._button(r, label, f"tf_{i}", active=abs(s.time_frame_hours - hours) < 1e-6)
            bx = r.right + 8
        y += 92

        self._slider(pygame.Rect(x, y + 26, colw - 40, 20), "conf",
                     s.confidence_threshold, 0.1, 0.9,
                     "Detection confidence", f"{int(s.confidence_threshold * 100)}%")
        y += 82

        self._text("Reference photos (off by default — saves disk space)",
                   self.font, C_FAINT, (x, y))
        self._button(pygame.Rect(x, y + 26, 130, 40),
                     "ON" if s.save_reference_photos else "OFF",
                     "toggle_photos", active=s.save_reference_photos)
        bx = x + 140
        for i, iv in enumerate(REF_INTERVAL_CHOICES):
            r = pygame.Rect(bx, y + 26, 66, 40)
            label = f"{iv:g}s"
            self._button(r, label, f"ref_{i}", active=abs(s.reference_interval_s - iv) < 1e-6)
            bx = r.right + 6
        y += 92

        self._button(pygame.Rect(x, y, 220, 44),
                     f"Save heat log: {'ON' if s.save_heat_log else 'OFF'}",
                     "toggle_log", active=s.save_heat_log)

        # Right column: Presentation (§4.6)
        x2 = PAD + 30 + colw
        y2 = 80
        self._text("Presentation", self.font, C_FAINT, (x2, y2))
        self._button(pygame.Rect(x2, y2 + 26, 200, 44),
                     f"Demo mode: {'ON' if s.demo_mode else 'OFF'}",
                     "toggle_demo", active=s.demo_mode)
        y2 += 110
        self._slider(pygame.Rect(x2, y2 + 26, colw - 60, 20), "demo_min",
                     s.demo_min, 1, 50, "Demo headcount min", str(s.demo_min))
        y2 += 80
        self._slider(pygame.Rect(x2, y2 + 26, colw - 60, 20), "demo_max",
                     s.demo_max, 1, 50, "Demo headcount max", str(s.demo_max))

    def _draw_flash(self) -> None:
        if self._flash and time.time() < self._flash[1]:
            msg = self._flash[0]
            r = pygame.Rect(0, 0, 16 + len(msg) * 9, 38)
            r.midtop = (self.w // 2, PAD)
            self._panel(r, (31, 61, 94, 250))
            self._text(msg, self.font, C_TEXT, r.center, "center")

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
