"""Compose every frame's rig parameters from cues, lip-sync and idle life.

``compose_frames`` is the deterministic clock: frame ``i`` is at ``i / fps``
and its parameters depend only on (cues, mouth envelope, fps, seed). Nothing
here looks at wall time, so the renderer can capture frames in any order.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from content_farm.explainer.mascot import idle, physics
from content_farm.explainer.mascot.cues import SceneCue
from content_farm.explainer.mascot.params import PARAM_NAMES, POSE_KEYS, pose_vector

TRANSITION_S = 0.25          # pose cross-fade at a scene change (200–300 ms)
DEADPAN_HOLD_S = 1.1         # stare before the first deliberate blink
DEADPAN_TAIL_SILENCE_S = 0.6  # silence after the punchline that earns a slow blink
BUBBLE_FADE_S = 0.2
BUBBLE_DELAY_S = 0.15
WAVE_HZ = 2.0
EAR_LAG_GAIN = 4.0          # ear swing per degree of head lag


@dataclass(frozen=True)
class Frame:
    params: Mapping[str, float]
    say: str | None


def smoothstep(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def cue_at(cues: Sequence[SceneCue], t: float) -> int:
    """Index of the cue on screen at ``t`` (clamped to the first/last)."""
    for i, cue in enumerate(cues):
        if t < cue.end:
            return i
    return len(cues) - 1


def pose_blend(cues: Sequence[SceneCue], t: float) -> dict[str, float]:
    """Pose targets at ``t``: previous pose → current pose over TRANSITION_S."""
    i = cue_at(cues, t)
    current = pose_vector(cues[i].pose)
    if i == 0:
        return dict(current)
    previous = pose_vector(cues[i - 1].pose)
    w = smoothstep((t - cues[i].start) / TRANSITION_S)
    return {k: previous[k] + (current[k] - previous[k]) * w for k in POSE_KEYS}


def deadpan_blinks(cues: Sequence[SceneCue], mouth: np.ndarray, fps: float) -> tuple[idle.Blink, ...]:
    """Slow, deliberate blinks for deadpan scenes: after a hold, and after the punchline."""
    blinks: list[idle.Blink] = []
    for cue in cues:
        if cue.pose != "deadpan":
            continue
        if cue.duration > DEADPAN_HOLD_S + 0.6:
            blinks.append(idle.Blink(cue.start + DEADPAN_HOLD_S, slow=True))
        lo, hi = int(cue.start * fps), min(int(cue.end * fps), mouth.size)
        voiced = np.nonzero(mouth[lo:hi] > 0)[0]
        if voiced.size:
            last_word = (lo + int(voiced[-1]) + 1) / fps
            if cue.end - last_word >= DEADPAN_TAIL_SILENCE_S:
                blinks.append(idle.Blink(last_word + 0.2, slow=True))
    return tuple(blinks)


def bubble_level(cue: SceneCue, t: float) -> float:
    """0..1 visibility of the speech bubble for ``cue`` at ``t``."""
    if not cue.say:
        return 0.0
    hold = min(6.0, max(2.5, 1.8 + 0.18 * len(cue.say)))
    show = cue.start + BUBBLE_DELAY_S
    hide = min(cue.end - 0.05, show + hold)
    if not show <= t < hide:
        return 0.0
    return min(1.0, (t - show) / BUBBLE_FADE_S, (hide - t) / BUBBLE_FADE_S)


def compose_frames(
    cues: Sequence[SceneCue],
    mouth: np.ndarray,
    fps: float,
    n_frames: int,
    seed: int = 7,
) -> tuple[Frame, ...]:
    if not cues:
        raise ValueError("no cues")
    if mouth.size < n_frames:
        mouth = np.concatenate([mouth, np.zeros(n_frames - mouth.size)])
    dt = 1.0 / fps
    duration = n_frames * dt
    blinks = idle.blink_schedule(duration, seed)
    slow = deadpan_blinks(cues, mouth, fps)
    heads = idle.head_events(duration, seed)
    base = [_base_frame(cues, mouth[i], i * dt, seed, blinks, slow, heads) for i in range(n_frames)]
    secondary = _secondary(base, dt, idle.twitch_schedule(duration, seed), fps)
    frames = []
    for i, params in enumerate(base):
        merged = {**params, **{k: v[i] for k, v in secondary.items()}}
        cue = cues[cue_at(cues, i * dt)]
        frames.append(Frame(
            params={k: round(float(merged[k]), 4) for k in PARAM_NAMES},
            say=cue.say if merged["ParamBubble"] > 0 else None,
        ))
    return tuple(frames)


def _base_frame(
    cues: Sequence[SceneCue], mouth: float, t: float, seed: int,
    blinks: tuple[idle.Blink, ...], slow: tuple[idle.Blink, ...], heads: tuple[idle.HeadEvent, ...],
) -> dict[str, float]:
    pose = pose_blend(cues, t)
    breath = idle.breath(t)
    dx, dy, dz = idle.head_drift(t, seed, heads)
    sway = pose["Sway"]
    closure = max(idle.blink_closure(t, blinks) * pose["BlinkMul"], idle.blink_closure(t, slow))
    eye_open = pose["EyeOpen"] * (1.0 - closure)
    cue = cues[cue_at(cues, t)]
    return {
        "ParamAngleX": pose["AngleX"] + sway * dx,
        "ParamAngleY": pose["AngleY"] + sway * dy + 3.0 * mouth,  # small nod while talking
        "ParamAngleZ": pose["AngleZ"] + sway * dz,
        "ParamBodyAngleX": pose["BodyAngleX"] + 0.25 * sway * dz,
        "ParamBodyX": 0.0,
        "ParamBodyY": pose["BodyY"],
        "ParamBreath": breath,
        "ParamEyeLOpen": eye_open,
        "ParamEyeROpen": eye_open,
        "ParamEyeLSmile": pose["EyeSmile"],
        "ParamEyeRSmile": pose["EyeSmile"],
        "ParamEyeBallX": pose["EyeBallX"],
        "ParamEyeBallY": pose["EyeBallY"],
        "ParamPupil": pose["Pupil"],
        "ParamMouthOpenY": float(mouth),
        "ParamMouthForm": pose["MouthForm"],
        "ParamMouthO": pose["MouthO"],
        "ParamTailPuff": pose["TailPuff"],
        "ParamArmR": pose["ArmR"],
        "ParamArmRWave": pose["WaveAmp"] * math.sin(2 * math.pi * WAVE_HZ * t),
        "ParamBubble": bubble_level(cue, t),
        "_EarBase": pose["EarBase"],
    }


def _secondary(
    base: Sequence[Mapping[str, float]], dt: float, twitches: tuple[idle.Twitch, ...], fps: float,
) -> dict[str, list[float]]:
    """Ears, tail and pendant: spring lag behind head/body motion (+ ear flicks)."""
    head = [f["ParamAngleZ"] + 0.4 * f["ParamAngleX"] for f in base]
    body = [f["ParamBodyAngleX"] + 0.3 * f["ParamAngleX"] + 0.2 * f["ParamBodyY"] for f in base]
    ear_lag = physics.lag(head, physics.EAR, dt)
    kicks = {"L": {}, "R": {}}
    for tw in twitches:
        kicks[tw.side][int(round(tw.time * fps))] = tw.strength
    zeros = [0.0] * len(base)
    flick = {s: physics.follow(zeros, physics.TWITCH, dt, kicks[s]) for s in ("L", "R")}
    wag = [0.35 * math.sin(2 * math.pi * i * dt / 4.3) for i in range(len(base))]
    tail_drive = [w - 0.04 * b for w, b in zip(wag, body)]
    tail1 = physics.follow(tail_drive, physics.TAIL, dt)
    tail2 = physics.follow(tail1, physics.TAIL_TIP, dt)
    chip = physics.lag([b + 6.0 * f["ParamBreath"] for b, f in zip(body, base)], physics.CHIP, dt)
    return {
        "ParamEarL": [f["_EarBase"] + EAR_LAG_GAIN * e + fl for f, e, fl in zip(base, ear_lag, flick["L"])],
        "ParamEarR": [f["_EarBase"] - EAR_LAG_GAIN * e + fl for f, e, fl in zip(base, ear_lag, flick["R"])],
        "ParamTail": [_clamp(v, -1.0, 1.0) for v in tail1],
        "ParamTail2": [_clamp(1.4 * v, -1.0, 1.0) for v in tail2],
        "ParamChip": [_clamp(-2.5 * c, -25.0, 25.0) for c in chip],
    }


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, v))
