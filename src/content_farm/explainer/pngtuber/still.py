"""One PNGtuber pose as a transparent PNG cropped to the character (thumbnails), the counterpart of
``explainer.mascot.still.pose_png`` for still-image hosts."""

from __future__ import annotations

from pathlib import Path

from content_farm.explainer.pngtuber.pack import MOUTH_LAYERS, load_pack


def pose_still(pack_ref: str, pose: str, out: Path, *, mouth: int = 0) -> Path:
    """The pack's expression for ``pose`` (mouth closed by default), at the pack's own resolution."""
    pack = load_pack(pack_ref)
    img = pack.base.copy()
    expression = pack.expression_for(pose)
    if expression != "neutral":
        img.alpha_composite(pack.layers[expression])
    if mouth:
        img.alpha_composite(pack.layers[MOUTH_LAYERS[mouth - 1]])
    bbox = img.getchannel("A").getbbox()
    out.parent.mkdir(parents=True, exist_ok=True)
    (img.crop(bbox) if bbox else img).save(out)
    return out
