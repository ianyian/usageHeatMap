"""Demo mode: synthetic occupancy generator (§4.6) — a port of the mockup's agent sim.

Produces guaranteed-lively detections regardless of the real room, for presenting the
tool when the space happens to be empty. Headcount wobbles smoothly inside the
configured min–max range; agents wander between zones rather than teleporting.
"""
import math
import random
import time
from typing import List, Tuple

Detection = Tuple[float, float, float]

# Zones agents gravitate toward (normalized coords) — spread across the frame.
ZONES = [
    (0.15, 0.35), (0.15, 0.55), (0.35, 0.45), (0.5, 0.3), (0.5, 0.6),
    (0.65, 0.45), (0.8, 0.35), (0.8, 0.65), (0.3, 0.75), (0.6, 0.8),
]
AGENT_SPEED = 0.04       # normalized units per second toward target
DWELL_S = (3.0, 12.0)    # how long an agent lingers at a zone before moving on
WOBBLE_PERIOD_S = 45.0   # headcount oscillation period


class _Agent:
    def __init__(self):
        self.x, self.y = random.choice(ZONES)
        self.x += random.uniform(-0.05, 0.05)
        self.y += random.uniform(-0.05, 0.05)
        self._pick_target()

    def _pick_target(self):
        tx, ty = random.choice(ZONES)
        self.tx = tx + random.uniform(-0.06, 0.06)
        self.ty = ty + random.uniform(-0.06, 0.06)
        self.dwell_until = 0.0

    def step(self, dt: float, now: float):
        if now < self.dwell_until:
            return
        dx, dy = self.tx - self.x, self.ty - self.y
        dist = math.hypot(dx, dy)
        if dist < 0.01:
            self.dwell_until = now + random.uniform(*DWELL_S)
            self._pick_target()
            return
        step = min(dist, AGENT_SPEED * dt)
        self.x += dx / dist * step
        self.y += dy / dist * step


class DemoSimulator:
    def __init__(self):
        self.agents: List[_Agent] = []
        self._last = time.time()
        self._phase = random.uniform(0, math.tau)

    def target_count(self, min_n: int, max_n: int, now: float) -> int:
        # Smooth sinusoid + slow drift between min and max — never jumps.
        t = (math.sin(math.tau * now / WOBBLE_PERIOD_S + self._phase) + 1) / 2
        return round(min_n + t * (max_n - min_n))

    def tick(self, min_n: int, max_n: int) -> List[Detection]:
        now = time.time()
        dt = min(0.5, now - self._last)
        self._last = now

        target = self.target_count(min_n, max_n, now)
        while len(self.agents) < target:
            self.agents.append(_Agent())
        while len(self.agents) > target:
            self.agents.pop(random.randrange(len(self.agents)))

        for a in self.agents:
            a.step(dt, now)
        return [
            (min(0.98, max(0.02, a.x)), min(0.98, max(0.02, a.y)), random.uniform(0.6, 0.95))
            for a in self.agents
        ]
