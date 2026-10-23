"""Procedural jaw drop for a flat PNGtuber: open the mouth along its own line instead of swapping patches.

The pack's closed mouth is a drawn line. To open it, the part of the figure below that line slides down
(strongest at the middle of the mouth, zero at the corners, fading out toward the belly), the gap becomes
a dark mouth interior with a tongue, and the original line is redrawn as the upper lip. The line's own
pixels travel down with the jaw and become the lower lip. No generated art: only the pack's base image
and the geometry in its manifest ``jaw`` entry:

    "jaw": {"x_range": [x0, x1], "rows": [y0, y1], "depth": px, "falloff": px}

``x_range`` spans the mouth corners and ``rows`` the band the line sits in (canvas px); ``depth`` is the
full-open gap at the middle of the mouth and ``falloff`` how far below the line the shift fades out.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from content_farm.explainer.pngtuber.warp import remap

JAW_STEPS = 8                      # quantised openings; each is composited once and cached
DARK_LUMA = 90
INTERIOR = (62, 14, 26, 255)
TONGUE = (226, 112, 124, 255)
SUPERSAMPLE = 3


def mouth_arc(base: Image.Image, x_range: tuple[int, int], rows: tuple[int, int]) -> np.ndarray:
    """y of the closed mouth line for each x in ``x_range`` (inclusive): the topmost dark pixel of the
    column inside ``rows``; columns with none are interpolated from their neighbours."""
    arr = np.asarray(base.convert("RGBA")).astype(np.int32)
    dark = (arr[..., :3].mean(-1) < DARK_LUMA) & (arr[..., 3] > 200)
    x0, x1 = x_range
    ys = np.full(x1 - x0 + 1, np.nan)
    for i, x in enumerate(range(x0, x1 + 1)):
        hit = np.where(dark[rows[0]:rows[1], x])[0]
        if hit.size:
            ys[i] = rows[0] + hit[0]
    known = ~np.isnan(ys)
    if known.sum() < 8:
        raise ValueError(f"no mouth line found in x {x_range} rows {rows}")
    return np.interp(np.arange(len(ys)), np.nonzero(known)[0], ys[known])


class JawRig:
    """Builds the opened face for a pack: ``open_face(img, amount)`` with amount 0..1."""

    def __init__(self, base: Image.Image, spec: dict) -> None:
        self.x0, self.x1 = spec["x_range"]
        self.depth, self.falloff = float(spec["depth"]), float(spec["falloff"])
        rows = tuple(spec["rows"])
        self.arc = mouth_arc(base, (self.x0, self.x1), rows)
        self.top = float(self.arc.min()) - 4.0                       # everything from here down can move
        width = self.x1 - self.x0
        self.taper = np.sin(np.pi * (np.arange(width + 1) / width)) ** 0.8   # 0 at the corners, 1 mid-mouth
        self.size = base.size

    def _shift(self, amount: float) -> np.ndarray:
        """Downward shift (canvas px) of every pixel: depth·amount·taper(x)·fade(y)."""
        w, h = self.size
        taper = np.zeros(w, dtype=np.float32)
        taper[self.x0:self.x1 + 1] = self.taper
        yy = np.arange(h, dtype=np.float32)[:, None]
        fade = np.clip(1.0 - (yy - self.top) / self.falloff, 0.0, 1.0) * (yy >= self.top)
        return (self.depth * amount) * taper[None, :] * fade

    def open_face(self, img: Image.Image, amount: float) -> Image.Image:
        if amount <= 0.0:
            return img
        shift = self._shift(amount)
        out = remap(img, np.zeros_like(shift), shift)
        out.alpha_composite(self._interior(amount))
        return out

    def _interior(self, amount: float) -> Image.Image:
        """The dark opening between the old line (upper lip) and the line's new place (lower lip)."""
        ss = SUPERSAMPLE
        xs = np.arange(self.x0, self.x1 + 1)
        gap = self.depth * amount * self.taper * np.clip(1.0 - (self.arc - self.top) / self.falloff, 0.0, 1.0)
        top = self.arc
        bottom = self.arc + gap
        poly = [(float(x) * ss, float(y) * ss) for x, y in zip(xs, top)]
        poly += [(float(x) * ss, float(y) * ss) for x, y in zip(xs[::-1], bottom[::-1])]
        size = (self.size[0] * ss, self.size[1] * ss)
        lens = Image.new("L", size, 0)
        ImageDraw.Draw(lens).polygon(poly, fill=255)
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        layer.paste(Image.new("RGBA", size, INTERIOR), (0, 0), lens)
        cx = (self.x0 + self.x1) / 2
        mid = len(xs) // 2
        tongue = Image.new("L", size, 0)
        tw, th = (self.x1 - self.x0) * 0.22, float(gap[mid]) * 0.55
        bottom_y = float(bottom[mid])
        ImageDraw.Draw(tongue).ellipse(((cx - tw) * ss, (bottom_y - th) * ss, (cx + tw) * ss, (bottom_y + th * 0.4) * ss),
                                       fill=255)
        tongue = Image.fromarray(np.minimum(np.asarray(tongue), np.asarray(lens)))
        layer.paste(Image.new("RGBA", size, TONGUE), (0, 0), tongue)
        ImageDraw.Draw(layer).line([(float(x) * ss, float(y) * ss) for x, y in zip(xs, top)],
                                   fill=(18, 12, 12, 255), width=5 * ss, joint="curve")
        return layer.resize(self.size, Image.LANCZOS)
