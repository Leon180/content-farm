"""One settled pose of the 晶片貓 rig as a transparent PNG (thumbnails, Shorts).

Uses the same motion model as the video overlay (``compose_frames``), sampled
after the pose transition has settled, so a thumbnail cat is the cat that
appears in the video — not a separate drawing that could drift from it.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image

from content_farm.explainer.mascot.cues import SceneCue
from content_farm.explainer.mascot.motion import compose_frames
from content_farm.explainer.mascot.render import capture_pngs

FPS = 30
SPAN = 3.0
SETTLE_AT = 2.4                  # seconds into the pose: transition and blink are over
CAT_BOX = (240, 60, 620, 540)    # the cat's area inside the 620x540 rig canvas


def pose_png(pose: str, out: Path, *, mouth: float = 0.0, seed: int = 7) -> Path:
    """Render ``pose`` (idle/point/think/shocked/smug/deadpan/wave) to ``out``, cropped to the cat."""
    cues = (SceneCue(index=1, start=0.0, end=SPAN, pose=pose, say=None),)
    n_frames = int(SPAN * FPS)
    frames = compose_frames(cues, np.full(n_frames, mouth), FPS, n_frames, seed=seed)
    png = next(iter(capture_pngs([frames[int(SETTLE_AT * FPS)]])))
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.open(io.BytesIO(png)).convert("RGBA").crop(CAT_BOX).save(out)
    return out
