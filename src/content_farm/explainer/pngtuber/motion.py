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
from content_farm.explainer.pngtuber.profiles import LEGACY, MotionProfile

MOUTH_HALF_AT = LEGACY.mouth_half_at     # envelope level where the half-open mouth starts
MOUTH_OPEN_AT = LEGACY.mouth_open_at     # ... and the wide-open one
MOUTH_HOLD_FRAMES = LEGACY.mouth_hold    # a mouth shape stays at least this long (no 1-frame flicker)
BREATH_SCALE = LEGACY.breath_scale       # vertical stretch at the top of a breath
SWAY_DEG, SWAY_PERIOD_S = LEGACY.sway_deg, 5.3
BOUNCE_PX = LEGACY.bounce_px             # lift while talking, scaled by the envelope
HEAD_DRIFT_PERIOD_S = 6.1
BEAT_FRAMES, BEAT_LAND_FRAMES, BEAT_GAP_FRAMES = 7, 4, 8   # hop up/down, squash on landing, refractory
BEAT_RISE, BEAT_MIN_LEVEL = 0.18, 0.35                      # envelope rise over 3 frames that counts as an onset
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
    # head-only pose (any pack): px of the head's offset, feet pinned; positive dy = down
    head_dx: float = 0.0
    head_dy: float = 0.0
    bubbles: tuple[tuple[float, float, float, float], ...] = ()   # speech_fx: (x, y, radius, alpha), pack px


YAW_PERIOD_S, NOD_PERIOD_S = 7.7, 4.6
TALK_SQUASH = 0.035      # at a fully open mouth


def mouth_levels(envelope: np.ndarray, hold: int = MOUTH_HOLD_FRAMES, half_at: float = MOUTH_HALF_AT,
                 open_at: float = MOUTH_OPEN_AT, open_max: int = 0) -> np.ndarray:
    """Closed/half/open per frame. ``open_max`` > 0 eases a wide mouth back to half after that many
    frames, so a sustained loud vowel chatters instead of staring open."""
    target = np.where(envelope >= open_at, 2, np.where(envelope >= half_at, 1, 0))
    out = np.zeros(len(target), dtype=np.int8)
    current, held = 0, hold
    for i, goal in enumerate(target):
        if open_max and goal == 2 and current == 2 and held >= open_max:
            goal = 1
        if goal != current and held >= hold:
            current, held = int(goal), 0
        held += 1
        out[i] = current
    return out


def smooth(envelope: np.ndarray, frames: int) -> np.ndarray:
    """Centered moving average (same length); ``frames`` <= 1 returns the input."""
    if frames <= 1:
        return envelope
    padded = np.pad(envelope, (frames // 2, frames - 1 - frames // 2), mode="edge")
    return np.convolve(padded, np.ones(frames) / frames, mode="valid")


def beat_track(envelope: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(hop, stretch) per frame from voice onsets: an eased hop of BEAT_FRAMES after each onset, then
    a short squash on landing. Onset = the envelope rose BEAT_RISE over 3 frames to >= BEAT_MIN_LEVEL;
    onsets closer than BEAT_GAP_FRAMES are ignored. Both are 0..1 (stretch is negative on landing)."""
    n = len(envelope)
    hop, stretch = np.zeros(n), np.zeros(n)
    last = -BEAT_GAP_FRAMES
    for i in range(3, n):
        if i - last >= BEAT_GAP_FRAMES and envelope[i] >= BEAT_MIN_LEVEL and envelope[i] - envelope[i - 3] >= BEAT_RISE:
            last = i
            for k in range(BEAT_FRAMES):
                if i + k < n:
                    hop[i + k] = max(hop[i + k], math.sin(math.pi * (k + 1) / (BEAT_FRAMES + 1)))
                    stretch[i + k] = max(stretch[i + k], math.sin(math.pi * (k + 1) / (BEAT_FRAMES + 1)))
            for k in range(BEAT_LAND_FRAMES):
                j = i + BEAT_FRAMES + k
                if j < n and hop[j] == 0:
                    stretch[j] = -0.5 * math.sin(math.pi * (k + 1) / (BEAT_LAND_FRAMES + 1))
    return hop, stretch


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
                seed: int = 7, profile: MotionProfile = LEGACY) -> tuple[HostFrame, ...]:
    if len(envelope) < n_frames:
        envelope = np.pad(envelope, (0, n_frames - len(envelope)))
    envelope = np.asarray(envelope[:n_frames])
    duration = n_frames / fps
    blinks = idle.blink_schedule(duration, seed)
    mouths = mouth_levels(envelope, profile.mouth_hold, profile.mouth_half_at, profile.mouth_open_at,
                          profile.mouth_open_max)
    body = smooth(envelope, profile.smooth_frames)
    hop, hop_stretch = beat_track(envelope) if profile.beat_px else (np.zeros(n_frames), np.zeros(n_frames))
    phase = (seed % 97) / 97 * 2 * math.pi
    bubbles = (bubble_track(envelope, fps, n_frames, pack.speech_fx, seed)
               if pack.speech_fx else [()] * n_frames)
    frames = []
    for i in range(n_frames):
        t = i / fps
        expression = pack.expression_for(cues[cue_at(cues, t)].pose) if cues else "neutral"
        blink = expression not in NO_BLINK and idle.blink_closure(t, blinks) > 0.5
        mouth = int(mouths[i]) if profile.mouth_on_expression or expression == "neutral" else 0
        frames.append(HostFrame(
            expression=expression, mouth=mouth, blink=blink,
            stretch=1.0 + profile.breath_scale * idle.breath(t) + profile.beat_stretch * float(hop_stretch[i]),
            angle=profile.sway_deg * math.sin(2 * math.pi * t / SWAY_PERIOD_S + phase),
            lift=profile.bounce_px * float(body[i]) + profile.beat_px * float(hop[i]),
            yaw=math.sin(2 * math.pi * t / YAW_PERIOD_S + 2 * phase),
            nod=0.6 * math.sin(2 * math.pi * t / NOD_PERIOD_S + 3 * phase),
            squash=TALK_SQUASH * float(envelope[i]),
            head_dx=profile.head_drift_px * math.sin(2 * math.pi * t / HEAD_DRIFT_PERIOD_S + phase),
            head_dy=profile.head_nod_px * float(body[i]),
            bubbles=bubbles[i]))
    return tuple(frames)
