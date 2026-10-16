"""Objective per-clip numbers to back the eyeball review.

For every labelled clip listed in results.jsonl (latest ok row per model × segment):
- pop:     mean |frame1 - frame0| (0-255). A jump far above `motion` means the clip snaps away from the
           start image on the first frame — visible as a cut when looping or splicing after the still.
- motion:  median mean-abs-diff between consecutive frames from frame 1 on (how much moves).
- drift:   mean |last frame - first frame| (how far the clip wanders from the start image overall).
- color:   mean RGB of the last frame minus the first (tint / exposure drift; + = brighter/warmer channel).
All on 256-px-wide greyscale/RGB downsamples; the 「AI 示意圖」 box is the same in every frame so it cancels out.

Usage: python clip_stats.py <out_dir>   → writes <out_dir>/clip_stats.json and prints a table
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

WIDTH = 256


def frames(path: Path) -> np.ndarray:
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True).stdout.strip()
    width, height = (int(v) for v in probe.split(","))
    out_h = round(height * WIDTH / width / 2) * 2
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={WIDTH}:{out_h}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, out_h, WIDTH, 3).astype(np.float32)


def stats(video: np.ndarray) -> dict:
    grey = video.mean(axis=3)
    diffs = np.abs(np.diff(grey, axis=0)).mean(axis=(1, 2))
    color = video[-1].mean(axis=(0, 1)) - video[0].mean(axis=(0, 1))
    return {"frames": int(video.shape[0]), "pop": round(float(diffs[0]), 2),
            "motion": round(float(np.median(diffs[1:])), 2),
            "drift": round(float(np.abs(grey[-1] - grey[0]).mean()), 2),
            "color_rgb": [round(float(c), 1) for c in color]}


def main() -> int:
    out_dir = Path(sys.argv[1])
    rows: dict[tuple[str, str], dict] = {}
    for line in (out_dir / "results.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get("ok"):
                rows[(row["model"], row["segment"])] = row
    result = []
    for (model, segment), row in sorted(rows.items()):
        entry = {"model": model, "segment": segment, **stats(frames(out_dir / row["video"]))}
        result.append(entry)
        print(f"{model:11} {segment:16} frames={entry['frames']:3} pop={entry['pop']:6} motion={entry['motion']:5} "
              f"drift={entry['drift']:6} color={entry['color_rgb']}")
    (out_dir / "clip_stats.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
