"""A drawn 2.5D package cross-section (substrate → interposer → compute die + memory stacks).

Used as the key visual of a thumbnail panel (CoWoS v3 variant B): channel-drawn, so it needs no
AI label or credit, and it shows the actual subject (the interposer) instead of a stock metaphor.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from content_farm.explainer.diagrams.render import Palette, _font, palette_for


def cross_section(out: Path, *, brand: str | None = None, size: int = 1120, question: bool = True) -> Path:
    pal: Palette = palette_for(brand)
    navy, amber, grey, white = pal.fg, "#f59f00", "#8a97a8", "#ffffff"
    image = Image.new("RGB", (size, size), navy)
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    s = size / 1120
    # interposer glow
    g.rounded_rectangle((150 * s, 560 * s, 970 * s, 660 * s), radius=30 * s, fill=(245, 159, 0, 170))
    glow = glow.filter(ImageFilter.GaussianBlur(40 * s))
    image.paste(glow, (0, 0), glow)
    d = ImageDraw.Draw(image)
    label: ImageFont.ImageFont = _font(round(44 * s))
    # substrate
    d.rounded_rectangle((90 * s, 700 * s, 1030 * s, 800 * s), radius=10 * s, fill=grey)
    for x in range(130, 1000, 70):                       # solder balls under the substrate
        d.ellipse((x * s, 805 * s, (x + 34) * s, 839 * s), fill="#c9d2dc")
    # interposer
    d.rectangle((170 * s, 600 * s, 950 * s, 660 * s), fill=amber)
    for x in range(190, 940, 28):                        # micro-bumps
        d.ellipse((x * s, 586 * s, (x + 12) * s, 598 * s), fill="#ffd27a")
    # compute die (centre) and memory stacks (sides)
    d.rectangle((420 * s, 400 * s, 700 * s, 584 * s), outline=white, width=round(6 * s), fill="#1d3557")
    for x0 in (210, 760):
        for k in range(4):
            y = 540 - k * 40
            d.rectangle((x0 * s, y * s, (x0 + 150) * s, (y + 36) * s), outline=white, width=round(4 * s), fill="#244a74")
    d.text((560 * s, 492 * s), "運算晶片", fill=white, font=label, anchor="mm")
    d.text((285 * s, 360 * s), "記憶體", fill=white, font=label, anchor="mm")
    d.text((835 * s, 360 * s), "記憶體", fill=white, font=label, anchor="mm")
    d.text((560 * s, 630 * s), "中介層", fill=navy, font=label, anchor="mm")
    d.text((560 * s, 750 * s), "載板", fill=navy, font=label, anchor="mm")
    if question:
        q = _font(round(330 * s))
        d.text((560 * s, 230 * s), "?", fill=amber, font=q, anchor="mm", stroke_width=round(8 * s), stroke_fill=navy)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)
    return out
