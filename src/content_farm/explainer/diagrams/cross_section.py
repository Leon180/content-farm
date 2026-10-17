"""A drawn 2.5D package cross-section (substrate → interposer → compute die + memory stacks).

- ``cross_section()``: the still key visual for a thumbnail panel (CoWoS v3 variant B);
- ``section_frames()``: the animated diagram — ``mode=build`` adds one layer per narration
  stage (載板 → 中介層 → 運算晶片 → 記憶體); ``mode=warp`` shows the whole package, heats it up
  and bends interposer + substrate (2024 Blackwell warpage, as reported).
Channel-drawn, so no AI label or third-party credit is needed.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from content_farm.explainer.diagrams.render import FPS, Palette, _ease, _font, _stage, palette_for

AMBER, GREY, WHITE = "#f59f00", "#8a97a8", "#ffffff"
LAYERS = ("載板", "中介層", "運算晶片", "記憶體")


def _bow(x: float, centre: float, half: float, warp: float, amplitude: float) -> float:
    """Vertical offset of a bent board at x (edges lift, a "smile" warp)."""
    u = (x - centre) / half
    return -warp * amplitude * u * u


def draw(size: int, pal: Palette, *, parts: int = 4, warp: float = 0.0, heat: float = 0.0,
         question: bool = False, dark: bool = True) -> Image.Image:
    s = size / 1120
    bg = pal.fg if dark else pal.bg
    ink = WHITE if dark else pal.fg
    image = Image.new("RGB", (size, size), bg)
    centre, half = 560 * s, 470 * s

    def board(x0: float, x1: float, y0: float, y1: float, fill: str) -> None:
        steps = 40
        top = [(x0 + (x1 - x0) * k / steps, y0 + _bow(x0 + (x1 - x0) * k / steps, centre, half, warp, 70 * s))
               for k in range(steps + 1)]
        bottom = [(x, y + (y1 - y0)) for x, y in reversed(top)]
        d.polygon(top + bottom, fill=fill)

    if parts >= 2 or heat:
        glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        g = ImageDraw.Draw(glow)
        colour = (230, 60, 40, round(200 * heat)) if heat else (245, 159, 0, 170)
        g.rounded_rectangle((150 * s, 560 * s, 970 * s, 660 * s), radius=30 * s, fill=colour)
        glow = glow.filter(ImageFilter.GaussianBlur(40 * s))
        image.paste(glow, (0, 0), glow)
    d = ImageDraw.Draw(image)
    label = _font(round(44 * s))
    if parts >= 1:
        board(90 * s, 1030 * s, 700 * s, 800 * s, GREY)
        for x in range(130, 1000, 70):
            off = _bow((x + 17) * s, centre, half, warp, 70 * s)
            d.ellipse((x * s, 805 * s + off, (x + 34) * s, 839 * s + off), fill="#c9d2dc")
        d.text((560 * s, 750 * s + _bow(560 * s, centre, half, warp, 70 * s)), "載板", fill=pal.fg, font=label, anchor="mm")
    if parts >= 2:
        board(170 * s, 950 * s, 600 * s, 660 * s, AMBER)
        d.text((560 * s, 630 * s), "中介層", fill=pal.fg, font=label, anchor="mm")
    if parts >= 3:
        lift = _bow(560 * s, centre, half, warp, 70 * s)
        d.rectangle((420 * s, 400 * s + lift, 700 * s, 584 * s + lift), outline=WHITE, width=round(6 * s), fill="#1d3557")
        d.text((560 * s, 492 * s + lift), "運算晶片", fill=WHITE, font=label, anchor="mm")
    if parts >= 4:
        for x0 in (210, 760):
            lift = _bow((x0 + 75) * s, centre, half, warp, 70 * s)
            for k in range(4):
                y = 540 - k * 40
                d.rectangle((x0 * s, y * s + lift, (x0 + 150) * s, (y + 36) * s + lift), outline=WHITE,
                            width=round(4 * s), fill="#244a74")
            d.text(((x0 + 75) * s, 360 * s + lift), "記憶體", fill=ink, font=label, anchor="mm")
    if question:
        d.text((560 * s, 230 * s), "?", fill=AMBER, font=_font(round(330 * s)), anchor="mm",
               stroke_width=round(8 * s), stroke_fill=bg)
    return image


def cross_section(out: Path, *, brand: str | None = None, size: int = 1120, question: bool = True) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    draw(size, palette_for(brand), question=question).save(out)
    return out


def section_frames(labels: list[str], starts: list[float], seconds: float, pal: Palette, mode: str = "build"):
    """Frames for the 1920x1080 diagram band: the section centred, the stage label on the right."""
    from content_farm.explainer.diagrams.render import BOTTOM, H, TOP, W

    size = round((BOTTOM - TOP) * 1.4)          # the drawing fills ~32–75 % of its square: scale up, shift up
    side = _font(52)
    for frame in range(round(seconds * FPS)):
        t = frame / FPS
        stage = _stage(t, starts)
        if mode == "warp":
            heat = _ease((t - starts[1]) / 1.5) if len(starts) > 1 and stage >= 1 else 0.0
            warp = _ease((t - starts[2]) / 2.0) if len(starts) > 2 and stage >= 2 else 0.0
            section = draw(size, pal, parts=4, warp=warp, heat=heat, dark=False)
        else:
            section = draw(size, pal, parts=max(stage + 1, 0), dark=False)
        image = Image.new("RGB", (W, H), pal.bg)
        image.paste(section, ((W - size) // 2 - 300, TOP - round(size * 0.26)))
        draw_ = ImageDraw.Draw(image)
        for k, text in enumerate(labels[: stage + 1]):
            colour = pal.accent if k == stage else pal.muted
            draw_.text((1380, TOP + 60 + 80 * k), f"{k + 1}. {text}", fill=colour, font=side)
        yield image
