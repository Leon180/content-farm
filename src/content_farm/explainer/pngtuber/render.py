"""Draw PNGtuber frames and encode them as an alpha video (same ProRes 4444 as the rig).

Two placements, each a canvas overlaid at a fixed origin on the frame:
  LANDSCAPE (1920x1080): the rig's 620x540 canvas at the rig's origin, figure right-aligned so its
            pixels stay at x >= 1600 below y 880 (the subtitle band), like the 晶片貓.
  VERTICAL  (1080x1920 Shorts): bottom-left, under the burned subtitle band (y 1220–1420) and left
            of the Shorts action buttons, where the scripted Shorts already put the cat.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from content_farm.explainer.mascot.overlay import ORIGIN, Rect
from content_farm.explainer.mascot.render import ALPHA_CODEC_ARGS, CANVAS_H, CANVAS_W
from content_farm.explainer.pngtuber.jaw import JAW_STEPS, JawRig
from content_farm.explainer.pngtuber.motion import HostFrame
from content_farm.explainer.pngtuber.pack import MOUTH_LAYERS, Pack
from content_farm.explainer.pngtuber.warp import remap


@dataclass(frozen=True)
class Placement:
    name: str
    frame: tuple[int, int]
    canvas: tuple[int, int]
    origin: tuple[int, int]      # canvas top-left on the frame
    height: int                  # figure height before breathing
    max_width: int
    anchor: str                  # "right" or "left"
    margin_x: int
    margin_bottom: int
    forbidden: dict[str, Rect]   # frame rects the figure must stay out of (checked by tests / clearance)


LANDSCAPE = Placement("landscape", (1920, 1080), (CANVAS_W, CANVAS_H), ORIGIN, height=352, max_width=292,
                      anchor="right", margin_x=12, margin_bottom=8,
                      forbidden={"meta": Rect(120, 832, 1520, 872), "subtitles": Rect(320, 880, 1600, 1080)})
VERTICAL = Placement("vertical", (1080, 1920), (560, 520), (0, 1400), height=440, max_width=500,
                     anchor="left", margin_x=24, margin_bottom=12,
                     forbidden={"subtitles": Rect(0, 1220, 1080, 1420)})
PLACEMENTS = {p.frame: p for p in (LANDSCAPE, VERTICAL)}


YAW_SHIFT = 0.032        # 2.5D: max sideways shift of the nearest pixels, share of the figure width
NOD_SHIFT = 0.018        # ... and vertical, share of the figure height
SHADOW_ALPHA = 0.30


def depth_warp(img: Image.Image, depth: np.ndarray, dx: float, dy: float) -> Image.Image:
    """A pixel at depth d samples from (x - dx·(d-½), y - dy·(d-½)), so near parts slide past far
    ones like a small head turn."""
    off = depth - 0.5
    return remap(img, dx * off, dy * off)


HEAD_FALLOFF = 2.0   # head_warp weight = (1 - y/h) ** this: the head moves, the belly barely, the feet never


def head_warp(img: Image.Image, dx: float, dy: float) -> Image.Image:
    """Move the top of a flat figure by (dx, dy) px with the feet pinned: a nod / head drift that
    needs no depth map and no body split."""
    h, w = img.height, img.width
    weight = np.clip(1.0 - np.arange(h, dtype=np.float32) / h, 0.0, 1.0) ** HEAD_FALLOFF
    col = np.broadcast_to(weight[:, None], (h, w))
    return remap(img, dx * col, dy * col)


def draw_bubbles(img: Image.Image, bubbles: Sequence[tuple[float, float, float, float]], offset: tuple[int, int],
                 scale: float) -> Image.Image:
    """Light, see-through bubbles (pack px → face px): faint fill, white rim, a small highlight."""
    ss = 3   # supersample for smooth small circles
    layer = Image.new("RGBA", (img.width * ss, img.height * ss), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for bx, by, br, ba in bubbles:
        x, y, r = (bx - offset[0]) * scale * ss, (by - offset[1]) * scale * ss, max(1.5, br * scale) * ss
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, round(55 * ba)),
                     outline=(255, 255, 255, round(225 * ba)), width=max(2, round(r * 0.2)))
        hr = r * 0.28
        draw.ellipse((x - r * 0.45 - hr, y - r * 0.45 - hr, x - r * 0.45 + hr, y - r * 0.45 + hr),
                     fill=(255, 255, 255, round(235 * ba)))
    out = img.copy()
    out.alpha_composite(layer.resize(img.size, Image.LANCZOS))
    return out


def ground_shadow(width: int, lift: float) -> Image.Image:
    """Soft contact shadow; fainter while the figure is lifted by the talk bounce."""
    w, h = max(8, round(width * 0.62)), max(4, round(width * 0.075))
    pad = 12
    shadow = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
    strength = SHADOW_ALPHA * max(0.4, 1.0 - lift / 12.0)
    ImageDraw.Draw(shadow).ellipse((pad, pad, pad + w, pad + h), fill=round(255 * strength))
    out = Image.new("RGBA", shadow.size, (0, 0, 0, 0))
    out.putalpha(shadow.filter(ImageFilter.GaussianBlur(5)))
    return out


@dataclass(frozen=True)
class RenderStats:
    frames: int
    faces: int
    seconds: float


class Composer:
    """Composites face patches onto the base once per (expression, mouth, blink), then poses it."""

    def __init__(self, pack: Pack, placement: Placement) -> None:
        self.pack, self.placement = pack, placement
        # size from the solid figure: faint fringes (e.g. a leftover painted shadow) must not shrink it
        bbox = pack.base.getchannel("A").point(lambda a: 255 if a > 128 else 0).getbbox()
        if bbox is None:
            raise ValueError(f"pack {pack.id}: base image is empty")
        self.bbox = bbox
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        self.scale = min(placement.height / h, placement.max_width / w)
        self.depth: np.ndarray | None = None
        if pack.depth is not None:   # 2.5D: leave room for the turn and the squash inside max_width
            self.scale *= 1.0 - YAW_SHIFT - 0.04
            size = (round(w * self.scale), round(h * self.scale))
            crop = Image.fromarray(np.ascontiguousarray(pack.depth[bbox[1]:bbox[3], bbox[0]:bbox[2]], dtype=np.float32))
            self.depth = np.asarray(crop.resize(size, Image.BILINEAR), dtype=np.float32)
        self._faces: dict[tuple[str, int, bool, int], Image.Image] = {}
        self._jaw = JawRig(pack.base, pack.jaw) if pack.jaw else None

    def face(self, expression: str, mouth: int, blink: bool, jaw_step: int = 0) -> Image.Image:
        if self.pack.mouth_mode == "none":
            mouth = 0
        elif self.pack.mouth_mode == "small_o" and expression != "neutral":
            mouth = 0   # the 'o' only replaces the neutral mouth; an expression keeps its own (no ghost smile)
        if jaw_step and self._jaw is None:
            raise ValueError(f"pack {self.pack.id} has no jaw geometry in its manifest")
        key = (expression, mouth, blink, jaw_step)
        if key not in self._faces:
            img = self.pack.base.copy()
            if expression != "neutral":
                img.alpha_composite(self.pack.layers[expression])
            if blink:
                img.alpha_composite(self.pack.layers["blink"])
            if mouth:
                img.alpha_composite(self.pack.layers[MOUTH_LAYERS[mouth - 1]])
            if jaw_step:
                img = self._jaw.open_face(img, jaw_step / JAW_STEPS)
            img = img.crop(self.bbox)
            size = (round(img.width * self.scale), round(img.height * self.scale))
            self._faces[key] = img.resize(size, Image.LANCZOS)
        return self._faces[key]

    def canvas(self, frame: HostFrame) -> Image.Image:
        p = self.placement
        img = self.face(frame.expression, frame.mouth, frame.blink, round(frame.jaw * JAW_STEPS))
        if frame.bubbles:
            img = draw_bubbles(img, frame.bubbles, self.bbox[:2], self.scale)
        base_w = img.width
        if frame.head_dx or frame.head_dy:
            img = head_warp(img, frame.head_dx, frame.head_dy)
        squash = frame.squash if self.depth is not None else 0.0
        if self.depth is not None:
            img = depth_warp(img, self.depth, YAW_SHIFT * img.width * frame.yaw, NOD_SHIFT * img.height * frame.nod)
        w, h = round(img.width * (1 + squash)), round(img.height * frame.stretch * (1 - squash))
        img = img.resize((w, h), Image.BILINEAR)
        pad = round(0.06 * max(w, h)) + 4
        work = Image.new("RGBA", (w + 2 * pad, h + pad), (0, 0, 0, 0))
        work.paste(img, (pad, 0), img)
        feet = (pad + w / 2, h)                          # rotate about the middle of the feet
        work = work.rotate(frame.angle, resample=Image.BICUBIC, center=feet)
        anchor_x = p.canvas[0] - p.margin_x - base_w / 2 if p.anchor == "right" else p.margin_x + base_w / 2
        anchor_y = p.canvas[1] - p.margin_bottom - frame.lift
        out = Image.new("RGBA", p.canvas, (0, 0, 0, 0))
        if self.depth is not None:
            shadow = ground_shadow(base_w, frame.lift)
            out.alpha_composite(shadow, (round(anchor_x - shadow.width / 2),
                                         round(p.canvas[1] - p.margin_bottom - shadow.height * 0.62)))
        out.alpha_composite(work, (round(anchor_x - feet[0]), round(anchor_y - feet[1])))
        return out


def render_alpha_video(composer: Composer, frames: Sequence[HostFrame], fps: float, out: Path) -> RenderStats:
    w, h = composer.placement.canvas
    out.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w}x{h}",
                             "-r", f"{fps:g}", "-i", "-", *ALPHA_CODEC_ARGS, str(out)],
                            stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for frame in frames:
            proc.stdin.write(composer.canvas(frame).tobytes())
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace")
        if proc.wait() != 0:
            raise RuntimeError(f"alpha encode failed: {err[-400:]}")
    except BrokenPipeError as exc:
        proc.kill()
        raise RuntimeError(f"ffmpeg exited early: {proc.stderr.read().decode(errors='replace')[-400:]}") from exc
    return RenderStats(frames=len(frames), faces=len(composer._faces), seconds=round(time.monotonic() - started, 1))
