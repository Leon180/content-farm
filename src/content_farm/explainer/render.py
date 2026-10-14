"""Screenshot slide pages with one shared headless Chromium, check layout, build a contact sheet.

Overflow is a hard failure: a slide whose content is clipped, spills into the
subtitle safe zone, or leaves the frame is reported by index and id. PNGs are
still written so the problem can be inspected, but no contact sheet is made —
the review gate only ever sees a deck that rendered cleanly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from content_farm.assembly.drawtext import find_cjk_font
from content_farm.explainer.pages import SlidePage

WIDTH, HEIGHT = 1920, 1080
SAFE_TOP = 880  # keep in sync with --safe-top in templates/base.css

# Returns a list of human-readable problems for the current page.
_LAYOUT_CHECK_JS = """
([safeTop, width, height]) => {
  const problems = [];
  const describe = (el) => {
    const cls = el.className && typeof el.className === 'string'
      ? '.' + el.className.trim().split(/\\s+/).join('.') : '';
    const text = (el.textContent || '').trim().slice(0, 20);
    return `<${el.tagName.toLowerCase()}${cls}>` + (text ? ` "${text}"` : '');
  };
  const content = document.querySelector('.content');
  if (content.scrollHeight > content.clientHeight + 1)
    problems.push(`content too tall: ${content.scrollHeight}px > ${content.clientHeight}px box`);
  if (content.scrollWidth > content.clientWidth + 1)
    problems.push(`content too wide: ${content.scrollWidth}px > ${content.clientWidth}px box`);
  for (const el of document.querySelectorAll('.stage *')) {
    if (el.closest('.safe-zone, .mascot, .meta, .topbar')) continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.bottom > safeTop + 0.5)
      problems.push(`${describe(el)} enters subtitle safe zone (bottom ${Math.round(r.bottom)}px)`);
    if (r.right > width + 0.5 || r.left < -0.5)
      problems.push(`${describe(el)} leaves the frame horizontally`);
  }
  return problems;
}
"""


@dataclass(frozen=True)
class RenderedSlide:
    index: int
    slide_id: str
    layout: str
    html_path: Path
    png_path: Path
    problems: tuple[str, ...] = ()


class SlideOverflowError(RuntimeError):
    def __init__(self, failed: Sequence[RenderedSlide]) -> None:
        self.failed = tuple(failed)
        lines = [
            f"slide {r.index:02d} ({r.slide_id}, {r.layout}): {p}"
            for r in self.failed for p in r.problems
        ]
        super().__init__(f"{len(self.failed)} slide(s) overflow:\n" + "\n".join(lines))


def write_html(pages: Sequence[SlidePage], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for page in pages:
        path = out_dir / f"{page.stem}.html"
        path.write_text(page.html, encoding="utf-8")
        paths.append(path)
    return paths


def render_pages(pages: Sequence[SlidePage], out_dir: Path) -> tuple[RenderedSlide, ...]:
    """Write HTML + PNG for every page using one browser; raise on any overflow."""
    from playwright.sync_api import sync_playwright

    html_paths = write_html(pages, out_dir)
    rendered: list[RenderedSlide] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
            for slide_page, html_path in zip(pages, html_paths):
                rendered.append(_shoot(page, slide_page, html_path))
        finally:
            browser.close()

    failed = [r for r in rendered if r.problems]
    if failed:
        raise SlideOverflowError(failed)
    return tuple(rendered)


def _shoot(page: object, slide_page: SlidePage, html_path: Path) -> RenderedSlide:
    page.goto(html_path.resolve().as_uri(), wait_until="load")  # type: ignore[attr-defined]
    page.evaluate("document.fonts.ready.then(() => true)")  # type: ignore[attr-defined]
    problems = page.evaluate(_LAYOUT_CHECK_JS, [SAFE_TOP, WIDTH, HEIGHT])  # type: ignore[attr-defined]
    png_path = html_path.with_suffix(".png")
    page.screenshot(path=str(png_path), full_page=False)  # type: ignore[attr-defined]
    return RenderedSlide(
        index=slide_page.index,
        slide_id=slide_page.slide.id,
        layout=slide_page.slide.layout.value,
        html_path=html_path,
        png_path=png_path,
        problems=tuple(problems),
    )


def make_contact_sheet(
    slides: Sequence[RenderedSlide],
    out_path: Path,
    *,
    columns: int = 3,
    thumb_width: int = 560,
) -> Path:
    """Grid of thumbnails labelled ``NN · id · layout`` for the review gate."""
    if not slides:
        raise ValueError("no slides for contact sheet")
    thumb_h = thumb_width * HEIGHT // WIDTH
    gutter, label_h = 24, 44
    rows = -(-len(slides) // columns)
    sheet = Image.new(
        "RGB",
        (gutter + columns * (thumb_width + gutter), gutter + rows * (thumb_h + label_h + gutter)),
        "#0e0f12",
    )
    draw = ImageDraw.Draw(sheet)
    font = _label_font(24)
    for i, slide in enumerate(slides):
        col, row = i % columns, i // columns
        x = gutter + col * (thumb_width + gutter)
        y = gutter + row * (thumb_h + label_h + gutter)
        with Image.open(slide.png_path) as img:
            sheet.paste(img.convert("RGB").resize((thumb_width, thumb_h), Image.LANCZOS), (x, y))
        draw.text((x, y + thumb_h + 8), f"{slide.index:02d} · {slide.slide_id} · {slide.layout}",
                  fill="#d8dbe0", font=font)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, optimize=True)
    return out_path


def _label_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    path = find_cjk_font()
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()
