#!/usr/bin/env python3
"""Render the 10 opt-in slide styles on the same 5 demo slides (design review).

    PYTHONPATH=src python scripts/render_slide_styles.py [--styles swiss,chalk] [--stock IMG]

Writes into ``docs/design/slide-styles-10/``:
    <code>/01_title.jpg … 05_stock.jpg   full-size frames (lightbox)
    <code>.png                            one strip per style
    overview.png                          all styles, one row each
    measurements.json                     layout problems + WCAG ratios per style
The review page (index.html) is built from measurements.json by
``scripts/build_slide_styles_page.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from content_farm.explainer.cards import overlay_html
from content_farm.explainer.deck import Deck
from content_farm.explainer.pages import build_pages
from content_farm.explainer.render import _LAYOUT_CHECK_JS, HEIGHT, SAFE_TOP, WIDTH, _label_font
from content_farm.explainer.styles import contrast_report, get_style, style_codes

ROOT = Path(__file__).resolve().parents[1]
DECK_JSON = ROOT / "docs" / "examples" / "explainer-tsmc" / "deck.json"
OUT = ROOT / "docs" / "design" / "slide-styles-10"
DEFAULT_STOCK = OUT / "assets" / "stock_pexels_6754834.jpg"

# (file stem, slide id, how it is rendered)
SHOTS = (
    ("01_title", "s01", "slide"),
    ("02_big_number", "s02", "slide"),
    ("03_compare", "s03", "slide"),
    ("04_timeline", "s05", "slide"),
    ("05_stock", "s04", "overlay"),
)

# Placeholder for 晶片貓 at the box the mascot worker measured (x 1660–1900, y 728–1072,
# outline #1d2230 5 px + 2.5 px white halo). Neutral grey so it never reads as a design choice.
MASCOT_SVG = """
<svg class="mascot mascot-ph" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 344"
     style="position:absolute;left:1660px;top:728px;right:auto;bottom:auto;width:240px;height:344px;
            max-width:none;max-height:none;z-index:50;
            filter:drop-shadow(0 0 2.5px rgba(255,255,255,.9)) drop-shadow(0 8px 10px rgba(0,0,0,.25))">
  <g fill="#7b818c" stroke="#1d2230" stroke-width="5" stroke-linejoin="round">
    <path d="M186 300 C 236 290, 238 230, 214 196" fill="none" stroke-width="16" stroke-linecap="round"/>
    <ellipse cx="120" cy="262" rx="86" ry="78"/>
    <path d="M50 92 L60 12 L110 50 Z"/><path d="M190 92 L180 12 L130 50 Z"/>
    <circle cx="120" cy="124" r="78"/>
  </g>
  <circle cx="92" cy="120" r="9" fill="#1d2230"/><circle cx="148" cy="120" r="9" fill="#1d2230"/>
  <rect x="86" y="226" width="68" height="56" rx="6" fill="#1d2230"/>
  <g stroke="#1d2230" stroke-width="4">
    <path d="M96 222v-8M110 222v-8M124 222v-8M138 222v-8M96 286v8M110 286v8M124 286v8M138 286v8"/>
  </g>
  <text x="120" y="262" fill="#e8e8e8" font-size="20" font-weight="700" text-anchor="middle"
        font-family="Noto Sans CJK TC">晶片貓</text>
</svg>
"""


def demo_deck() -> Deck:
    """The TSMC example trimmed to the 5 demo slides; s02 counts up, s04 sits on footage."""
    data = json.loads(DECK_JSON.read_text(encoding="utf-8"))
    by_id = {s["id"]: s for sec in data["sections"] for s in sec["slides"]}
    s02 = {**by_id["s02"], "media": {"kind": "animated", "animation": "count_up"}}
    s04 = {**by_id["s04"], "media": {"kind": "stock", "query": "semiconductor wafer"}}
    titles = [sec["title"] for sec in data["sections"]]
    sections = [
        {"title": titles[0], "slides": [by_id["s01"]]},
        {"title": titles[1], "slides": [s02, by_id["s03"], s04]},
        {"title": titles[2], "slides": [by_id["s05"]]},
    ]
    # draft badge off: it covers the top-right corner every style decorates differently.
    # The captions still say 示意數字・待查證.
    return Deck.model_validate({**data, "sections": sections, "draft_data": False})


def inject_mascot(html: str) -> str:
    """Insert the placeholder just before the stage's closing tag (before any script)."""
    script_at = html.find("<script>")
    end = html.rfind("</div>", 0, script_at if script_at >= 0 else len(html))
    if end < 0:
        raise ValueError("no stage element to attach the mascot placeholder to")
    return html[:end] + MASCOT_SVG + html[end:]


def page_html(deck: Deck, code: str, slide_id: str, kind: str) -> str:
    sections = [sec for sec in deck.sections for _ in sec.slides]
    index = next(i for i, s in enumerate(deck.slides, 1) if s.id == slide_id)
    if kind == "overlay":
        return overlay_html(deck, sections[index - 1], deck.slides[index - 1], index, style=code)
    return build_pages(deck, animate=True, style=code)[index - 1].html


