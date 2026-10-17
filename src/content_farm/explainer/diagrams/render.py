"""Animated diagrams drawn frame by frame with Pillow, piped to ffmpeg.

``wafer_packing``: a 300 mm wafer; for each stage the square interposers of that size fill the
wafer one by one and a counter shows how many fit (geometry.pack). ``reticle_stitch``: one
exposure field (26×33 mm ≈ an A4 sheet in the analogy) and then 3.3×/5.5×/9× fields stitched
like a poster from several A4 sheets.

Stages start at the narration-cued times (stage_cues); after the last stage the picture keeps
moving (slow wafer turn / a light sweep over the seams) so it never holds still.
"""

from __future__ import annotations

import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from content_farm.explainer.diagrams.geometry import RETICLE_AREA, RETICLE_MM, pack

W, H, FPS = 1920, 1080, 30
FILL_SECONDS = 1.4
TOP, BOTTOM = 130, 700          # keep clear of the top bar and the lower-third
DIAGRAMS = ("wafer_packing", "reticle_stitch")


@dataclass(frozen=True)
class Palette:
    bg: str = "#f2f5f8"
    fg: str = "#0e1b2a"
    muted: str = "#4a5a6b"
    rule: str = "#c5d0da"
    accent: str = "#d9480f"
    accent2: str = "#0b5cc2"


def palette_for(brand: str | None) -> Palette:
    if not brand:
        return Palette()
    from content_farm.explainer.brands import brand_css_path

    css = brand_css_path(brand).read_text(encoding="utf-8")
    tokens = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{3,8})", css))
    base = Palette()
    return Palette(tokens.get("bg", base.bg), tokens.get("fg", base.fg), tokens.get("muted", base.muted),
                   tokens.get("rule", base.rule), tokens.get("accent", base.accent),
                   tokens.get("accent-2", base.accent2))


def _font(size: int) -> ImageFont.ImageFont:
    from content_farm.assembly.drawtext import find_cjk_font

    path = find_cjk_font()
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()


def _ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def _stage(t: float, starts: list[float]) -> int:
    return max((i for i, s in enumerate(starts) if t >= s), default=-1)


# ---- wafer packing -----------------------------------------------------------------------

