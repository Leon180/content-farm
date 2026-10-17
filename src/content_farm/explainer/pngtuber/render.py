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

from PIL import Image

from content_farm.explainer.mascot.overlay import ORIGIN, Rect
from content_farm.explainer.mascot.render import ALPHA_CODEC_ARGS, CANVAS_H, CANVAS_W
from content_farm.explainer.pngtuber.motion import HostFrame
from content_farm.explainer.pngtuber.pack import MOUTH_LAYERS, Pack


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


@dataclass(frozen=True)
class RenderStats:
    frames: int
    faces: int
    seconds: float


class Composer:
    """Composites face patches onto the base once per (expression, mouth, blink), then poses it."""

    def __init__(self, pack: Pack, placement: Placement) -> None:
        self.pack, self.placement = pack, placement
        bbox = pack.base.getchannel("A").getbbox()
        if bbox is None:
            raise ValueError(f"pack {pack.id}: base image is empty")
        self.bbox = bbox
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        self.scale = min(placement.height / h, placement.max_width / w)
        self._faces: dict[tuple[str, int, bool], Image.Image] = {}

    def face(self, expression: str, mouth: int, blink: bool) -> Image.Image:
        key = (expression, mouth, blink)
        if key not in self._faces:
            img = self.pack.base.copy()
            if expression != "neutral":
                img.alpha_composite(self.pack.layers[expression])
            if blink:
                img.alpha_composite(self.pack.layers["blink"])
            if mouth:
                img.alpha_composite(self.pack.layers[MOUTH_LAYERS[mouth - 1]])
            img = img.crop(self.bbox)
            size = (round(img.width * self.scale), round(img.height * self.scale))
            self._faces[key] = img.resize(size, Image.LANCZOS)
        return self._faces[key]

    def canvas(self, frame: HostFrame) -> Image.Image:
        p = self.placement
        img = self.face(frame.expression, frame.mouth, frame.blink)
        w, h = img.width, round(img.height * frame.stretch)
        img = img.resize((w, h), Image.BILINEAR)
        pad = round(0.06 * max(w, h)) + 4
        work = Image.new("RGBA", (w + 2 * pad, h + pad), (0, 0, 0, 0))
        work.paste(img, (pad, 0), img)
        feet = (pad + w / 2, h)                          # rotate about the middle of the feet
        work = work.rotate(frame.angle, resample=Image.BICUBIC, center=feet)
        anchor_x = p.canvas[0] - p.margin_x - w / 2 if p.anchor == "right" else p.margin_x + w / 2
        anchor_y = p.canvas[1] - p.margin_bottom - frame.lift
        out = Image.new("RGBA", p.canvas, (0, 0, 0, 0))
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
