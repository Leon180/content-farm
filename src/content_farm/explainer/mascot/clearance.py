"""Do the burned subtitles stay clear of the cat's column?

The cat sits bottom-right; ``overlay.SUBTITLES`` promises its pixels stay at
x >= 1600 below y 880. Subtitles are centred at x = 960, so any line wider than
2 × (1600 − 960) = 1280 px reaches into the cat. ``wrap_text`` allows up to
max + 4 characters when it can break at punctuation, so the landscape default
(24 → up to 28 CJK chars ≈ 1460 px at 52 pt) can overshoot; explainer runs use
``CF_SUBTITLE_MAX_CHARS_PER_LINE_LANDSCAPE=20`` (≤ 24 chars ≈ 1250 px).

Widths are measured with Pillow on the same CJK font the assembly burns with.
Pillow's size is the em size; libass sizes by ascender+descender, which for
CJK fonts is >= 1 em, so the estimate errs on the wide side.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from PIL import ImageFont

from content_farm.explainer.mascot.overlay import FRAME_W, SUBTITLES

SUBTITLE_FONT_SIZE = 64  # timeline_assembly.LANDSCAPE_PRESET.subtitle_font_size
SUBTITLE_OUTLINE = 10    # box padding (ASS Outline with BorderStyle 3) in timeline_assembly


@dataclass(frozen=True)
class WideLine:
    text: str
    width: int
    right_edge: int


def srt_lines(srt: str) -> list[str]:
    """Every displayed text line of an SRT (index and timing rows dropped)."""
    lines: list[str] = []
    for block in re.split(r"\n\s*\n", srt.strip()):
        rows = block.splitlines()
        lines.extend(row for row in rows[2:] if row.strip())
    return lines


def wide_lines(
    srt_path: Path, font_path: str, *, font_size: int = SUBTITLE_FONT_SIZE,
    outline: int = SUBTITLE_OUTLINE, limit_x: int = SUBTITLES.x1,
) -> tuple[WideLine, ...]:
    """Lines whose right edge passes ``limit_x``, widest first."""
    font = ImageFont.truetype(font_path, font_size)
    centre = FRAME_W // 2
    hits = []
    for text in srt_lines(srt_path.read_text(encoding="utf-8")):
        x0, _, x1, _ = font.getbbox(text)
        width = (x1 - x0) + 2 * outline
        right = centre + (width + 1) // 2
        if right > limit_x:
            hits.append(WideLine(text=text, width=width, right_edge=right))
    return tuple(sorted(hits, key=lambda w: w.width, reverse=True))
