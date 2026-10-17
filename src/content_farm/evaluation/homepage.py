"""Homepage-context thumbnail eval (orchestrator spec e1c7f75cfc420552, Leon 2026-10-17).

- ``feed_image``: a phone feed (thumbnail ~360 px wide, two-line title, channel name) or a
  desktop grid (~246 px) mixing our thumbnail with 8–11 competitor thumbnails, our position
  shuffled per reviewer. Cards are numbered so a reviewer can name what they noticed.
- ``thumb_metrics``: at 168 px wide — big-text glyph height, text/background contrast, subject
  share of the frame, hue distance from the competitors' average (stand-out).

Competitor thumbnails are public YouTube images used for internal evaluation only: they live
under ``output/`` (gitignored) and are never committed or published.
"""

from __future__ import annotations

import colorsys
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

PHONE_W, DESKTOP_W, SMALL_W = 360, 246, 168
DESKTOP_COLUMNS = 4
BG, FG, MUTED = "#0f0f0f", "#f1f1f1", "#aaaaaa"


@dataclass(frozen=True)
class Card:
    image: Path
    title: str
    channel: str
    ours: bool = False


def _font(size: int) -> ImageFont.ImageFont:
    from content_farm.assembly.drawtext import find_cjk_font

    path = find_cjk_font()
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, width: int, lines: int = 2) -> list[str]:
    out, line = [], ""
    for char in text:
        if draw.textlength(line + char, font=font) > width:
            out.append(line)
            line = char
            if len(out) == lines:
                break
        else:
            line += char
    if len(out) < lines and line:
        out.append(line)
    if len(out) == lines and "".join(out) != text:
        out[-1] = out[-1][:-1] + "…"
    return out


def load_competitors(directory: Path) -> list[Card]:
    meta = json.loads((directory / "competitors.json").read_text(encoding="utf-8"))
    return [Card(directory / c["thumb"], c["title"], c["channel"]) for c in meta if (directory / c["thumb"]).is_file()]


def arrange(ours: Card, competitors: list[Card], seed: str, total: int = 12) -> list[Card]:
    rng = random.Random(seed)
    picked = rng.sample(competitors, min(len(competitors), total - 1))
    cards = [*picked, ours]
    rng.shuffle(cards)
    return cards


def _thumb(card: Card, width: int) -> Image.Image:
    with Image.open(card.image) as raw:
        image = raw.convert("RGB")
    target_h = round(width * 9 / 16)
    scale = max(width / image.width, target_h / image.height)
    resized = image.resize((math.ceil(image.width * scale), math.ceil(image.height * scale)), Image.LANCZOS)
    left, top = (resized.width - width) // 2, (resized.height - target_h) // 2
    return resized.crop((left, top, left + width, top + target_h))


def _card(draw: ImageDraw.ImageDraw, canvas: Image.Image, card: Card, number: int, x: int, y: int, width: int,
          title_px: int) -> int:
    thumb = _thumb(card, width)
    canvas.paste(thumb, (x, y))
    y += thumb.height + 10
    font, small = _font(title_px), _font(round(title_px * 0.8))
    draw.ellipse((x, y, x + 2 * title_px, y + 2 * title_px), fill="#3a3a3a")
    draw.text((x + title_px, y + title_px), str(number), fill=FG, font=small, anchor="mm")
    tx = x + 2 * title_px + 10
    for line in _wrap(draw, card.title, font, width - (tx - x)):
        draw.text((tx, y), line, fill=FG, font=font)
        y += round(title_px * 1.35)
    draw.text((tx, y), f"{card.channel}・觀看次數", fill=MUTED, font=small)
    return y + round(title_px * 1.6)


