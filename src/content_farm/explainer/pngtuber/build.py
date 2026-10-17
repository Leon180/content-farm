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
from PIL import Image, ImageDraw, ImageFilter

from content_farm.explainer.pngtuber.cutout import cut_white
from content_farm.explainer.pngtuber.pack import EXPRESSIONS, LAYERS, MOUTH_LAYERS, MOUTH_MODES

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


def _ring_colour(base: Image.Image, center: tuple[int, int], cover: tuple[int, int]) -> tuple[int, int, int]:
    """Median colour just outside the mouth (dark line pixels excluded): what the cover is filled with."""
    rgb = np.asarray(base.convert("RGB"), dtype=np.int16)
    h, w = rgb.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    rx, ry = cover[0] / 2, cover[1] / 2
    d = ((xx - center[0]) / (rx + 8)) ** 2 + ((yy - center[1]) / (ry + 8)) ** 2
    ring = (d <= 1.0) & (((xx - center[0]) / rx) ** 2 + ((yy - center[1]) / ry) ** 2 > 1.0)
    pixels = rgb[ring]
    pixels = pixels[pixels.sum(axis=1) > 200] if (pixels.sum(axis=1) > 200).any() else pixels
    return tuple(int(v) for v in np.median(pixels, axis=0))


def small_o_layer(base: Image.Image, center: tuple[int, int], cover: tuple[int, int], o_size: tuple[int, int],
                  ink: str = "#1c1414", inner: str = "#7a2433") -> Image.Image:
    """Hide the drawn mouth under the surrounding colour and draw a small round 'o' in its place."""
    scale = 4
    w, h = base.size
    cx, cy = center[0] * scale, center[1] * scale
    fill = _ring_colour(base, center, cover)
    rx, ry = cover[0] / 2 * scale, cover[1] / 2 * scale
    # feathered cover: a hard edge shows as a faint ring where the body colour is not perfectly flat
    cover_alpha = Image.new("L", (w * scale, h * scale), 0)
    ImageDraw.Draw(cover_alpha).ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=255)
    cover_alpha = cover_alpha.filter(ImageFilter.GaussianBlur(3 * scale))
    big = Image.new("RGBA", (w * scale, h * scale), (*fill, 0))
    big.putalpha(cover_alpha)
    draw = ImageDraw.Draw(big)
    ox, oy = o_size[0] / 2 * scale, o_size[1] / 2 * scale
    draw.ellipse((cx - ox, cy - oy, cx + ox, cy + oy), fill=inner, outline=ink, width=3 * scale)
    layer = big.resize((w, h), Image.LANCZOS)
    alpha = np.minimum(np.asarray(layer.getchannel("A")), np.asarray(base.getchannel("A")))
    layer.putalpha(Image.fromarray(alpha))
    return layer


def apply_mouth_mode(folder: Path, mode: str, *, center: tuple[int, int] | None = None,
                     cover: tuple[int, int] | None = None,
                     o_sizes: tuple[tuple[int, int], tuple[int, int]] | None = None) -> dict:
    """Switch a built pack's talking mouth: 'frames' (generated, as built), 'none' (mouth never moves),
    'small_o' (the original mouth swapped for a small 'o' at the same spot; ``o_sizes`` = (half, open)
    in canvas px, default from the covered mouth's height)."""
    if mode not in MOUTH_MODES:
        raise ValueError(f"mouth mode {mode!r}; expected one of {MOUTH_MODES}")
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["mouth_mode"] = mode
    if mode == "small_o":
        if center is None or cover is None:
            raise ValueError("small_o needs the mouth center and the size of the area to cover")
        base = Image.open(folder / "base.png").convert("RGBA")
        if o_sizes is None:
            small = max(8, round(cover[1] * 0.9))
            o_sizes = ((small, round(small * 1.1)), (round(small * 1.3), round(small * 1.5)))
        sizes = dict(zip(MOUTH_LAYERS, o_sizes))
        for layer, size in sizes.items():
            small_o_layer(base, center, cover, size).save(folder / f"{layer}.png", optimize=True)
        manifest["mouth"] = {"center": list(center), "cover": list(cover), "o_sizes": {k: list(v) for k, v in sizes.items()}}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


def set_manifest(folder: Path, **fields: object) -> dict:
    """Merge renderer settings (``motion``, ``speech_fx``, …) into a built pack's manifest."""
    path = folder / "manifest.json"
    manifest = {**json.loads(path.read_text(encoding="utf-8")), **fields}
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


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
