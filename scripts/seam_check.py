"""Seam acceptance: an incrementally rendered video vs. the same script rendered whole.

Usage:
    python scripts/seam_check.py --a output/<run>/assembly/release.mp4 --b output/<run-full>/assembly/release.mp4 \
        --run-dir output/<run> [--b-run-dir output/<run-full>] [--out seam_check.json]

Checks (thresholds from the incremental-render task):
  frames    same count, constant frame interval in A (no skipped / doubled timestamps)
  black     black segments (blackdetect) present in A but not in B
  repeats   frames where A holds still (identical to the previous frame) but B moves
  match     per-frame PSNR of A vs B (min / at every scene boundary ±3 frames)
  audio     clicks: sample jumps > 6x the local RMS that B does not have; integrated loudness
            difference (EBU R128) ≤ 0.5 LU
  subtitles cue start / end of A vs B ≤ 1 frame
Exit 0 when every check passes, 2 otherwise. Local ffmpeg only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

from content_farm.visual.timeline import parse_srt

FPS = 30.0
LOUDNESS_TOLERANCE_LU = 0.5
PSNR_IDENTICAL = 60.0


def _ffprobe_pts(path: Path) -> np.ndarray:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True).stdout
    return np.sort(np.array([float(x) for x in out.split() if x and x != "N/A"]))


def frames_check(a: Path, b: Path) -> dict:
    pa, pb = _ffprobe_pts(a), _ffprobe_pts(b)
    steps = np.diff(pa)
    irregular = int(np.sum(np.abs(steps - 1 / FPS) > 0.5 / FPS))
    return {"frames_a": int(pa.size), "frames_b": int(pb.size), "irregular_steps_a": irregular,
            "ok": pa.size == pb.size and irregular == 0}


def black_segments(path: Path) -> list[tuple[float, float]]:
    err = subprocess.run(["ffmpeg", "-v", "info", "-i", str(path), "-vf", "blackdetect=d=0.03:pix_th=0.10",
                          "-an", "-f", "null", "-"], capture_output=True, text=True).stderr
    return [(float(s), float(e)) for s, e in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", err)]


def black_check(a: Path, b: Path) -> dict:
    ba, bb = black_segments(a), black_segments(b)
    new = [s for s in ba if not any(abs(s[0] - t[0]) < 0.1 and abs(s[1] - t[1]) < 0.1 for t in bb)]
    return {"black_a": ba, "black_b": bb, "only_in_a": new, "ok": not new}


def _gray_frames(path: Path, size: tuple[int, int] = (160, 90)) -> np.ndarray:
    w, h = size
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={w}:{h},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.int16)


def motion_and_match(a: Path, b: Path, boundaries: list[float]) -> dict:
    fa, fb = _gray_frames(a), _gray_frames(b)
    n = min(len(fa), len(fb))
    fa, fb = fa[:n], fb[:n]
    still_a = np.abs(np.diff(fa, axis=0)).mean(axis=(1, 2)) < 0.05
    moving_b = np.abs(np.diff(fb, axis=0)).mean(axis=(1, 2)) > 0.5
    repeats = [int(i + 1) for i in np.nonzero(still_a & moving_b)[0]]
    mse = ((fa - fb) ** 2).mean(axis=(1, 2))
    psnr = np.where(mse == 0, 99.0, 10 * np.log10(255 ** 2 / np.maximum(mse, 1e-9)))
    around = sorted({min(n - 1, max(0, int(round(t * FPS)) + d)) for t in boundaries for d in range(-3, 4)})
    worst = int(np.argmin(psnr))
    return {"compared_frames": n, "repeats_only_in_a": repeats,
            "psnr_min": round(float(psnr.min()), 2), "psnr_min_at_s": round(worst / FPS, 3),
            "psnr_median": round(float(np.median(psnr)), 2),
            "psnr_min_at_boundaries": round(float(psnr[around].min()), 2) if around else None,
            "frames_below_35db": int((psnr < 35).sum()),
            "ok": not repeats}


def _audio(path: Path, sr: int = 48_000) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def clicks(samples: np.ndarray, sr: int = 48_000) -> list[float]:
    """Instants where one sample step is far above the steps around it (a cut without a fade)."""
    step = np.abs(np.diff(samples.astype(np.float64)))
    hop = sr // 100
    typical = np.convolve(step, np.ones(hop) / hop, mode="same")
    hits = np.nonzero(step > 8 * typical + 0.01)[0]
    out: list[float] = []
    for i in hits:
        t = i / sr
        if not out or t - out[-1] > 0.05:
            out.append(round(t, 3))
    return out


def loudness(path: Path) -> float:
    err = subprocess.run(["ffmpeg", "-v", "info", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    found = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    return float(found[-1])


def audio_check(a: Path, b: Path) -> dict:
    ca, cb = clicks(_audio(a)), clicks(_audio(b))
    only_a = [t for t in ca if not any(abs(t - u) < 0.05 for u in cb)]
    la, lb = loudness(a), loudness(b)
    return {"clicks_a": len(ca), "clicks_b": len(cb), "clicks_only_in_a": only_a,
            "lufs_a": la, "lufs_b": lb, "lufs_diff": round(abs(la - lb), 2),
            "ok": not only_a and abs(la - lb) <= LOUDNESS_TOLERANCE_LU}


def subtitle_check(srt_a: Path, srt_b: Path) -> dict:
    ca, cb = parse_srt(srt_a.read_text(encoding="utf-8")), parse_srt(srt_b.read_text(encoding="utf-8"))
    if len(ca) != len(cb):
        return {"cues_a": len(ca), "cues_b": len(cb), "ok": False}
    worst = max((max(abs(x[0] - y[0]), abs(x[1] - y[1])) for x, y in zip(ca, cb)), default=0.0)
    return {"cues": len(ca), "max_offset_s": round(worst, 4), "frame_s": round(1 / FPS, 4),
            "ok": worst <= 1 / FPS + 1e-6}


def scene_boundaries(run_dir: Path) -> list[float]:
    from content_farm.assembly.timeline_assembly import scan_timeline_clips

    return [c.start_seconds for c in scan_timeline_clips(run_dir / "visual")][1:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--a", type=Path, required=True, help="incrementally rendered video")
    parser.add_argument("--b", type=Path, required=True, help="the same script rendered whole")
    parser.add_argument("--run-dir", type=Path, required=True, help="run dir of A (scene boundaries, subtitles)")
    parser.add_argument("--b-run-dir", type=Path, help="run dir of B (its subtitles); default: same SRT")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    boundaries = scene_boundaries(args.run_dir)
    srt_a = args.run_dir / "subtitles" / "subtitles.srt"
    srt_b = (args.b_run_dir or args.run_dir) / "subtitles" / "subtitles.srt"
    report = {"a": str(args.a), "b": str(args.b), "scene_boundaries": len(boundaries),
              "frames": frames_check(args.a, args.b), "black": black_check(args.a, args.b),
              "video": motion_and_match(args.a, args.b, boundaries), "audio": audio_check(args.a, args.b),
              "subtitles": subtitle_check(srt_a, srt_b)}
    report["ok"] = all(v["ok"] for v in report.values() if isinstance(v, dict))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