def wafer_frames(areas: list[float], labels: list[str], starts: list[float], seconds: float, pal: Palette):
    packs = [pack(a) for a in areas]
    cx, cy, radius = 640, (TOP + BOTTOM) // 2, (BOTTOM - TOP) // 2 - 10
    scale = radius / 150.0
    big, mid, small = _font(150), _font(46), _font(34)
    for frame in range(round(seconds * FPS)):
        t = frame / FPS
        stage = _stage(t, starts)
        image = Image.new("RGB", (W, H), pal.bg)
        layer = Image.new("RGBA", (2 * radius + 4, 2 * radius + 4), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.ellipse((2, 2, 2 * radius + 2, 2 * radius + 2), fill="#dfe6ee", outline=pal.rule, width=4)
        inner = (150 - 3) * scale
        d.ellipse((radius + 2 - inner, radius + 2 - inner, radius + 2 + inner, radius + 2 + inner), outline=pal.rule, width=2)
        shown = 0
        if stage >= 0:
            p = packs[stage]
            progress = _ease((t - starts[stage]) / FILL_SECONDS)
            shown = int(round(p.count * progress))
            side = p.side_mm * scale
            for k, (x, y) in enumerate(sorted(p.squares, key=lambda s: (-s[1], s[0]))[:shown]):
                px, py = radius + 2 + x * scale, radius + 2 - (y + p.side_mm) * scale
                d.rectangle((px + 1, py + 1, px + side - 1, py + side - 1), fill=pal.accent if k % 2 == 0 else pal.accent2,
                            outline=pal.bg, width=2)

        angle = t * 2.0                            # the wafer turns slowly the whole time (never a still)
        layer = layer.rotate(angle, resample=Image.BICUBIC)
        image.paste(layer, (cx - radius - 2, cy - radius - 2), layer)
        draw = ImageDraw.Draw(image)
        draw.text((cx, BOTTOM - 4), "12 吋晶圓（直徑 300 mm，扣邊 3 mm）", fill=pal.muted, font=small, anchor="mt")
        if stage >= 0:
            draw.text((1500, 330), f"{shown}", fill=pal.accent, font=big, anchor="ms")
            draw.text((1500, 400), "片／每片晶圓", fill=pal.fg, font=mid, anchor="mt")
            draw.text((1500, 470), labels[stage], fill=pal.muted, font=small, anchor="mt")
            for k in range(stage):
                draw.text((1500, 540 + 46 * k), f"{labels[k]}：{packs[k].count} 片", fill=pal.muted, font=small, anchor="mt")
        yield image


# ---- reticle stitching ("A4 拼海報") --------------------------------------------------------

def reticle_frames(multiples: list[float], labels: list[str], starts: list[float], seconds: float, pal: Palette):
    unit = 5.2                                   # px per mm: a 3×3 block of 26×33 fits the band
    tw, th = RETICLE_MM[0] * unit, RETICLE_MM[1] * unit
    origin_x, origin_y = 300, TOP + 20
    mid, small = _font(46), _font(34)
    for frame in range(round(seconds * FPS)):
        t = frame / FPS
        stage = _stage(t, starts)
        image = Image.new("RGB", (W, H), pal.bg)
        draw = ImageDraw.Draw(image, "RGBA")
        if stage >= 0:
            m = multiples[stage]
            tiles = math.ceil(m)
            progress = _ease((t - starts[stage]) / FILL_SECONDS) * tiles
            for k in range(tiles):
                appear = min(max(progress - k, 0.0), 1.0)
                if appear <= 0:
                    continue
                frac = min(m - k, 1.0)
                x, y = origin_x + (k % 3) * tw, origin_y + (k // 3) * th
                width = tw * frac
                drop = (1 - appear) * 40
                draw.rectangle((x + 2, y + 2 - drop, x + width - 2, y + th - 2 - drop),
                               fill=(*_rgb(pal.accent2 if k else pal.accent), round(200 * appear)), outline=pal.fg, width=2)
                draw.text((x + width / 2, y + th / 2 - drop), "A4", fill=(255, 255, 255, round(255 * appear)),
                          font=small, anchor="mm")
            sweep = (t - starts[-1] - FILL_SECONDS) / 4.0 if starts else -1
            if sweep > 0:                         # light sweeps across the seams, forever
                sx = origin_x + (sweep % 1.0) * 3 * tw
                draw.rectangle((sx, origin_y, sx + 24, origin_y + 3 * th), fill=(255, 255, 255, 90))
            area = round(m * RETICLE_AREA)
            draw.text((1450, 300), labels[stage], fill=pal.accent, font=mid, anchor="ms")
            draw.text((1450, 360), f"≈ {area:,} mm²", fill=pal.fg, font=mid, anchor="mt")
            draw.text((1450, 440), "一次曝光最大 26 × 33 mm", fill=pal.muted, font=small, anchor="mt")
            draw.text((1450, 490), "＝ 858 mm²（像一張 A4）", fill=pal.muted, font=small, anchor="mt")
        yield image


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    h = hex_colour.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def frames_for(name: str, params: dict[str, str], starts: list[float], seconds: float, pal: Palette):
    labels = [s.strip() for s in params.get("labels", "").split("|") if s.strip()]
    values = [float(v) for v in params.get("values", "").split("|") if v.strip()]
    if not values or len(labels) != len(values):
        raise ValueError(f"diagram {name}: params need matching 'values' and 'labels' (| separated)")
    starts = (list(starts) + [starts[-1] if starts else 0.5] * len(values))[: len(values)] if starts else \
        [0.5 + i * 3.0 for i in range(len(values))]
    if name == "wafer_packing":
        return wafer_frames(values, labels, starts, seconds, pal)
    if name == "reticle_stitch":
        return reticle_frames(values, labels, starts, seconds, pal)
    raise ValueError(f"unknown diagram {name!r}; known: {', '.join(DIAGRAMS)}")


def render_clip(name: str, params: dict[str, str], starts: list[float], seconds: float, out: Path,
                brand: str | None = None) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
           "-pix_fmt", "yuv420p", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for image in frames_for(name, params, starts, seconds, palette_for(brand)):
            proc.stdin.write(image.tobytes())
    finally:
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace")
        code = proc.wait()
    if code != 0:
        raise RuntimeError(f"diagram {name} encode failed: {err[-400:]}")
    return out
