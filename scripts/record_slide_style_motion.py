#!/usr/bin/env python3
"""5-second motion sample for a slide style: count_up (2.5 s) then draw_line (2.5 s).

    PYTHONPATH=src python scripts/record_slide_style_motion.py datajournal collage

Uses the production capturer (``PageCapturer.animate``: fixed-step ``__anim.seek``),
so the clip is exactly what ``media_to_visual`` would produce in that style.
Output: docs/design/slide-styles-10/motion_<code>.mp4
"""

from __future__ import annotations

import sys
from pathlib import Path

from content_farm.explainer import ffmpeg_ops
from content_farm.explainer.capture import PageCapturer
from content_farm.explainer.pages import build_pages
from content_farm.explainer.styles import get_style

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_slide_styles import OUT, ROOT, demo_deck, inject_mascot  # noqa: E402

# big_number count_up (settles at ~1.8 s), timeline draw_line (settles at ~2.65 s)
SEGMENTS = (("s02", 2.1), ("s05", 2.9))


def record(code: str, capturer: PageCapturer, work: Path) -> Path:
    get_style(code)
    deck = demo_deck()
    pages = {p.slide.id: p for p in build_pages(deck, animate=True, style=code)}
    parts = []
    for slide_id, seconds in SEGMENTS:
        html = work / f"{code}_{slide_id}.html"
        html.write_text(inject_mascot(pages[slide_id].html), encoding="utf-8")
        capture = capturer.animate(html, work / f"{code}_{slide_id}.mp4", seconds)
        if capture.problems:
            raise RuntimeError(f"{code}/{slide_id} layout problems: {capture.problems}")
        parts.append(capture.clip)
    out = OUT / f"motion_{code}.mp4"
    listing = work / f"{code}_concat.txt"
    listing.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
    ffmpeg_ops.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(listing), "-c", "copy", "-movflags", "+faststart", str(out)])
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    work = ROOT / "output" / "slide-styles-10" / "motion"
    work.mkdir(parents=True, exist_ok=True)
    with PageCapturer() as capturer:
        for code in argv:
            print(record(code, capturer, work))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
