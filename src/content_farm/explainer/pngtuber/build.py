"""Build a pack from whole-frame source images (one generated image per state, same canvas).

Generated edits are never pixel-identical to the base (outline jitter, slight colour drift), so whole
frames would shimmer when swapped, and a loose patch drags that jitter along (a talking mouth over
an expression would paste the neutral eyes back as ghosts). So every layer gets a *tight region*:
the bounding box of its significant change (strong difference, thin jitter removed by an opening,
outliers trimmed by percentiles) plus a small margin. Inside the region the layer replaces the base
completely, with feathered edges. Both mouth layers share the wide-open mouth's region.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from content_farm.explainer.pngtuber.cutout import cut_white
from content_farm.explainer.pngtuber.pack import EXPRESSIONS, LAYERS, MOUTH_LAYERS

DIFF_THRESHOLD = 40      # max channel difference that counts as a real change
OPEN_PX = 3              # opening kernel: removes outline jitter a pixel or two wide
TRIM_PERCENTILE = 1.0    # ignore the outermost 1 % of changed pixels on each side (stray specks)
REGION_MARGIN = 14
FEATHER_PX = 4


Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class Built:
    folder: Path
    regions: dict[str, Box]
    iou: dict[str, float]
    changed_px: dict[str, int]


def silhouette_iou(a: Image.Image, b: Image.Image) -> float:
    ma, mb = np.asarray(a.getchannel("A")) > 128, np.asarray(b.getchannel("A")) > 128
    return float((ma & mb).sum() / max(1, (ma | mb).sum()))


def significant_change(base: Image.Image, other: Image.Image) -> np.ndarray:
    """Strongly changed pixels, minus thin outline jitter (morphological opening)."""
    a = np.asarray(base.convert("RGB"), dtype=np.int16)
    b = np.asarray(other.convert("RGB"), dtype=np.int16)
    changed = Image.fromarray(((np.abs(a - b).max(axis=-1) > DIFF_THRESHOLD) * 255).astype(np.uint8))
    opened = changed.filter(ImageFilter.MinFilter(OPEN_PX)).filter(ImageFilter.MaxFilter(OPEN_PX))
    return np.asarray(opened) > 0


def region_of(mask: np.ndarray, size: tuple[int, int], margin: int = REGION_MARGIN) -> Box:
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        raise ValueError("source frame does not differ from the base: nothing to animate")
    lo, hi = TRIM_PERCENTILE, 100 - TRIM_PERCENTILE
    x0, x1 = np.percentile(xs, [lo, hi])
    y0, y1 = np.percentile(ys, [lo, hi])
    w, h = size
    return (max(0, int(x0) - margin), max(0, int(y0) - margin),
            min(w, int(x1) + margin + 1), min(h, int(y1) + margin + 1))


def patch(frame: Image.Image, region: Box) -> Image.Image:
    """The frame inside ``region`` (feathered edges), transparent elsewhere."""
    w, h = frame.size
    rect = Image.new("L", (w, h), 0)
    inset = FEATHER_PX
    rect.paste(255, (region[0] + inset, region[1] + inset, region[2] - inset, region[3] - inset))
    alpha = np.minimum(np.asarray(rect.filter(ImageFilter.GaussianBlur(FEATHER_PX))),
                       np.asarray(frame.getchannel("A")))
    out = frame.copy()
    out.putalpha(Image.fromarray(alpha))
    return out


def build_pack(src: Path, out: Path, pack_id: str, name: str, *, source: dict | None = None,
               pose_map: dict[str, str] | None = None) -> Built:
    """``src`` holds base.png + one png per layer (white background); writes the pack to ``out``."""
    frames = {state: cut_white(Image.open(src / f"{state}.png").convert("RGB")) for state in ("base", *LAYERS)}
    base, size = frames["base"], frames["base"].size
    masks = {state: significant_change(base, frames[state]) for state in LAYERS}
    mouth_region = region_of(masks["mouth_open"] | masks["mouth_half"], size)
    regions = {state: mouth_region if state in MOUTH_LAYERS else region_of(masks[state], size) for state in LAYERS}
    out.mkdir(parents=True, exist_ok=True)
    base.save(out / "base.png", optimize=True)
    iou = {state: round(silhouette_iou(base, frames[state]), 4) for state in LAYERS}
    changed = {state: int(masks[state].sum()) for state in LAYERS}
    for state in LAYERS:
        patch(frames[state], regions[state]).save(out / f"{state}.png", optimize=True)
    manifest = {"id": pack_id, "name": name, "size": list(size), "layers": list(LAYERS),
                "mouth_layers": list(MOUTH_LAYERS), "regions": {k: list(v) for k, v in regions.items()},
                "expressions": list(EXPRESSIONS), "pose_map": pose_map or {}, "silhouette_iou": iou,
                "changed_px": changed, "source": source or {}}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return Built(out, regions, iou, changed)
