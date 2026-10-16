"""1920x1080 in-context frames: a real brand slide + the host bottom-right + a mock subtitle line.

    PYTHONPATH=src python docs/design/channel-hosts/tools/frames.py <ai_raw_dir> <work_dir>

Slides come from the real explainer templates (build_pages, brand=<code>, slide 2 of
docs/examples/brands/<code>.json), shot clean (no silhouette placeholder). Hosts:
  vector  png/<id>_front.png (render_svgs.py)
  ai      <ai_raw_dir>/<code>_base_s<seed>.png, white background cut out (cutout.py)
  chipcat the live rig (src/.../mascot/assets/rig.html) at its production overlay origin
Every frame's host layer is checked against overlay.FORBIDDEN (meta row, subtitle band):
the count of host pixels with alpha > 8 inside each rect goes to frames.json.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[3]

from cutout import cut_white  # noqa: E402

from content_farm.assembly.drawtext import find_cjk_font  # noqa: E402
from content_farm.explainer.deck import Deck  # noqa: E402
from content_farm.explainer.mascot.overlay import FORBIDDEN, ORIGIN  # noqa: E402
from content_farm.explainer.pages import build_pages  # noqa: E402

OUT = HERE.parent
W, H = 1920, 1080
RIGHT, BOTTOM = 1908, 1072          # host box anchor (12 px / 8 px from the frame edge)
BOX_H = 352                          # ≈ the live cat's height on frame (440 × 0.86 ≈ 378 incl. margins)
SLIDE_INDEX = 1                      # slide 2: a content slide, not the title

CONCEPTS = {
    # id: (brand, kind, source)
    "y1": ("yokai", "vector", "y1"), "y2": ("yokai", "vector", "y2"), "y3": ("yokai", "ai", "yokai_base_s23.png"),
    "o1": ("offwork", "vector", "o1"), "o2": ("offwork", "vector", "o2"), "o3": ("offwork", "ai", "offwork_base_s11.png"),
    "c1": ("cel", "vector", "c1"), "c2": ("cel", "vector", "c2"), "c3": ("cel", "ai", "cel_base_s23.png"),
    "chipcat": ("chipcat", "rig", "idle"),
}
SUBTITLE = {
    "yokai": "最早的原典裡，牠其實只有一條尾巴",
    "offwork": "需求很簡單，只是要在下班前做完",
    "cel": "一集三十分鐘的預算，到底花去哪裡",
    "chipcat": "先進封裝，就是把晶片疊在一起賣",
}


def shoot_slides(work: Path) -> dict[str, Path]:
    from playwright.sync_api import sync_playwright

    shots = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": W, "height": H})
            for code in sorted({c[0] for c in CONCEPTS.values()}):
                deck = Deck.model_validate(json.loads((ROOT / "docs/examples/brands" / f"{code}.json").read_text("utf-8")))
                slide_page = build_pages(deck, animate=True, brand=code)[SLIDE_INDEX]
                html = work / f"slide_{code}.html"
                html.write_text(slide_page.html, encoding="utf-8")
                page.goto(html.resolve().as_uri(), wait_until="load")
                page.evaluate("document.fonts.ready.then(() => true)")
                if page.evaluate("typeof window.__anim !== 'undefined'"):
                    page.evaluate("window.__anim.seek(1e6)")
                shots[code] = work / f"slide_{code}.png"
                page.screenshot(path=str(shots[code]))
        finally:
            browser.close()
    return shots


def place(img: Image.Image, box_h: int = BOX_H, max_w: int = RIGHT - 1600) -> Image.Image:
    """Scale to box_h tall (narrower if needed), anchor bottom-right on a transparent frame."""
    scale = min(box_h / img.height, max_w / img.width)
    sized = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer.paste(sized, (RIGHT - sized.width, BOTTOM - sized.height), sized)
    return layer


def vector_layer(hid: str) -> Image.Image:
    img = Image.open(OUT / "png" / f"{hid}_front.png").convert("RGBA")
    img = img.crop(img.getbbox())
    if hid == "o1":   # the duo is wider: only the PM dog may sit left of x 1600, and only above the band
        return place(img, max_w=W)
    return place(img)


def ai_layer(raw: Path) -> Image.Image:
    cut = cut_white(Image.open(raw).convert("RGB"))
    return place(cut.crop(cut.getbbox()), box_h=BOX_H - 10)


def rig_layer(pose: str) -> Image.Image:
    from content_farm.explainer.mascot.cues import SceneCue
    from content_farm.explainer.mascot.motion import compose_frames
    from content_farm.explainer.mascot.render import capture_pngs

    cues = (SceneCue(index=1, start=0.0, end=3.0, pose=pose, say=None),)
    frames = compose_frames(cues, np.zeros(90), 30, 90, seed=7)
    png = next(iter(capture_pngs([frames[72]])))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas = Image.open(io.BytesIO(png)).convert("RGBA")
    layer.paste(canvas, ORIGIN, canvas)
    return layer


def intrusions(layer: Image.Image) -> dict[str, int]:
    alpha = np.asarray(layer.getchannel("A"))
    return {name: int((alpha[r.y0:r.y1, r.x0:r.x1] > 8).sum()) for name, r in FORBIDDEN.items()}


def subtitle(frame: Image.Image, text: str) -> None:
    font = ImageFont.truetype(find_cjk_font(), 52)
    draw = ImageDraw.Draw(frame)
    x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font, stroke_width=3)
    draw.text(((W - (x1 - x0)) // 2, H - 80 - (y1 - y0)), text, font=font, fill="#ffffff",
              stroke_width=3, stroke_fill="#000000")


def main(argv: list[str]) -> int:
    raw_dir, work = Path(argv[0]), Path(argv[1])
    work.mkdir(parents=True, exist_ok=True)
    slides = shoot_slides(work)
    report = {}
    for cid, (code, kind, src) in CONCEPTS.items():
        layer = {"vector": lambda: vector_layer(src), "ai": lambda: ai_layer(raw_dir / src),
                 "rig": lambda: rig_layer(src)}[kind]()
        frame = Image.open(slides[code]).convert("RGBA")
        frame.alpha_composite(layer)
        frame = frame.convert("RGB")
        subtitle(frame, SUBTITLE[code])
        out = OUT / "frames" / f"{cid}.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        frame.save(out, quality=88)
        bbox = layer.getbbox()
        report[cid] = {"brand": code, "kind": kind, "source": src, "host_bbox": list(bbox) if bbox else None,
                       "forbidden_pixels": intrusions(layer)}
        print(cid, report[cid], flush=True)
    (OUT / "frames.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if any(sum(r["forbidden_pixels"].values()) for r in report.values()) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
