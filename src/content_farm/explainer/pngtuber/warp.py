"""Backward bilinear remap shared by the depth warp, head warp and jaw drop."""

from __future__ import annotations

import numpy as np
from PIL import Image


def remap(img: Image.Image, off_x: np.ndarray, off_y: np.ndarray) -> Image.Image:
    """Backward bilinear remap: output pixel (x, y) samples from (x - off_x, y - off_y). Premultiplied
    alpha keeps edges clean."""
    arr = np.asarray(img, dtype=np.float32) / 255.0
    rgb = arr[..., :3] * arr[..., 3:4]
    pre = np.concatenate([rgb, arr[..., 3:4]], axis=-1)
    h, w = off_x.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    sx = np.clip(xx - off_x, 0, w - 1.001)
    sy = np.clip(yy - off_y, 0, h - 1.001)
    x0, y0 = sx.astype(np.int32), sy.astype(np.int32)
    fx, fy = (sx - x0)[..., None], (sy - y0)[..., None]
    out = (pre[y0, x0] * (1 - fx) * (1 - fy) + pre[y0, x0 + 1] * fx * (1 - fy)
           + pre[y0 + 1, x0] * (1 - fx) * fy + pre[y0 + 1, x0 + 1] * fx * fy)
    alpha = out[..., 3:4]
    rgb = np.where(alpha > 1e-4, out[..., :3] / np.maximum(alpha, 1e-4), 0.0)
    return Image.fromarray((np.concatenate([rgb, alpha], axis=-1) * 255).round().astype(np.uint8))
