"""Overlay the animated 晶片貓 on assembly/draft.mp4 → assembly/final.mp4.

Usage:
    python scripts/mascot_overlay.py --run-dir output/<run>
    python scripts/mascot_overlay.py --run-dir output/<run> --seconds 20   # quick preview
    python scripts/mascot_overlay.py --run-dir output/<run> --stills 12.5,40,61.2
    python scripts/mascot_overlay.py --run-dir output/<run> --pngtuber pngtuber/frog-scribe  # still-image host

Reads deck.json (mascot.pose / say per slide) or script.json, slide timing from
visual/ timeline names (fallback: audio/scene_NNN.mp3 lengths), and voice audio
for lip-sync. Writes assembly/mascot.mov (ProRes 4444, alpha) and final.mp4.
Does not touch draft.mp4. Local only: Playwright + ffmpeg, no network, no paid API.
Refuses to run when a subtitle line in subtitles/subtitles.srt is wide enough to
reach the cat (see explainer.mascot.clearance).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from content_farm.assembly.drawtext import find_cjk_font
from content_farm.explainer.mascot.clearance import wide_lines
from content_farm.explainer.mascot.cues import CueError
from content_farm.explainer.mascot.overlay import SUBTITLES
from content_farm.explainer.mascot.render import render_still
from content_farm.explainer.mascot.run import frames_for_run, probe_video, run_overlay


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=min(3, os.cpu_count() or 1))
    parser.add_argument("--no-cache", action="store_true",
                        help="redraw every scene (default: reuse scenes whose identity is unchanged)")
    parser.add_argument("--seed", type=int, default=7, help="idle-motion seed (same seed = same frames)")
    parser.add_argument("--seconds", type=float, help="only the first N seconds (preview)")
    parser.add_argument("--out", type=Path, help="default <run-dir>/assembly/final.mp4")
    parser.add_argument("--stills", help="comma-separated times (s): write mascot PNGs instead of video")
    parser.add_argument("--dump-params", action="store_true", help="also write assembly/mascot_params.json")
    parser.add_argument("--allow-subtitle-overlap", action="store_true",
                        help="overlay even if a subtitle line reaches the cat's column")
    parser.add_argument("--motion-profile", metavar="NAME", default=None,
                        help="PNGtuber motion profile (legacy, calm, nod, beat); default legacy")
    parser.add_argument("--pngtuber", metavar="REF",
                        help="draw a PNGtuber pack (e.g. pngtuber/frog-scribe) instead of the vector rig")
    return parser.parse_args(argv)


def _pngtuber(args: argparse.Namespace) -> int:
    from content_farm.explainer.pngtuber.run import run_host_overlay

    result = run_host_overlay(args.run_dir, args.pngtuber, seed=args.seed, seconds=args.seconds, out=args.out,
                              motion_profile=args.motion_profile)
    t = result.timings
    print(f"Host:   {args.pngtuber} ({result.placement}), {result.render.frames} frames, "
          f"{result.render.faces} composited faces")
    print(f"Timing: params {t['params']:.1f}s, render {t['render']:.1f}s, "
          f"overlay {t['overlay']:.1f}s, total {t['total']:.1f}s")
    print(f"Alpha:  {result.alpha_video}")
    print(f"Final:  {result.final}")
    return 0


def _subtitle_clearance(run_dir: Path) -> list[str]:
    """Problems with subtitle lines wide enough to run under the cat (empty = clear)."""
    srt = run_dir / "subtitles" / "subtitles.srt"
    font = find_cjk_font()
    if not srt.is_file() or not font:
        return []
    return [f"subtitle line {w.width}px wide reaches x={w.right_edge} (cat column starts at "
            f"x={SUBTITLES.x1}): {w.text}" for w in wide_lines(srt, font)]


def _stills(run_dir: Path, times: str, seed: int) -> int:
    info = probe_video(run_dir / "assembly" / "draft.mp4")
    frames = frames_for_run(run_dir, info, seed)
    for raw in times.split(","):
        index = min(len(frames) - 1, int(round(float(raw) * info.fps)))
        path = render_still(frames[index], run_dir / "assembly" / f"mascot_{index:05d}.png")
        print(f"{float(raw):.2f}s -> frame {index} -> {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args(argv)
    try:
        if args.stills:
            return _stills(args.run_dir, args.stills, args.seed)
        overlaps = _subtitle_clearance(args.run_dir)
        for problem in overlaps:
            print(f"{'WARNING' if args.allow_subtitle_overlap else 'Error'}: {problem}", file=sys.stderr)
        if overlaps and not args.allow_subtitle_overlap:
            print("Re-run voice with CF_SUBTITLE_MAX_CHARS_PER_LINE_LANDSCAPE=20 (or shorten those "
                  "sentences), or pass --allow-subtitle-overlap.", file=sys.stderr)
            return 1
        if args.pngtuber:
            return _pngtuber(args)
        result = run_overlay(args.run_dir, workers=args.workers, seed=args.seed,
                             seconds=args.seconds, out=args.out, use_cache=not args.no_cache)
        if args.dump_params:
            info = probe_video(args.run_dir / "assembly" / "draft.mp4")
            frames = frames_for_run(args.run_dir, info, args.seed)
            dump = [{"params": dict(f.params), "say": f.say} for f in frames]
            (args.run_dir / "assembly" / "mascot_params.json").write_text(json.dumps(dump), encoding="utf-8")
    except (OSError, ValueError, CueError, ValidationError, RuntimeError) as exc:  # PackError is a ValueError
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    t = result.timings
    seconds = result.rendered_frames / result.info.fps
    print(f"Frames: {result.rendered_frames} ({seconds:.1f}s @ {result.info.fps:g} fps); "
          f"scenes {result.scenes}, reused {result.reused_scenes}; drew {result.render.frames} frames "
          f"with {result.render.workers} workers")
    print(f"Timing: params {t['params']:.1f}s, render {t['render']:.1f}s, join {t.get('join', 0.0):.1f}s, "
          f"overlay {t['overlay']:.1f}s, total {t['total']:.1f}s")
    print(f"Alpha:  {result.alpha_video}")
    print(f"Final:  {result.final}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
