"""Round 3 trials: PNGtuber hosts on real runs, without touching the source runs.

    PYTHONPATH=src python docs/design/channel-hosts/tools/r3_trial.py <source_output_dir> <trial_dir>

  yokai  <src>/yokai-kyubi-launch  + pngtuber/frog-scribe      first 20 s, 1920x1080
  cel    <src>/cel-ep1             + pngtuber/paint-bottle     first 20 s, 1920x1080
  short  <src>/chipcat-7722-launch through the real scripted-Short renderer with the offwork channel
         (pngtuber/cooler-goldfish): beats with an empty cat slot, then the host bottom-left with
         each beat's pose. Whole Short, 1080x1920.

Landscape trials link the source run's inputs (read-only) and write only into <trial>/<name>/assembly.
Every alpha frame of host.mov is checked against the placement's forbidden rects (trials.json).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

from content_farm.explainer.pngtuber.render import PLACEMENTS
from content_farm.explainer.pngtuber.run import run_host_overlay

OUT = Path(__file__).resolve().parents[1] / "round3"
LANDSCAPE_TRIALS = {"yokai": ("yokai-kyubi-launch", "pngtuber/frog-scribe"),
                    "cel": ("cel-ep1", "pngtuber/paint-bottle")}
SHORT = ("chipcat-7722-launch", "pngtuber/cooler-goldfish")
LINKED = ("deck.json", "script.json", "audio", "visual", "subtitles")
STILL_AT = (2.0, 7.5, 13.0, 18.5)


def link_run(src: Path, dst: Path) -> Path:
    (dst / "assembly").mkdir(parents=True, exist_ok=True)
    for name in LINKED:
        if (src / name).exists() and not (dst / name).exists():
            (dst / name).symlink_to(src / name)
    draft = dst / "assembly" / "draft.mp4"
    if not draft.exists():
        draft.symlink_to(src / "assembly" / "draft.mp4")
    return dst


def short_trial(src: Path, dst: Path) -> dict:
    """The real scripted-Short path for a PNGtuber channel: render_scripted(…, offwork) renders the
    beats with an empty cat slot, then overlays the pack bottom-left with each beat's pose.
    The Short's small inputs are copied (render_scripted rewrites subtitles.srt); audio is linked."""
    from content_farm.production.channels import load_channel
    from content_farm.production.shorts_scripted_render import render_scripted

    dst.mkdir(parents=True, exist_ok=True)
    for name in ("script.json", "short_source.json"):
        shutil.copy2(src / name, dst / name)
    shutil.copytree(src / "subtitles", dst / "subtitles", dirs_exist_ok=True)
    if not (dst / "audio").exists():
        (dst / "audio").symlink_to(src / "audio")
    channel = load_channel("offwork")
    result = render_scripted(dst, channel)
    alpha = dst / "assembly" / "host.mov"
    times = tuple(t for t in STILL_AT if t < result.seconds - 0.2)
    return {"run_dir": str(dst), "pack": channel.mascot.ref, "final": str(result.video), "placement": "vertical",
            "seconds": result.seconds, "beats": result.beats,
            "forbidden": forbidden_pixels(alpha, (1080, 1920)), "stills": stills(result.video, "short", times)}


def forbidden_pixels(alpha_video: Path, placement_frame: tuple[int, int]) -> dict[str, int]:
    """Max over all frames of host pixels (alpha > 8) inside each forbidden rect."""
    p = PLACEMENTS[placement_frame]
    w, h = p.canvas
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(alpha_video), "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                            stdout=subprocess.PIPE)
    worst = dict.fromkeys(p.forbidden, 0)
    frames = 0
    while chunk := proc.stdout.read(w * h * 4):
        if len(chunk) < w * h * 4:
            break
        alpha = np.frombuffer(chunk, dtype=np.uint8).reshape(h, w, 4)[..., 3]
        frames += 1
        for name, r in p.forbidden.items():
            x0, y0 = max(0, r.x0 - p.origin[0]), max(0, r.y0 - p.origin[1])
            x1, y1 = min(w, r.x1 - p.origin[0]), min(h, r.y1 - p.origin[1])
            if x0 < x1 and y0 < y1:
                worst[name] = max(worst[name], int((alpha[y0:y1, x0:x1] > 8).sum()))
    if proc.wait() != 0 or frames == 0:
        raise RuntimeError(f"could not decode {alpha_video}")
    return {**worst, "frames_checked": frames}


def stills(video: Path, name: str, times: tuple[float, ...]) -> list[str]:
    out = []
    for t in times:
        path = OUT / f"trial_{name}_{t:04.1f}s.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                        "-q:v", "3", str(path)], check=True)
        out.append(path.name)
    return out


def trial(name: str, run_dir: Path, ref: str, seconds: float | None) -> dict:
    result = run_host_overlay(run_dir, ref, seconds=seconds)
    duration = seconds or result.render.frames / result.info.fps
    times = tuple(t for t in STILL_AT if t < duration - 0.2)
    return {"run_dir": str(run_dir), "pack": ref, "final": str(result.final), "placement": result.placement,
            "frames": result.render.frames, "faces": result.render.faces,
            "timings": {k: round(v, 1) for k, v in result.timings.items()},
            "forbidden": forbidden_pixels(result.alpha_video, (result.info.width, result.info.height)),
            "stills": stills(result.final, name, times)}


def main(argv: list[str]) -> int:
    src, work = Path(argv[0]), Path(argv[1])
    OUT.mkdir(parents=True, exist_ok=True)
    report_path = OUT / "trials.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    only = set(argv[2].split(",")) if len(argv) > 2 else {"yokai", "cel", "short"}
    for name, (run, ref) in LANDSCAPE_TRIALS.items():
        if name in only:
            report[name] = trial(name, link_run(src / run, work / name), ref, 20.0)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    if "short" in only:
        report["short"] = short_trial(src / SHORT[0], work / "short_pipeline")
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    bad = [n for n, r in report.items() if any(v for k, v in r["forbidden"].items() if k != "frames_checked")]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
