"""The ``frog`` motion profile and the procedural jaw drop (pngtuber.jaw)."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from content_farm.explainer.mascot.cues import SceneCue
from content_farm.explainer.pngtuber import motion
from content_farm.explainer.pngtuber.jaw import JawRig
from content_farm.explainer.pngtuber.profiles import FROG


def _base() -> Image.Image:
    img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((20, 20, 280, 290), fill=(120, 190, 150, 255))
    d.line((80, 170, 220, 170), fill=(10, 10, 10, 255), width=5)
    return img


def test_jaw_rig_opens_below_the_line_and_pins_the_corners() -> None:
    base = _base()
    rig = JawRig(base, {"x_range": [80, 220], "rows": [150, 190], "depth": 30, "falloff": 80})
    assert rig.open_face(base, 0.0) is base
    opened = np.asarray(rig.open_face(base, 1.0)).astype(int)
    closed = np.asarray(base).astype(int)
    assert np.abs(opened[:150] - closed[:150]).max() == 0                  # above the line: untouched
    assert opened[176, 110, 0] < 110 and opened[176, 110, 1] < 60          # dark interior under the line
    assert np.abs(opened[:, 78] - closed[:, 78]).max() <= 40               # corners hardly move


def test_frog_profile_is_neutral_and_only_the_jaw_moves() -> None:
    env = np.tile(np.concatenate([np.full(20, 0.95), np.full(10, 0.3)]), 6)
    jaw = motion.jaw_track(env, FROG)
    assert jaw.max() <= FROG.jaw_max + 1e-9 and jaw.min() == 0.0
    edges = np.flatnonzero(np.diff((jaw > 0).astype(int)))
    assert len(edges) > 2 and np.diff(edges).min() > 2                     # no 1-2 frame flicker
    fake = type("Pack", (), {"expression_for": lambda self, pose: "smug", "speech_fx": None})()
    frames = motion.host_frames((SceneCue(1, 0.0, 6.0, "smug"),), env, 30.0, len(env), fake, profile=FROG)
    assert {f.expression for f in frames} == {"neutral"} and {f.mouth for f in frames} == {0}
    assert all(f.angle == 0 and f.lift == 0 and f.head_dy == 0 for f in frames)
