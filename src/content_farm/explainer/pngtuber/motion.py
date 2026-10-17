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


def host_frames(cues: Sequence[SceneCue], envelope: np.ndarray, fps: float, n_frames: int, pack: Pack,
                seed: int = 7) -> tuple[HostFrame, ...]:
    if len(envelope) < n_frames:
        envelope = np.pad(envelope, (0, n_frames - len(envelope)))
    duration = n_frames / fps
    blinks = idle.blink_schedule(duration, seed)
    mouths = mouth_levels(np.asarray(envelope[:n_frames]))
    phase = (seed % 97) / 97 * 2 * math.pi
    frames = []
    for i in range(n_frames):
        t = i / fps
        expression = pack.expression_for(cues[cue_at(cues, t)].pose) if cues else "neutral"
        blink = expression not in NO_BLINK and idle.blink_closure(t, blinks) > 0.5
        frames.append(HostFrame(
            expression=expression, mouth=int(mouths[i]), blink=blink,
            stretch=1.0 + BREATH_SCALE * idle.breath(t),
            angle=SWAY_DEG * math.sin(2 * math.pi * t / SWAY_PERIOD_S + phase),
            lift=BOUNCE_PX * float(envelope[i])))
    return tuple(frames)
