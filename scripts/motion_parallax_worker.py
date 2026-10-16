"""2.5D parallax clip from one still: Depth Anything V2 Small depth + per-frame warp → H.264.

Runs in the mlx-video venv (torch / transformers / opencv), not the repo venv, so it imports
nothing from content_farm. ``content_farm.explainer.motion`` calls it and reads the one JSON
line it prints on success.

Usage:
    python motion_parallax_worker.py --image s06.png --out s06.parallax.mp4 --depth-model <dir> \
        [--seconds 3] [--zoom 0.06] [--pan-x 0.02] [--pan-y 0] [--thin-px 31] [--max-shift-px 18]

Thin-object mitigation (reeds, whiskers, tails tear when they move against the background):
1. *thin mask*: a morphological opening of the depth map with a ``thin-px`` disc removes near
   structures narrower than the disc; those pixels take the opened (background) depth, so they
   travel with what is behind them instead of stretching it;
2. *edge feather*: the depth map is dilated then blurred so a foreground edge carries its own
   border instead of smearing the background;
3. *shift cap*: the depth-dependent part of the motion is scaled so no pixel moves more than
   ``max-shift-px`` relative to a flat (Ken Burns-like) move.
``--no-mitigation`` turns 1 and 3 off (for before/after comparisons).

Only the Small checkpoint is Apache-2.0 (Base/Large/Giant are CC-BY-NC-4.0): never swap them in.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForDepthEstimation

OVERSCAN = 1.08  # base zoom so warped edges never reveal the frame border


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--depth-model", required=True, help="local dir of Depth-Anything-V2-Small-hf")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--zoom", type=float, default=0.06)
    parser.add_argument("--pan-x", type=float, default=0.0)
    parser.add_argument("--pan-y", type=float, default=0.0)
    parser.add_argument("--thin-px", type=int, default=31)
    parser.add_argument("--max-shift-px", type=float, default=18.0)
    parser.add_argument("--no-mitigation", action="store_true")
    return parser.parse_args(argv)


def estimate_depth(image: Image.Image, model_dir: str, size: tuple[int, int]) -> np.ndarray:
    """Relative depth in [0, 1], 1 = nearest, at ``size`` (width, height)."""
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    processor = AutoImageProcessor.from_pretrained(model_dir)
    model = AutoModelForDepthEstimation.from_pretrained(model_dir).to(device).eval()
    inputs = processor(images=image, return_tensors="pt").to(device)
    with torch.no_grad():
        predicted = model(**inputs).predicted_depth
    width, height = size
    depth = torch.nn.functional.interpolate(predicted.unsqueeze(1), size=(height, width),
                                            mode="bicubic", align_corners=False).squeeze().cpu().numpy()
    return (depth - depth.min()) / max(float(depth.max() - depth.min()), 1e-6)


def flatten_thin(depth: np.ndarray, thin_px: int) -> tuple[np.ndarray, float]:
    """Give near structures narrower than ``thin_px`` the depth behind them; returns the share
    of pixels changed by more than 0.05."""
    disc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (thin_px, thin_px))
    opened = cv2.morphologyEx(depth.astype(np.float32), cv2.MORPH_OPEN, disc)
    return opened, float(np.mean((depth - opened) > 0.05))


def feather(depth: np.ndarray) -> np.ndarray:
    depth = cv2.dilate(depth.astype(np.float32), np.ones((9, 9), np.uint8))
    return cv2.GaussianBlur(depth, (0, 0), 6)


def ease(t: float) -> float:
    """Smoothstep: zero velocity at both ends, so a ping-pong loop turns without a jolt."""
    return t * t * (3 - 2 * t)


class Warp:
    """Backward map: near pixels (depth→1) zoom and pan more than far ones."""

    def __init__(self, depth: np.ndarray, args: argparse.Namespace) -> None:
        self.height, self.width = depth.shape
        self.ys, self.xs = np.mgrid[0:self.height, 0:self.width].astype(np.float32)
        self.args = args
        self.depth = depth
        self.strength = 1.0

    def maps(self, k: float, depth: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        d = 0.5 + self.strength * ((self.depth if depth is None else depth) - 0.5)
        a, cx, cy = self.args, self.width / 2, self.height / 2
        zoom = OVERSCAN * (1 + a.zoom * k * (0.35 + 0.65 * d))
        shift_x = a.pan_x * self.width * (k - 0.5) * (d - 0.5)
        shift_y = a.pan_y * self.height * (k - 0.5) * (d - 0.5)
        return cx + (self.xs - cx) / zoom - shift_x, cy + (self.ys - cy) / zoom - shift_y

    def depth_shift_px(self) -> float:
        """Largest displacement (either end of the move) relative to the same move on a flat scene."""
        flat = np.full_like(self.depth, 0.5)
        worst = 0.0
        for k in (0.0, 1.0):
            mx, my = self.maps(k)
            fx, fy = self.maps(k, flat)
            worst = max(worst, float(np.max(np.hypot(mx - fx, my - fy))))
        return worst

    def cap(self, max_shift_px: float) -> None:
        raw = self.depth_shift_px()
        self.strength = min(1.0, max_shift_px / raw) if raw > 0 else 1.0


def encode(frames, out: Path, size: tuple[int, int], fps: int) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    width, height = size
    argv = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{width}x{height}", "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264",
            "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", str(out)]
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE)
    try:
        for frame in frames:
            proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed writing {out}")


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    if not 0 < args.seconds <= 3.0:
        raise SystemExit("--seconds must be in (0, 3]")
    started = time.monotonic()
    size = (args.width, args.height)
    still = Image.open(args.image).convert("RGB").resize(size, Image.LANCZOS)
    depth = estimate_depth(still, args.depth_model, size)
    depth_seconds = time.monotonic() - started
    thin_share = 0.0
    if not args.no_mitigation:
        depth, thin_share = flatten_thin(depth, args.thin_px)
    warp = Warp(feather(depth), args)
    raw_shift = warp.depth_shift_px()
    if not args.no_mitigation:
        warp.cap(args.max_shift_px)
    source = np.asarray(still)
    total = max(2, round(args.seconds * args.fps))

    def frames():
        for index in range(total):
            map_x, map_y = warp.maps(ease(index / (total - 1)))
            yield cv2.remap(source, map_x, map_y, interpolation=cv2.INTER_CUBIC,
                            borderMode=cv2.BORDER_REFLECT)

    encode(frames(), args.out, size, args.fps)
    print(json.dumps({"ok": True, "frames": total, "fps": args.fps, "seconds": round(total / args.fps, 3),
                      "size": list(size), "build_seconds": round(time.monotonic() - started, 2),
                      "depth_seconds": round(depth_seconds, 2), "thin_share": round(thin_share, 4),
                      "depth_shift_px_raw": round(raw_shift, 1),
                      "depth_shift_px": round(warp.depth_shift_px(), 1),
                      "depth_strength": round(warp.strength, 3), "mitigation": not args.no_mitigation}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
