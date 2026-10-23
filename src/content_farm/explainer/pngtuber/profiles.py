"""Selectable motion profiles for PNGtuber hosts.

``legacy`` is the behaviour every channel shipped with and stays the default; the others are opt-in
(``--motion-profile`` on scripts/mascot_overlay.py, or ``mascot.motion_profile`` in a channel yaml).
A profile only tunes how the existing face patches and the one still body are moved - no new art.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class MotionProfile:
    name: str
    # mouth: voice envelope -> closed / half / open
    mouth_half_at: float = 0.12
    mouth_open_at: float = 0.45
    mouth_hold: int = 2             # a shape stays at least this many frames
    mouth_open_max: int = 0         # frames the wide mouth may stay open before easing to half; 0 = no limit
    mouth_on_expression: bool = True  # False: a non-neutral face keeps its own mouth (patches are neutral-only)
    # body (whole figure, pivot at the feet)
    smooth_frames: int = 1          # moving-average window on the envelope that drives bounce / nod
    bounce_px: float = 6.0          # lift, scaled by the (smoothed) envelope
    sway_deg: float = 1.4
    breath_scale: float = 0.018
    # head only (feet and belly stay put): dip with the voice, slow sideways drift
    head_nod_px: float = 0.0
    head_drift_px: float = 0.0
    # syllable beats: a short eased hop on each voice onset (instead of following the level every frame)
    beat_px: float = 0.0
    beat_stretch: float = 0.0       # vertical stretch at the top of a hop, squash on landing


LEGACY = MotionProfile("legacy")

# calm: same body, but the mouth stops flapping and the body stops twitching with the envelope
CALM = replace(LEGACY, name="calm", mouth_half_at=0.4, mouth_open_at=0.84, mouth_hold=4, mouth_open_max=6,
               mouth_on_expression=False, smooth_frames=9, bounce_px=2.5, sway_deg=0.5, breath_scale=0.012)

# nod: rigid body, only the head moves (dip on speech + slow drift), like a talking head
NOD = replace(CALM, name="nod", bounce_px=0.0, sway_deg=0.0, head_nod_px=5.0, head_drift_px=3.0)

# beat: syllable-onset hops with squash and stretch; no continuous bounce, no sway
BEAT = replace(CALM, name="beat", bounce_px=0.0, sway_deg=0.0, beat_px=7.0, beat_stretch=0.03,
               head_nod_px=2.5, head_drift_px=2.0)

PROFILES = {p.name: p for p in (LEGACY, CALM, NOD, BEAT)}


def get_profile(name: str | None) -> MotionProfile:
    if not name:
        return LEGACY
    try:
        return PROFILES[name]
    except KeyError:
        raise ValueError(f"unknown motion profile {name!r}; choose from {', '.join(PROFILES)}") from None
