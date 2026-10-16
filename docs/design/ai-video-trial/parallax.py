"""2.5D parallax fallback: one depth map per still (Depth Anything V2 Small, Apache-2.0) + per-frame warp → ffmpeg.

Usage: python parallax.py <shots.json> <src_dir> <out_dir>
For every shot in shots.json["shots"] with a "parallax" block, writes <out_dir>/parallax/<id>.mp4
(1280x720, 24 fps, 3 s, 「AI 示意圖」 burned in) and appends a measurement line to <out_dir>/results.jsonl.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForDepthEstimation

from trial_common import label_layer, swap_used_mb

# Local copy kept at ~/.local/share/mlx-video/models/depth-anything-v2-small-hf; override with DEPTH_MODEL.
# Only the Small checkpoint is Apache-2.0 — Base/Large are CC-BY-NC-4.0, do not swap them in.
DEPTH_REPO = os.environ.get("DEPTH_MODEL", "depth-anything/Depth-Anything-V2-Small-hf")
WIDTH, HEIGHT, FPS = 1280, 720, 24
OVERSCAN = 1.10  # base zoom so warped edges never reveal the border


def estimate_depth(image: Image.Image, processor, model, device: str) -> np.ndarray:
    """Relative depth in [0, 1], 1 = nearest, smoothed so the warp does not tear at edges."""
    inputs = processor(images=image, return_tensors="pt").to(device)
    with torch.no_grad():
        predicted = model(**inputs).predicted_depth
    depth = torch.nn.functional.interpolate(predicted.unsqueeze(1), size=(HEIGHT, WIDTH),
                                            mode="bicubic", align_corners=False).squeeze().cpu().numpy()
    depth = (depth - depth.min()) / max(float(depth.max() - depth.min()), 1e-6)
    depth = cv2.dilate(depth, np.ones((9, 9), np.uint8))  # widen foreground so it carries its own edge
    return cv2.GaussianBlur(depth, (0, 0), 6)


def ease(t: float) -> float:
    return t * t * (3 - 2 * t)


def warp_frame(image: np.ndarray, depth: np.ndarray, motion: dict, t: float) -> np.ndarray:
    """Backward-map every output pixel; near pixels (depth→1) move and zoom more than far ones."""
    k = ease(t)
    ys, xs = np.mgrid[0:HEIGHT, 0:WIDTH].astype(np.float32)
    cx, cy = WIDTH / 2, HEIGHT / 2
    zoom = OVERSCAN * (1 + motion.get("zoom", 0.0) * k * (0.35 + 0.65 * depth))
    shift_x = motion.get("pan_x", 0.0) * WIDTH * (k - 0.5) * (depth - 0.5)
    shift_y = motion.get("pan_y", 0.0) * HEIGHT * (k - 0.5) * (depth - 0.5)
    map_x = cx + (xs - cx) / zoom - shift_x
    map_y = cy + (ys - cy) / zoom - shift_y
    return cv2.remap(image, map_x, map_y, interpolation=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)


def render(shot: dict, src_dir: Path, out_path: Path, processor, model, device: str) -> dict:
    still = Image.open(src_dir / shot["image"]).convert("RGB").resize((WIDTH, HEIGHT), Image.LANCZOS)
    swap_before, started = swap_used_mb(), time.monotonic()
    depth = estimate_depth(still, processor, model, device)
    depth_seconds = time.monotonic() - started
    Image.fromarray((depth * 255).astype(np.uint8)).save(out_path.with_suffix(".depth.png"))
    label = np.asarray(label_layer(WIDTH, HEIGHT)).astype(np.float32) / 255.0
    alpha = label[..., 3:4]
    frames = int(shot["seconds"] * FPS)
    source = np.asarray(still)
    argv = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}",
            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(out_path)]
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE)
    for index in range(frames):
        frame = warp_frame(source, depth, shot["parallax"], index / max(frames - 1, 1)).astype(np.float32)
        frame = frame * (1 - alpha) + label[..., :3] * 255.0 * alpha
        proc.stdin.write(frame.clip(0, 255).astype(np.uint8).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed for {out_path}")
    return {"model": "parallax", "segment": shot["id"], "mode": "i2v", "ok": True,
            "seconds": round(time.monotonic() - started, 1), "depth_seconds": round(depth_seconds, 2),
            "frames": frames, "fps": FPS, "size": [WIDTH, HEIGHT], "device": device,
            "swap_before_mb": round(swap_before), "swap_after_mb": round(swap_used_mb()),
            "video": out_path.relative_to(out_path.parent.parent).as_posix(), "motion": shot["parallax"]}


def main() -> int:
    shots_path, src_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    spec = json.loads(shots_path.read_text(encoding="utf-8"))
    (out_dir / "parallax").mkdir(parents=True, exist_ok=True)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    loaded = time.monotonic()
    processor = AutoImageProcessor.from_pretrained(DEPTH_REPO)
    model = AutoModelForDepthEstimation.from_pretrained(DEPTH_REPO).to(device).eval()
    print(f"depth model loaded on {device} in {time.monotonic() - loaded:.1f}s", flush=True)
    with (out_dir / "results.jsonl").open("a", encoding="utf-8") as results:
        for shot in spec["shots"]:
            if "parallax" not in shot:
                continue
            shot = {"seconds": spec["seconds"], **shot}
            row = render(shot, src_dir, out_dir / "parallax" / f"{shot['id']}.mp4", processor, model, device)
            results.write(json.dumps(row, ensure_ascii=False) + "\n")
            results.flush()
            print(f"parallax/{shot['id']}: {row['seconds']}s (depth {row['depth_seconds']}s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
