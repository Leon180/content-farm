"""Per-frame PNGtuber state: which face patches show, plus breathing scale, sway and a talk bounce.

Reuses the rig's timing sources so both hosts behave alike: scene cues (deck mascot pose),
the voice envelope (lipsync) and the blink schedule (idle). Deterministic for a given seed.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from content_farm.explainer.mascot import idle
from content_farm.explainer.mascot.cues import SceneCue
from content_farm.explainer.mascot.motion import cue_at
from content_farm.explainer.pngtuber.pack import Pack

MOUTH_HALF_AT = 0.12     # envelope level where the half-open mouth starts
MOUTH_OPEN_AT = 0.45     # ... and the wide-open one
MOUTH_HOLD_FRAMES = 2    # a mouth shape stays at least this long (no 1-frame flicker)
BREATH_SCALE = 0.018     # vertical stretch at the top of a breath
SWAY_DEG, SWAY_PERIOD_S = 1.4, 5.3
BOUNCE_PX = 6.0          # lift while talking, scaled by the envelope
NO_BLINK = {"surprised"}  # wide-eyed hold: a neutral blink patch would not cover it


@dataclass(frozen=True)
class HostFrame:
    expression: str
    mouth: int        # 0 closed, 1 half, 2 open
    blink: bool
    stretch: float    # vertical scale about the feet
    angle: float      # degrees about the feet
    lift: float       # px up (canvas pixels at the final size)
    # 2.5D only (packs with a depth map); 0 = the flat behaviour
    yaw: float = 0.0     # -1..1 head turn: near pixels shift sideways more than far ones
    nod: float = 0.0     # -1..1 nod: the same, vertically
    squash: float = 0.0  # 0..1 talk squash: wider and shorter
    bubbles: tuple[tuple[float, float, float, float], ...] = ()   # speech_fx: (x, y, radius, alpha), pack px


YAW_PERIOD_S, NOD_PERIOD_S = 7.7, 4.6
TALK_SQUASH = 0.035      # at a fully open mouth


def mouth_levels(envelope: np.ndarray, hold: int = MOUTH_HOLD_FRAMES) -> np.ndarray:
    target = np.where(envelope >= MOUTH_OPEN_AT, 2, np.where(envelope >= MOUTH_HALF_AT, 1, 0))
    out = np.zeros(len(target), dtype=np.int8)
    current, held = 0, hold
    for i, goal in enumerate(target):
        if goal != current and held >= hold:
            current, held = int(goal), 0
        held += 1
        out[i] = current
    return out


BUBBLE_IDLE_RATE = 0.3       # bubbles per second while silent ("now and then one or two")
BUBBLE_TALK_RATE = 9.0       # extra bubbles per second at full voice
BUBBLE_RADIUS = (5.0, 13.0)  # pack px: quiet .. loud
BUBBLE_SPEED = (45.0, 85.0)  # pack px per second, upward
BUBBLE_SPREAD = 16.0         # pack px, sideways jitter at the emit point
BUBBLE_FADE_IN = 40.0        # pack px of rise before a bubble is fully visible (keeps the face clear)


def bubble_track(envelope: np.ndarray, fps: float, n_frames: int, fx: dict,
                 seed: int) -> list[tuple[tuple[float, float, float, float], ...]]:
    """Bubbles on screen per frame. Emission rate and size follow the voice envelope; each bubble
    rises with a small wobble from near ``emit`` and disappears at ``surface_y`` (deterministic)."""
    rng = np.random.default_rng(seed + 9173)
    ex, ey = fx["emit"]
    x0, x1 = fx["x_range"]
    surface = fx["surface_y"]
    born: list[tuple[float, float, float, float, float]] = []   # t0, x, radius, speed, wobble phase
    frames = []
    for i in range(n_frames):
        level = float(envelope[i]) if i < len(envelope) else 0.0
        rate = BUBBLE_IDLE_RATE + BUBBLE_TALK_RATE * level
        for _ in range(rng.poisson(rate / fps)):
            radius = BUBBLE_RADIUS[0] + (BUBBLE_RADIUS[1] - BUBBLE_RADIUS[0]) * level * rng.uniform(0.5, 1.0)
            born.append((i / fps, ex + rng.normal(0, BUBBLE_SPREAD), radius, rng.uniform(*BUBBLE_SPEED),
                         rng.uniform(0, 6.28)))
        t = i / fps
        alive = []
        for t0, bx, r, v, ph in born:
            risen = v * (t - t0)
            y = ey - risen
            if y - r > surface:
                x = min(x1 - r, max(x0 + r, bx + 4.0 * math.sin(5.0 * (t - t0) + ph)))
                alive.append((x, y, r, min(1.0, 0.25 + risen / BUBBLE_FADE_IN)))
        born = [b for b in born if ey - b[3] * (t - b[0]) - b[2] > surface]
        frames.append(tuple(alive))
    return frames


def host_frames(cues: Sequence[SceneCue], envelope: np.ndarray, fps: float, n_frames: int, pack: Pack,
                seed: int = 7) -> tuple[HostFrame, ...]:
    if len(envelope) < n_frames:
        envelope = np.pad(envelope, (0, n_frames - len(envelope)))
    duration = n_frames / fps
    blinks = idle.blink_schedule(duration, seed)
    mouths = mouth_levels(np.asarray(envelope[:n_frames]))
    phase = (seed % 97) / 97 * 2 * math.pi
    bubbles = (bubble_track(np.asarray(envelope), fps, n_frames, pack.speech_fx, seed)
               if pack.speech_fx else [()] * n_frames)
    frames = []
    for i in range(n_frames):
        t = i / fps
        expression = pack.expression_for(cues[cue_at(cues, t)].pose) if cues else "neutral"
        blink = expression not in NO_BLINK and idle.blink_closure(t, blinks) > 0.5
        frames.append(HostFrame(
            expression=expression, mouth=int(mouths[i]), blink=blink,
            stretch=1.0 + BREATH_SCALE * idle.breath(t),
            angle=SWAY_DEG * math.sin(2 * math.pi * t / SWAY_PERIOD_S + phase),
            lift=BOUNCE_PX * float(envelope[i]),
            yaw=math.sin(2 * math.pi * t / YAW_PERIOD_S + 2 * phase),
            nod=0.6 * math.sin(2 * math.pi * t / NOD_PERIOD_S + 3 * phase),
            squash=TALK_SQUASH * float(envelope[i]),
            bubbles=bubbles[i]))
    return tuple(frames)
