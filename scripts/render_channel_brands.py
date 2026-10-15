#!/usr/bin/env python3
"""Render the four channel brands for design review.

    PYTHONPATH=src python scripts/render_channel_brands.py [--brands chipcat,yokai] [--skip-assets]

Writes into ``docs/design/channel-brands/``:
    <code>/slide_01..03.jpg     3 demo slides through the real explainer templates (brand=<code>)
    <code>/thumb_1..3.jpg       3 thumbnail mockups (1280x720)
    <code>/icon.png             channel icon (800x800) + icon_circle.png (how YouTube crops it)
    <code>/banner.jpg           channel banner (2560x1440, safe area outlined)
    <code>/shorts.jpg           one Shorts frame (1080x1920)
    <code>/endcard.jpg          end card (shared studio layout, brand tokens)
    overview.png                the four brands side by side
    measurements.json           layout problems + WCAG ratios per brand
Character positions are flat silhouettes only (no generated art).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from content_farm.explainer.brands import BRAND_ASSET_DIR, brand_codes, brand_contrast_report, get_brand
from content_farm.explainer.deck import Deck
from content_farm.explainer.pages import build_pages
from content_farm.explainer.render import _LAYOUT_CHECK_JS, HEIGHT, SAFE_TOP, WIDTH

sys.path.insert(0, str(Path(__file__).resolve().parent))
from brand_assets import ASSET_SHOTS, asset_html, overview_html  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DECKS = ROOT / "docs" / "examples" / "brands"
OUT = ROOT / "docs" / "design" / "channel-brands"

# silhouette colour + halo per brand (a placeholder, so it stays flat and plain)
SILHOUETTE = {
    "chipcat": ("#0e1b2a", "drop-shadow(0 0 2.5px #fff) drop-shadow(0 8px 10px rgba(14,27,42,.25))"),
    "yokai": ("#050403", "drop-shadow(0 0 3px rgba(201,164,92,.9)) drop-shadow(0 0 18px rgba(201,164,92,.35))"),
    "offwork": ("#141414", "drop-shadow(6px 6px 0 #ffffff)"),
    "cel": ("#1f2329", "drop-shadow(0 0 2.5px #fff)"),
}


def silhouette_svg(code: str, *, left: int = 1660, top: int = 728, width: int = 240) -> str:
    colour, halo = SILHOUETTE[code]
    svg = (BRAND_ASSET_DIR / "silhouettes" / f"{code}.svg").read_text(encoding="utf-8")
    height = width * 344 // 240
    style = (f'style="position:absolute;left:{left}px;top:{top}px;width:{width}px;height:{height}px;'
             f'right:auto;bottom:auto;max-width:none;max-height:none;'
             f'color:{colour};filter:{halo};z-index:50;overflow:visible"')
    # class "mascot": the layout check exempts the mascot slot, which is where this sits
    return svg.replace("<svg ", f'<svg class="mascot mascot-ph" {style} ', 1)


def inject_mascot(html: str, code: str) -> str:
    script_at = html.find("<script>")
    end = html.rfind("</div>", 0, script_at if script_at >= 0 else len(html))
    if end < 0:
        raise ValueError("no stage element to attach the mascot placeholder to")
    return html[:end] + silhouette_svg(code) + html[end:]


def load_deck(code: str) -> Deck:
    path = DECKS / f"{code}.json"
    return Deck.model_validate(json.loads(path.read_text(encoding="utf-8")))


def shoot(page: object, html: str, html_path: Path, out: Path, *, size: tuple[int, int]) -> list[str]:
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")
    page.set_viewport_size({"width": size[0], "height": size[1]})
    page.goto(html_path.resolve().as_uri(), wait_until="load")
    page.evaluate("document.fonts.ready.then(() => true)")
    if page.evaluate("typeof window.__anim !== 'undefined'"):
        page.evaluate("window.__anim.seek(1e6)")
    problems: list[str] = []
    if page.evaluate("!!document.querySelector('.content')"):
        problems = list(page.evaluate(_LAYOUT_CHECK_JS, [SAFE_TOP, WIDTH, HEIGHT]))
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix == ".jpg":
        page.screenshot(path=str(out), type="jpeg", quality=86)
    else:
        page.screenshot(path=str(out))
    return problems


def missing_fonts(page: object, families: list[str]) -> list[str]:
    """Families the browser cannot resolve (it silently falls back otherwise)."""
    return [f for f in families if not page.evaluate("f => document.fonts.check(`40px \"${f}\"`, '字')", f)]


def render_brand(page: object, code: str, work: Path, *, assets: bool) -> dict:
    get_brand(code)
    deck = load_deck(code)
    problems: dict[str, list[str]] = {}
    frames = []
    for i, slide_page in enumerate(build_pages(deck, animate=True, brand=code), 1):
        out = OUT / code / f"slide_{i:02d}.jpg"
        found = shoot(page, inject_mascot(slide_page.html, code), work / code / f"slide_{i:02d}.html",
                      out, size=(WIDTH, HEIGHT))
        if found:
            problems[out.stem] = found
        frames.append(str(out.relative_to(OUT)))
    if assets:
        for stem, size in ASSET_SHOTS:
            ext = ".png" if stem.startswith("icon") else ".jpg"
            out = OUT / code / f"{stem}{ext}"
            shoot(page, asset_html(code, stem, silhouette_svg), work / code / f"{stem}.html", out, size=size)
            frames.append(str(out.relative_to(OUT)))
    return {"code": code, "frames": frames, "problems": problems, "contrast": brand_contrast_report(code)}


FONT_FAMILIES = ["Noto Sans CJK TC", "Songti TC", "Weibei TC", "Kaiti TC", "Yuanti TC", "HanziPen TC",
                 "DIN Condensed", "SF Mono", "Arial Rounded MT Bold"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--brands", default=",".join(brand_codes()))
    parser.add_argument("--skip-assets", action="store_true")
    parser.add_argument("--work", type=Path, default=ROOT / "output" / "channel-brands")
    args = parser.parse_args(argv)
    codes = [c.strip() for c in args.brands.split(",") if c.strip()]
    for code in codes:
        get_brand(code)

    from playwright.sync_api import sync_playwright

    results_path = OUT / "measurements.json"
    results = json.loads(results_path.read_text(encoding="utf-8")) if results_path.is_file() else {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
            page.set_content("<p>字</p>")
            results["_missing_fonts"] = missing_fonts(page, FONT_FAMILIES)
            print("missing fonts:", results["_missing_fonts"], flush=True)
            for code in codes:
                results[code] = render_brand(page, code, args.work, assets=not args.skip_assets)
                flag = "OK" if not results[code]["problems"] else f"PROBLEMS {results[code]['problems']}"
                print(f"{code}: {flag}", flush=True)
                results_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            if not args.skip_assets and all(c in results for c in brand_codes()):
                shoot(page, overview_html(OUT), args.work / "overview.html", OUT / "overview.png", size=(2400, 1500))
        finally:
            browser.close()
    return 1 if any(results[c]["problems"] for c in codes) else 0


if __name__ == "__main__":
    sys.exit(main())
