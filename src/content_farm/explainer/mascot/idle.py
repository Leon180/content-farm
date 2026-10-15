"""Idle life: breathing, blinking, head drift and ear twitches.

Every schedule is drawn from ``random.Random(seed)`` up front, so the same
seed and duration always give the same motion (frames are reproducible and
the renderer can be split across processes without sharing state).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

BREATH_PERIOD_S = 3.8
BLINK_GAP_S = (2.0, 6.0)        # gap between blink events, uniformly jittered
DOUBLE_BLINK_PROB = 0.18
DOUBLE_BLINK_GAP_S = 0.24
FAST_BLINK = (0.06, 0.03, 0.09)  # close, hold, open (s)
SLOW_BLINK = (0.16, 0.14, 0.26)  # deliberate deadpan blink
HEAD_EVENT_GAP_S = (4.0, 10.0)
TWITCH_GAP_S = (3.0, 8.0)


@dataclass(frozen=True)
class Blink:
    start: float
    slow: bool = False

    @property
    def phases(self) -> tuple[float, float, float]:
        return SLOW_BLINK if self.slow else FAST_BLINK

    @property
    def end(self) -> float:
        return self.start + sum(self.phases)


@dataclass(frozen=True)
class HeadEvent:
    start: float
    duration: float
    angle_x: float
    angle_z: float


@dataclass(frozen=True)
class Twitch:
    time: float
    side: str  # "L" | "R"
    strength: float  # deg/s kick given to the ear spring


def breath(t: float, period: float = BREATH_PERIOD_S) -> float:
    """0..1, starts at exhale bottom."""
    return 0.5 - 0.5 * math.cos(2 * math.pi * t / period)


def blink_schedule(duration: float, seed: int) -> tuple[Blink, ...]:
    """Blink *events* every 2–6 s (jittered); some events are double blinks."""
    rng = random.Random(f"blink:{seed}")
    blinks: list[Blink] = []
    t = rng.uniform(0.6, 2.0)
    while t < duration:
        blinks.append(Blink(t))
        if rng.random() < DOUBLE_BLINK_PROB:
            blinks.append(Blink(t + DOUBLE_BLINK_GAP_S))
        t += rng.uniform(*BLINK_GAP_S)
    return tuple(blinks)


def blink_events(blinks: tuple[Blink, ...]) -> tuple[float, ...]:
    """Start time of each blink event (the second half of a double is folded in)."""
    events: list[float] = []
    for blink in blinks:
        if events and blink.start - events[-1] < 1.0:
            continue
        events.append(blink.start)
    return tuple(events)


def blink_closure(t: float, blinks: tuple[Blink, ...]) -> float:
    """Eyelid closure 0 (open) .. 1 (shut) at time ``t``."""
    closure = 0.0
    for blink in blinks:
        if blink.start <= t < blink.end:
            closure = max(closure, _blink_curve(t - blink.start, blink.phases))
    return closure


def _blink_curve(dt: float, phases: tuple[float, float, float]) -> float:
    close, hold, reopen = phases
    if dt < close:
        return _ease_in(dt / close)
    if dt < close + hold:
        return 1.0
    return 1.0 - _ease_out((dt - close - hold) / reopen)


def head_events(duration: float, seed: int) -> tuple[HeadEvent, ...]:
    """Occasional head tilts on top of the slow drift."""
    rng = random.Random(f"head:{seed}")
    events: list[HeadEvent] = []
    t = rng.uniform(*HEAD_EVENT_GAP_S) / 2
    while t < duration:
        sign = rng.choice((-1.0, 1.0))
        events.append(HeadEvent(
            start=t, duration=rng.uniform(1.2, 2.2),
            angle_x=sign * rng.uniform(2.0, 5.0), angle_z=sign * rng.uniform(4.0, 8.0),
        ))
        t += rng.uniform(*HEAD_EVENT_GAP_S)
    return tuple(events)


def head_drift(t: float, seed: int, events: tuple[HeadEvent, ...]) -> tuple[float, float, float]:
    """(AngleX, AngleY, AngleZ) idle offsets: two incommensurate sines + events."""
    rng = random.Random(f"drift:{seed}")
    px, py, pz = (rng.uniform(0, 2 * math.pi) for _ in range(3))
    x = 3.0 * math.sin(2 * math.pi * t / 7.3 + px) + 1.2 * math.sin(2 * math.pi * t / 3.1 + py)
    y = 1.5 * math.sin(2 * math.pi * t / 5.9 + py)
    z = 2.0 * math.sin(2 * math.pi * t / 8.7 + pz)
    for event in events:
        if event.start <= t < event.start + event.duration:
            bump = 0.5 - 0.5 * math.cos(2 * math.pi * (t - event.start) / event.duration)
            x += event.angle_x * bump
            z += event.angle_z * bump
    return x, y, z


def twitch_schedule(duration: float, seed: int) -> tuple[Twitch, ...]:
    rng = random.Random(f"twitch:{seed}")
    twitches: list[Twitch] = []
    t = rng.uniform(1.5, 4.0)
    while t < duration:
        twitches.append(Twitch(t, rng.choice(("L", "R")), rng.uniform(260.0, 420.0)))
        t += rng.uniform(*TWITCH_GAP_S)
    return tuple(twitches)


def _ease_in(x: float) -> float:
    return x * x


def _ease_out(x: float) -> float:
    return 1 - (1 - x) * (1 - x)
