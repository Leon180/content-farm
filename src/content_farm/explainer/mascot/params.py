"""Live2D-style parameter names, their neutral values, and the pose table.

Everything the rig (``assets/rig.html``) draws is a function of one
``dict[str, float]`` keyed by these names. Swapping the SVG rig for a real
Live2D model means mapping the same names onto Cubism parameters — this module
and everything upstream of it stay as they are.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Literal, Mapping

PoseName = Literal["idle", "point", "think", "shocked", "smug", "deadpan", "wave"]
POSES: tuple[PoseName, ...] = ("idle", "point", "think", "shocked", "smug", "deadpan", "wave")

# Neutral value of every rig parameter (also the full list the page expects).
PARAM_DEFAULTS: Mapping[str, float] = MappingProxyType({
    "ParamAngleX": 0.0,       # head yaw, deg-ish; negative = looks toward screen left
    "ParamAngleY": 0.0,       # head pitch; negative = chin up
    "ParamAngleZ": 0.0,       # head roll, deg
    "ParamBodyAngleX": 0.0,   # body lean, deg (about the floor anchor)
    "ParamBodyX": 0.0,        # px
    "ParamBodyY": 0.0,        # px; negative = hop up
    "ParamBreath": 0.0,       # 0..1
    "ParamEyeLOpen": 1.0,     # 0 closed .. 1 open .. 1.2 wide
    "ParamEyeROpen": 1.0,
    "ParamEyeLSmile": 0.0,    # 0..1 lower lid rises
    "ParamEyeRSmile": 0.0,
    "ParamEyeBallX": 0.0,     # -1..1
    "ParamEyeBallY": 0.0,     # -1..1; negative = up
    "ParamPupil": 0.0,        # 0 slit .. 1 round (dilated)
    "ParamMouthOpenY": 0.0,   # 0..1, from the lip-sync envelope
    "ParamMouthForm": 0.0,    # -1 flat, 0 cat "ω", 1 smirk (only while closed)
    "ParamMouthO": 0.0,       # 1 = small "O" while closed (shocked)
    "ParamEarL": 0.0,         # deg, + = droops outward (physics output)
    "ParamEarR": 0.0,
    "ParamTail": 0.0,         # -1..1, base segment (physics output)
    "ParamTail2": 0.0,        # -1..1, tip segment (lags ParamTail)
    "ParamTailPuff": 0.0,     # 0..1
    "ParamArmR": 0.0,         # 0 resting .. 1 raised, pointing left
    "ParamArmRWave": 0.0,     # deg added to the raised arm
    "ParamChip": 0.0,         # deg, pendant swing (physics output)
    "ParamBubble": 0.0,       # 0..1 speech bubble visibility
})
PARAM_NAMES: tuple[str, ...] = tuple(PARAM_DEFAULTS)

# Per-pose targets. Blended linearly (smoothstep in time) at scene changes.
# "Sway" scales the idle head drift, "BlinkMul" the scheduled blinks,
# "WaveAmp" the arm oscillation; "EarBase" offsets both ears.
POSE_KEYS: tuple[str, ...] = (
    "AngleX", "AngleY", "AngleZ", "BodyAngleX", "BodyY", "EyeOpen", "EyeSmile",
    "EyeBallX", "EyeBallY", "Pupil", "MouthForm", "MouthO", "EarBase", "TailPuff",
    "ArmR", "WaveAmp", "Sway", "BlinkMul",
)

_NEUTRAL: dict[str, float] = {
    "AngleX": 0.0, "AngleY": 0.0, "AngleZ": 0.0, "BodyAngleX": 0.0, "BodyY": 0.0,
    "EyeOpen": 1.0, "EyeSmile": 0.0, "EyeBallX": 0.0, "EyeBallY": 0.0, "Pupil": 0.15,
    "MouthForm": 0.0, "MouthO": 0.0, "EarBase": 0.0, "TailPuff": 0.0,
    "ArmR": 0.0, "WaveAmp": 0.0, "Sway": 1.0, "BlinkMul": 1.0,
}


def _pose(**overrides: float) -> Mapping[str, float]:
    unknown = set(overrides) - set(POSE_KEYS)
    if unknown:
        raise KeyError(f"unknown pose keys {sorted(unknown)}")
    return MappingProxyType({**_NEUTRAL, **overrides})


POSE_TARGETS: Mapping[str, Mapping[str, float]] = MappingProxyType({
    "idle": _pose(),
    # Signature move: right forepaw toward the chart on screen-left, head follows.
    "point": _pose(AngleX=-12, AngleZ=-4, BodyAngleX=-3, EyeBallX=-0.75, ArmR=1.1,
                   EarBase=-4, Sway=0.6),
    "think": _pose(AngleX=6, AngleY=-3, AngleZ=11, EyeBallX=0.55, EyeBallY=-0.7,
                   EyeOpen=0.85, EarBase=6, Sway=0.5, MouthForm=-0.2),
    "shocked": _pose(AngleY=-4, BodyY=-8, EyeOpen=1.2, Pupil=1.0, MouthO=1.0,
                     EarBase=-10, TailPuff=1.0, Sway=0.3, BlinkMul=0.0),
    "smug": _pose(AngleX=4, AngleY=-6, AngleZ=-6, EyeOpen=0.78, EyeSmile=0.45,
                  EyeBallX=0.3, MouthForm=1.0, EarBase=-2, Sway=0.7),
    # Cold-joke face: half-lidded stare, flat mouth, ears sagging, no drift.
    "deadpan": _pose(EyeOpen=0.42, EyeBallY=0.1, Pupil=0.0, MouthForm=-1.0,
                     EarBase=16, Sway=0.0, BlinkMul=0.0),
    "wave": _pose(AngleZ=-6, EyeOpen=0.9, EyeSmile=0.35, ArmR=1.0, WaveAmp=14,
                  Sway=0.8, EarBase=-3),
})


def pose_vector(pose: str) -> Mapping[str, float]:
    """Targets for ``pose``; unknown names fall back to ``idle``."""
    return POSE_TARGETS.get(pose, POSE_TARGETS["idle"])
