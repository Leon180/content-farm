"""Depth map for a PNGtuber pack's base image (Depth Anything V2 Small, Apache-2.0).

Runs in the mlx-video venv (torch / transformers), like motion_parallax_worker.py, whose
``estimate_depth`` it reuses:

    $CF_MLX_VIDEO_HOME/venv/bin/python scripts/host_depth_worker.py --pack-dir <pack> --depth-model <dir>

Writes <pack>/depth.png: 16-bit, 0 = farthest .. 65535 = nearest, normalised inside the character's
alpha only (the white background would otherwise take most of the range), 0 outside it.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from motion_parallax_worker import estimate_depth  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pack-dir", type=Path, required=True)
    parser.add_argument("--depth-model", required=True)
    args = parser.parse_args(argv)
    base = Image.open(args.pack_dir / "base.png").convert("RGBA")
    flat = Image.new("RGB", base.size, "white")
    flat.paste(base, mask=base.getchannel("A"))
    started = time.monotonic()
    depth = estimate_depth(flat, args.depth_model, base.size)
    alpha = np.asarray(base.getchannel("A")) > 128
    if not alpha.any():
        raise SystemExit("base.png is empty")
    inside = depth[alpha]
    lo, hi = np.percentile(inside, 2), np.percentile(inside, 98)
    norm = np.clip((depth - lo) / max(hi - lo, 1e-6), 0.0, 1.0) * alpha
    Image.fromarray((norm * 65535).astype(np.uint16)).save(args.pack_dir / "depth.png")
    print(json.dumps({"pack": args.pack_dir.name, "seconds": round(time.monotonic() - started, 2),
                      "near_share": round(float((norm[alpha] > 0.66).mean()), 3)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
