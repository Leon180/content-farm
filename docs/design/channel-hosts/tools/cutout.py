"""Cut a generated character off its plain white background (PNGtuber layer).

Flood-fills from the border so white *inside* the character (eyes, belly, a ghost's body)
is kept; only background connected to the edge becomes transparent. The edge is pulled in
by one pixel and softened so the anti-aliased white fringe does not glow on dark brands.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

KEY = (255, 0, 255)


def cut_white(img: Image.Image, thresh: int = 38) -> Image.Image:
    padded = ImageOps.expand(img.convert("RGB"), border=2, fill=(255, 255, 255))
    ImageDraw.floodfill(padded, (0, 0), KEY, thresh=thresh)
    arr = np.asarray(padded)
    background = np.all(arr == KEY, axis=-1)
    alpha = Image.fromarray(np.where(background, 0, 255).astype(np.uint8))
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    out = ImageOps.expand(img.convert("RGB"), border=2, fill=(255, 255, 255)).convert("RGBA")
    out.putalpha(alpha)
    return out.crop((2, 2, out.width - 2, out.height - 2))
