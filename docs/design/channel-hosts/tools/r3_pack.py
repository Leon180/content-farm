"""Round 3: build the three PNGtuber packs from r3_gen.py output and review sheets.

    PYTHONPATH=src python docs/design/channel-hosts/tools/r3_pack.py <r3_raw_dir>

Writes src/content_farm/explainer/pngtuber/packs/<id>/ and docs/design/channel-hosts/round3/:
  sheet_<id>.png   row 1: raw generated states; row 2: what the renderer composes from the pack
  packs.json       face box, silhouette IoU and changed pixels per layer
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from content_farm.assembly.drawtext import find_cjk_font
from content_farm.explainer.pngtuber.build import apply_mouth_mode, build_pack
from content_farm.explainer.pngtuber.motion import HostFrame
from content_farm.explainer.pngtuber.pack import PACK_ROOT, load_pack
from content_farm.explainer.pngtuber.render import Composer, Placement

OUT = Path(__file__).resolve().parents[1] / "round3"
PACKS = {  # round-2 id → (pack id, name, brand background)
    "Y14": ("frog-scribe", "青蛙書記", "#14110d"),
    "O25": ("cooler-goldfish", "飲水機金魚", "#ffd84d"),
    "C09": ("paint-bottle", "顏料瓶老師傅", "#f5f1e8"),
}
# Leon 2026-10-17 after the trials: C09's talking mouth sat in the wrong place, O25's did not suit the
# fish. Both now keep their own mouth and only swap it for a small 'o' at the same spot (canvas px,
# measured on base.png). Y14 keeps the generated mouths.
MOUTHS = {
    "paint-bottle": {"mode": "small_o", "center": (386, 378), "cover": (52, 24), "o_sizes": ((13, 14), (17, 20))},
    "cooler-goldfish": {"mode": "small_o", "center": (393, 430), "cover": (64, 40), "o_sizes": ((12, 13), (16, 19))},
}
SOURCE = {"model": "FLUX.2 [klein] 4B (q4), mflux, klein multi-reference edit", "license": "Apache-2.0",
          "license_url": "https://huggingface.co/black-forest-labs/FLUX.2-klein-4B/blob/main/LICENSE.md",
          "note": "AI-generated; Leon 2026-10-17 approved AI images as hosts. Purely AI output may not be "
                  "protected by copyright."}
RAW_STATES = ("base", "mouth_half", "mouth_open", "blink", "surprised", "smug", "speechless")
COMPOSED = (("neutral", 0, False, "閉嘴"), ("neutral", 1, False, "半開"), ("neutral", 2, False, "張嘴"),
            ("neutral", 0, True, "眨眼"), ("surprised", 0, False, "驚訝"), ("smug", 0, False, "得意"),
            ("speechless", 0, False, "無言"), ("smug", 2, False, "得意＋說話"))
SHEET_CELL = 260
REVIEW = Placement("review", (0, 0), (SHEET_CELL, SHEET_CELL), (0, 0), height=236, max_width=236,
                   anchor="left", margin_x=12, margin_bottom=10, forbidden={})


def sheet(pick: str, raw: Path, pack_id: str, bg: str) -> Path:
    cols = max(len(RAW_STATES), len(COMPOSED))
    img = Image.new("RGB", (SHEET_CELL * cols, SHEET_CELL * 2 + 80), bg)
    draw, font = ImageDraw.Draw(img), ImageFont.truetype(find_cjk_font(), 22)
    ink = "#efe4cb" if bg == "#14110d" else "#1f2329"
    for i, state in enumerate(RAW_STATES):
        thumb = Image.open(raw / pick / f"{state}.png").convert("RGB").resize((SHEET_CELL - 8, SHEET_CELL - 8))
        img.paste(thumb, (i * SHEET_CELL + 4, 4))
        draw.text((i * SHEET_CELL + 8, SHEET_CELL + 2), f"生成：{state}", font=font, fill=ink)
    composer = Composer(load_pack(f"pngtuber/{pack_id}"), REVIEW)
    for i, (expr, mouth, blink, label) in enumerate(COMPOSED):
        canvas = composer.canvas(HostFrame(expr, mouth, blink, 1.0, 0.0, 0.0))
        img.paste(canvas, (i * SHEET_CELL, SHEET_CELL + 36), canvas)
        draw.text((i * SHEET_CELL + 8, 2 * SHEET_CELL + 40), f"組合：{label}", font=font, fill=ink)
    out = OUT / f"sheet_{pack_id}.png"
    img.save(out, optimize=True)
    return out


def main(argv: list[str]) -> int:
    raw = Path(argv[0])
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    for pick, (pack_id, name, bg) in PACKS.items():
        built = build_pack(raw / pick, PACK_ROOT / pack_id, pack_id, name, source={**SOURCE, "round2_id": pick})
        if pack_id in MOUTHS:
            m = MOUTHS[pack_id]
            apply_mouth_mode(PACK_ROOT / pack_id, m["mode"], center=m["center"], cover=m["cover"], o_sizes=m["o_sizes"])
        report[pack_id] = {"pick": pick, "regions": built.regions, "silhouette_iou": built.iou,
                           "changed_px": built.changed_px, "sheet": sheet(pick, raw, pack_id, bg).name}
        print(pack_id, report[pack_id], flush=True)
    (OUT / "packs.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
