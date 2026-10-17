"""PNGtuber route: cut out every AI variant, measure how far each drifts from the base, build sheets.

    PYTHONPATH=src python docs/design/channel-hosts/tools/ai_sheet.py <ai_raw_dir>

Out (docs/design/channel-hosts/):
  ai/<code>_<state>.png     cut-out layers, 512 px (base, blink, talk, surprised, smug, wave, drift, alt seed)
  ai/sheet_<code>.png       the strip on the brand background
  ai/consistency.json       silhouette IoU vs the base + mean colour difference inside the shared silhouette

Why IoU: a PNGtuber swaps whole frames (closed / open mouth / blink). If the silhouette moves
between frames the character visibly jumps, so frame-swap needs IoU close to 1. The colour
difference catches "same outline, different character" (palette or pattern drift).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cutout import cut_white  # noqa: E402

from content_farm.assembly.drawtext import find_cjk_font  # noqa: E402

OUT = HERE.parent / "ai"
PICK = {"yokai": 23, "offwork": 11, "cel": 23}
ALT = {"yokai": 11, "offwork": 23, "cel": 11}
STATES = ("base", "blink", "talk", "surprised", "smug", "wave", "drift", "alt")
LABEL = {"base": "定裝", "blink": "眨眼", "talk": "張嘴", "surprised": "驚訝", "smug": "得意", "wave": "揮手（姿勢）",
         "drift": "無參考圖，同 prompt", "alt": "另一個 seed"}
BRAND_BG = {"yokai": "#14110d", "offwork": "#ffd84d", "cel": "#f5f1e8"}
TEXT = {"yokai": "#efe4cb", "offwork": "#141414", "cel": "#1f2329"}


def source(raw: Path, code: str, state: str) -> Path:
    return {"base": raw / f"{code}_base_s{PICK[code]}.png", "alt": raw / f"{code}_base_s{ALT[code]}.png",
            "drift": raw / f"{code}_drift_s37.png"}.get(state, raw / f"{code}_{state}.png")


def metrics(base: Image.Image, other: Image.Image) -> dict[str, float]:
    a = np.asarray(base.getchannel("A")) > 128
    b = np.asarray(other.getchannel("A")) > 128
    both = a & b
    iou = both.sum() / max(1, (a | b).sum())
    rgb_a = np.asarray(base.convert("RGB"), dtype=np.float32)
    rgb_b = np.asarray(other.convert("RGB"), dtype=np.float32)
    colour = float(np.abs(rgb_a - rgb_b)[both].mean()) if both.any() else 255.0
    return {"silhouette_iou": round(float(iou), 3), "mean_rgb_diff_in_overlap": round(colour, 1)}


def build(raw: Path, code: str) -> dict:
    layers, report = {}, {}
    for state in STATES:
        path = source(raw, code, state)
        if not path.is_file():
            report[state] = {"missing": path.name}
            continue
        layers[state] = cut_white(Image.open(path).convert("RGB"))
        small = layers[state].resize((512, 512), Image.LANCZOS)
        small.save(OUT / f"{code}_{state}.png", optimize=True)
    for state, layer in layers.items():
        report[state] = {"file": source(raw, code, state).name, **metrics(layers["base"], layer)}
    sheet(code, layers)
    return report


def sheet(code: str, layers: dict[str, Image.Image]) -> None:
    cell, label_h = 300, 44
    img = Image.new("RGB", (cell * len(layers), cell + label_h), BRAND_BG[code])
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(find_cjk_font(), 24)
    for i, (state, layer) in enumerate(layers.items()):
        thumb = layer.resize((cell, cell), Image.LANCZOS)
        img.paste(thumb, (i * cell, 0), thumb)
        draw.text((i * cell + 12, cell + 8), LABEL[state], font=font, fill=TEXT[code])
    img.save(OUT / f"sheet_{code}.png", optimize=True)


def main(argv: list[str]) -> int:
    raw = Path(argv[0])
    OUT.mkdir(parents=True, exist_ok=True)
    report = {code: build(raw, code) for code in PICK}
    (OUT / "consistency.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for code, rows in report.items():
        for state, row in rows.items():
            print(code, state, row, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