def shoot(page: object, html_path: Path, png_path: Path, *, transparent: bool) -> list[str]:
    page.goto(html_path.resolve().as_uri(), wait_until="load")
    page.evaluate("document.fonts.ready.then(() => true)")
    if page.evaluate("typeof window.__anim !== 'undefined'"):
        page.evaluate("window.__anim.seek(1e6)")  # final frame (count_up finished)
    problems = []
    if page.evaluate("!!document.querySelector('.content')"):
        problems = page.evaluate(_LAYOUT_CHECK_JS, [SAFE_TOP, WIDTH, HEIGHT])
    page.screenshot(path=str(png_path), omit_background=transparent)
    return list(problems)


def render_style(page: object, deck: Deck, code: str, stock: Path, work: Path) -> dict:
    out_dir = OUT / code
    out_dir.mkdir(parents=True, exist_ok=True)
    problems: dict[str, list[str]] = {}
    frames: list[Path] = []
    for stem, slide_id, kind in SHOTS:
        html_path = work / code / f"{stem}.html"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(inject_mascot(page_html(deck, code, slide_id, kind)), encoding="utf-8")
        png = work / code / f"{stem}.png"
        found = shoot(page, html_path, png, transparent=kind == "overlay")
        if found:
            problems[stem] = found
        frame = composite_on(stock, png) if kind == "overlay" else Image.open(png).convert("RGB")
        jpg = out_dir / f"{stem}.jpg"
        frame.save(jpg, quality=84, optimize=True, progressive=True)
        frames.append(jpg)
    strip(code, frames, OUT / f"{code}.png")
    return {"code": code, "frames": [str(f.relative_to(OUT)) for f in frames],
            "problems": problems, "contrast": contrast_report(code)}


def composite_on(background: Path, overlay_png: Path) -> Image.Image:
    with Image.open(background) as bg, Image.open(overlay_png) as fg:
        base = bg.convert("RGBA").resize((WIDTH, HEIGHT), Image.LANCZOS)
        return Image.alpha_composite(base, fg.convert("RGBA")).convert("RGB")


def strip(code: str, frames: list[Path], out: Path, thumb_w: int = 480) -> Path:
    spec = get_style(code)
    thumb_h = thumb_w * HEIGHT // WIDTH
    gutter, head = 20, 64
    sheet = Image.new("RGB", (gutter + len(frames) * (thumb_w + gutter), head + thumb_h + gutter), "#16181c")
    draw = ImageDraw.Draw(sheet)
    draw.text((gutter, 14), f"{code}　{spec.name}　— {spec.tagline}", fill="#f0f0f0", font=_label_font(28))
    for i, frame in enumerate(frames):
        with Image.open(frame) as img:
            sheet.paste(img.resize((thumb_w, thumb_h), Image.LANCZOS), (gutter + i * (thumb_w + gutter), head))
    sheet.save(out, optimize=True)
    return out


def overview(codes: list[str], out: Path, thumb_w: int = 360) -> Path:
    thumb_h = thumb_w * HEIGHT // WIDTH
    gutter, label_w, row_h = 16, 300, thumb_h + 16
    width = label_w + len(SHOTS) * (thumb_w + gutter) + gutter
    sheet = Image.new("RGB", (width, gutter + len(codes) * row_h), "#101215")
    draw = ImageDraw.Draw(sheet)
    big, small = _label_font(34), _label_font(22)
    for row, code in enumerate(codes):
        y = gutter + row * row_h
        spec = get_style(code)
        draw.text((gutter, y + 40), f"{row + 1:02d} {code}", fill="#ffffff", font=big)
        draw.text((gutter, y + 92), spec.name, fill="#b8bec8", font=small)
        draw.text((gutter, y + 124), "／".join(spec.categories), fill="#8a919c", font=small)
        for i, (stem, _, _) in enumerate(SHOTS):
            with Image.open(OUT / code / f"{stem}.jpg") as img:
                x = label_w + i * (thumb_w + gutter)
                sheet.paste(img.resize((thumb_w, thumb_h), Image.LANCZOS), (x, y))
    sheet.save(out, optimize=True)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--styles", default=",".join(style_codes()))
    parser.add_argument("--stock", type=Path, default=DEFAULT_STOCK)
    parser.add_argument("--work", type=Path, default=ROOT / "output" / "slide-styles-10")
    args = parser.parse_args(argv)
    codes = [c.strip() for c in args.styles.split(",") if c.strip()]
    for code in codes:
        get_style(code)
    if not args.stock.is_file():
        parser.error(f"stock still not found: {args.stock}")

    from playwright.sync_api import sync_playwright

    deck = demo_deck()
    results_path = OUT / "measurements.json"
    previous = json.loads(results_path.read_text(encoding="utf-8")) if results_path.is_file() else {}
    results = dict(previous)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
            for code in codes:
                results[code] = render_style(page, deck, code, args.stock, args.work)
                flag = "OK" if not results[code]["problems"] else f"PROBLEMS {results[code]['problems']}"
                print(f"{code}: {flag}", flush=True)
                results_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        finally:
            browser.close()
    ordered = [c for c in style_codes() if c in results]
    overview(ordered, OUT / "overview.png")
    return 1 if any(results[c]["problems"] for c in codes) else 0


if __name__ == "__main__":
    sys.exit(main())
