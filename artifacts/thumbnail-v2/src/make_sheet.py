"""Contact sheet: the 3 options, their 168x94 phone previews (true size) and the old thumbnail for comparison.

    python artifacts/thumbnail-v2/src/make_sheet.py --run-dir <scratch run> --old <old thumbnail.jpg> --out <sheet.png>
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = "/System/Library/Fonts/STHeiti Medium.ttc"   # content_farm.assembly.drawtext.find_cjk_font() on this Mac
BG, INK, MUTED = (246, 240, 226), (58, 34, 16), (130, 105, 80)
CELL = (600, 338)
TINY = (168, 94)


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, size)


def _fit(path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGB").resize(size, Image.LANCZOS)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    thumbs = args.run_dir / "thumbnails"
    cells = [("A  誰會贏？", thumbs / "variant_a.jpg"), ("B  打還是讓？", thumbs / "variant_b.jpg"),
             ("C  為什麼沒人贏", thumbs / "variant_c.jpg")]
    margin, gap, head = 30, 24, 90
    width = margin * 2 + CELL[0] * 3 + gap * 2
    height = head + CELL[1] + 40 + 230 + 70 + CELL[1] + 60
    sheet = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(sheet)
    draw.text((margin, 22), "不奇而寓 · 中片縮圖 v2（1280×720，三選項）", font=_font(34), fill=INK)
    for index, (label, path) in enumerate(cells):
        x = margin + index * (CELL[0] + gap)
        sheet.paste(_fit(path, CELL), (x, head))
        draw.text((x, head + CELL[1] + 6), f"{label}  ·  {path.stat().st_size // 1024} KB", font=_font(24), fill=INK)
        tiny_y = head + CELL[1] + 50
        sheet.paste(_fit(path, TINY), (x, tiny_y))
        sheet.paste(_fit(path, (TINY[0] * 2, TINY[1] * 2)), (x + TINY[0] + 20, tiny_y))
        draw.text((x, tiny_y + TINY[1] * 2 + 6), "168×94 實際大小（左）與 2 倍放大（右）", font=_font(18), fill=MUTED)
    old_y = head + CELL[1] + 40 + 230 + 70
    draw.text((margin, old_y - 36), "舊版對照（寓言學堂標籤、標題整句壓底、主角小）", font=_font(24), fill=INK)
    sheet.paste(_fit(args.old, CELL), (margin, old_y))
    sheet.paste(_fit(args.old, TINY), (margin + CELL[0] + gap, old_y))
    draw.text((margin + CELL[0] + gap, old_y + TINY[1] + 6), "舊版 168×94", font=_font(18), fill=MUTED)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.out)
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
