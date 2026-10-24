"""Review copies: 540p, two parts (<= 13 MB each), 2-pass H.264 + mono AAC 48k.

    python scripts/encode_540p_parts.py --src output/<run>/assembly/release.mp4 --out-dir artifacts/<name> --prefix <name>
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


def encode(src: Path, start: float, length: float, out: Path, video_kbps: int) -> None:
    window = ["-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", str(src)]
    vf = ["-vf", "scale=960:540,setsar=1", "-c:v", "libx264", "-preset", "slow", "-b:v", f"{video_kbps}k", "-pix_fmt", "yuv420p"]
    with tempfile.TemporaryDirectory() as tmp:
        log = str(Path(tmp) / "pass")
        subprocess.run(["ffmpeg", "-y", "-v", "error", *window, *vf, "-pass", "1", "-passlogfile", log, "-an", "-f", "null", "/dev/null"],
                       check=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", *window, *vf, "-pass", "2", "-passlogfile", log, "-c:a", "aac", "-b:a", "48k",
                        "-ac", "1", "-movflags", "+faststart", str(out)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--video-kbps", type=int, default=290)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    total = duration(args.src)
    half = total / 2
    for i, (start, length) in enumerate(((0.0, half), (half, total - half)), start=1):
        out = args.out_dir / f"{args.prefix}-part{i}.mp4"
        encode(args.src, start, length, out, args.video_kbps)
        print(f"{out} {out.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