def feed_image(cards: list[Card], out: Path, *, desktop: bool = False) -> Path:
    if desktop:
        cols, width, title_px, gap = DESKTOP_COLUMNS, DESKTOP_W, 15, 16
        rows = math.ceil(len(cards) / cols)
        cell_h = round(width * 9 / 16) + 110
        canvas = Image.new("RGB", (cols * (width + gap) + gap, rows * cell_h + gap), BG)
        draw = ImageDraw.Draw(canvas)
        for i, card in enumerate(cards):
            _card(draw, canvas, card, i + 1, gap + (i % cols) * (width + gap), gap + (i // cols) * cell_h, width, title_px)
    else:
        width, title_px = PHONE_W, 17
        cell_h = round(width * 9 / 16) + 105
        canvas = Image.new("RGB", (width + 30, len(cards) * cell_h + 15), BG)
        draw = ImageDraw.Draw(canvas)
        y = 15
        for i, card in enumerate(cards):
            y = max(_card(draw, canvas, card, i + 1, 15, y, width, title_px), y + cell_h)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, quality=88)
    return out


# ---- objective metrics at 168 px -------------------------------------------------------

def _luminance(rgb: tuple[float, float, float]) -> float:
    def channel(c: float) -> float:
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return round((la + 0.05) / (lb + 0.05), 2)


def mean_hue(image: Image.Image) -> tuple[float, float]:
    """Saturation-weighted circular mean hue (degrees) and mean saturation."""
    small = np.asarray(image.convert("RGB").resize((64, 36))) / 255.0
    hsv = np.array([colorsys.rgb_to_hsv(*px) for px in small.reshape(-1, 3)])
    weights = hsv[:, 1] * hsv[:, 2]
    angle = hsv[:, 0] * 2 * math.pi
    x, y = (weights * np.cos(angle)).sum(), (weights * np.sin(angle)).sum()
    return round(math.degrees(math.atan2(y, x)) % 360, 1), round(float(hsv[:, 1].mean()), 3)


def hue_distance(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return round(min(d, 360 - d), 1)


_MEASURE_JS = """() => {
  const els = [...document.querySelectorAll('.big > div, .yokai-title > div, .num, .big')];
  const text = els.map(e => ({h: parseFloat(getComputedStyle(e).fontSize), c: getComputedStyle(e).color,
                              r: e.getBoundingClientRect()})).sort((a, b) => b.h - a.h)[0] || null;
  const vis = [...document.querySelectorAll('img.visual, img.art')].map(e => e.getBoundingClientRect());
  const area = vis.reduce((s, r) => s + Math.max(0, Math.min(r.right, 1280) - Math.max(r.left, 0)) *
                                      Math.max(0, Math.min(r.bottom, 720) - Math.max(r.top, 0)), 0);
  return {font_px: text ? text.h : null, color: text ? text.c : null,
          box: text ? [text.r.left, text.r.top, text.r.right, text.r.bottom] : null, subject_area: area};
}"""


def measure_page(html: Path) -> dict:
    """Big-text size/colour/box and subject area from the variant's HTML (rendered at 1280x720)."""
    from content_farm.explainer.capture import PageCapturer

    with PageCapturer(size=(1280, 720)) as capturer:
        page = capturer._open(html)                     # noqa: SLF001 — same browser, read-only query
        return page.evaluate(_MEASURE_JS)


def _rgb(css: str | None) -> tuple[float, float, float] | None:
    if not css or not css.startswith("rgb"):
        return None
    parts = css[css.index("(") + 1: css.index(")")].split(",")
    return tuple(float(p) for p in parts[:3])  # type: ignore[return-value]


def thumb_metrics(image_path: Path, page: dict, competitor_hues: list[float]) -> dict:
    with Image.open(image_path) as raw:
        image = raw.convert("RGB")
    scale = SMALL_W / image.width
    font_px = page.get("font_px")
    glyph = round(font_px * 0.88 * scale, 1) if font_px else None     # CJK ink ≈ 0.88 em
    text_rgb = _rgb(page.get("color"))
    contrast = None
    if text_rgb and page.get("box"):
        x0, y0, x1, y1 = (int(v) for v in page["box"])
        region = np.asarray(image.crop((max(x0, 0), max(y0, 0), min(x1, image.width), min(y1, image.height))))
        flat = region.reshape(-1, 3).astype(float)
        far = flat[np.abs(flat - np.array(text_rgb)).sum(axis=1) > 120]   # pixels that are not the text
        if len(far):
            contrast = contrast_ratio(text_rgb, tuple(np.median(far, axis=0)))
    hue, saturation = mean_hue(image)
    others = [h for h in competitor_hues if h is not None]
    mean_other = None
    if others:
        x = sum(math.cos(math.radians(h)) for h in others)
        y = sum(math.sin(math.radians(h)) for h in others)
        mean_other = math.degrees(math.atan2(y, x)) % 360
    return {"glyph_px_at_168": glyph, "contrast": contrast,
            "subject_share": round(page.get("subject_area", 0) / (image.width * image.height), 3),
            "hue": hue, "saturation": saturation,
            "hue_distance": hue_distance(hue, mean_other) if mean_other is not None else None}


# thresholds (🟡 rules of thumb: legible at feed size, WCAG AA for large text, clear subject)
SMALL_GLYPH_MIN = 12.0
CONTRAST_MIN = 4.5
SUBJECT_MIN = 0.15
HUE_DISTANCE_MIN = 40.0
