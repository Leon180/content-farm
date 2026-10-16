"""Write every vector host expression as SVG, then PNG (transparent), plus a review sheet.

    PYTHONPATH=src python docs/design/channel-hosts/tools/render_svgs.py

Out (docs/design/channel-hosts/): svg/<id>_<expr>.svg, png/<id>_<expr>.png, sheet_vector.png
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import chars_cel  # noqa: E402
import chars_offwork  # noqa: E402
import chars_yokai  # noqa: E402

OUT = HERE.parent
HOSTS = {**chars_yokai.HOSTS, **chars_offwork.HOSTS, **chars_cel.HOSTS}
BRAND_BG = {"y": "#14110d", "o": "#ffd84d", "c": "#f5f1e8"}


def write_svgs() -> list[tuple[str, str, Path]]:
    written = []
    for hid, (_, draw, exprs) in HOSTS.items():
        for expr in exprs:
            path = OUT / "svg" / f"{hid}_{expr}.svg"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(draw(expr, f"{hid}-{expr}"), encoding="utf-8")
            written.append((hid, expr, path))
    return written


def render_pngs(svgs: list[tuple[str, str, Path]], scale: float = 2.0) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(device_scale_factor=scale)
            for hid, expr, path in svgs:
                svg = path.read_text(encoding="utf-8")
                width = 560 if 'viewBox="0 0 560' in svg else 400
                page.set_viewport_size({"width": width + 40, "height": 480})
                page.set_content(f'<html><body style="margin:0;background:transparent">'
                                 f'<div style="padding:20px">{svg}</div></body></html>')
                page.evaluate("document.fonts.ready.then(() => true)")
                out = OUT / "png" / f"{hid}_{expr}.png"
                out.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(out), omit_background=True)
                print(out.relative_to(OUT), flush=True)
        finally:
            browser.close()


def review_sheet(svgs: list[tuple[str, str, Path]]) -> Path:
    from PIL import Image

    rows: dict[str, list[Path]] = {}
    for hid, expr, _ in svgs:
        rows.setdefault(hid, []).append(OUT / "png" / f"{hid}_{expr}.png")
    cell_w, cell_h = 600, 520
    sheet = Image.new("RGB", (cell_w * 3, cell_h * len(rows)), "#888888")
    for r, (hid, paths) in enumerate(rows.items()):
        bg = Image.new("RGB", (cell_w * 3, cell_h), BRAND_BG[hid[0]])
        sheet.paste(bg, (0, r * cell_h))
        for c, p in enumerate(paths):
            im = Image.open(p).convert("RGBA")
            im.thumbnail((cell_w, cell_h))
            sheet.paste(im, (c * cell_w + (cell_w - im.width) // 2, r * cell_h + (cell_h - im.height) // 2), im)
    out = OUT / "sheet_vector.png"
    sheet.save(out, optimize=True)
    return out


def main() -> int:
    svgs = write_svgs()
    render_pngs(svgs)
    print(review_sheet(svgs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
