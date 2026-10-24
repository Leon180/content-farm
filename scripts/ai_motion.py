"""Wan key-shot clips: list them, or bake them ahead of rendering (the nightly batch).

Usage:
    python scripts/ai_motion.py status --run-dir output/<run> [--run-dir output/<run2> ...]
    python scripts/ai_motion.py bake   --run-dir output/<run> [--run-dir ...] [--max-wait 14400]

``bake`` makes every missing ``motion: wan`` clip, one at a time. Before each clip it takes the
machine-wide render lock (no pipeline render can start meanwhile), then waits while memory
pressure is warn or worse or another render / mflux / mlx_video process runs (Wan peaks at
~26 GB). Run it when the machine is otherwise idle, e.g. nightly from cron or launchd:

    0 2 * * *  PYTHONPATH=<repo>/src <repo>/.venv/bin/python <repo>/scripts/ai_motion.py bake \
               --run-dir <repo>/output/<run> >> <repo>/output/ai_motion_bake.log 2>&1

The media step then only reads the cache (``assets/ai_motion/<slide>.wan.{mp4,json}``); a
slide whose clip is not baked falls back to parallax and QC warns.
Paths: CF_MLX_VIDEO_HOME (or CF_MLX_VIDEO_PYTHON / CF_WAN_MODEL_DIR), environment or --env-file.
"""

from __future__ import annotations

import argparse
import functools
import os
import sys
from pathlib import Path

from content_farm.explainer import wan
from content_farm.explainer.deck import load_deck
from content_farm.explainer.illustrate import wait_for_memory
from content_farm.explainer.motion_bake import WanShot, bake, wan_shots
from content_farm.explainer.motion_cache import MotionPaths, motion_env
from content_farm.production.runner import render_lock

REPO_ROOT = Path(__file__).resolve().parents[1]


def _busy() -> str | None:
    hits = wan.busy_processes({os.getpid(), os.getppid()})
    return hits[0] if hits else None


def _gate(max_wait: float) -> float:
    return wait_for_memory(busy=_busy, max_wait=max_wait)


def _shots(run_dirs: list[Path]) -> list[WanShot]:
    shots: list[WanShot] = []
    for run_dir in run_dirs:
        shots += wan_shots(load_deck(run_dir / "deck.json"), run_dir)
    return shots


def _status(shots: list[WanShot]) -> int:
    todo = [s for s in shots if s.request is not None and not s.cached]
    for shot in shots:
        state = "no still yet" if shot.request is None else ("cached" if shot.cached else "to bake")
        print(f"{shot.run_dir.name}/{shot.slide_id}: {state}")
    minutes = sum(s.request.segments for s in todo) * wan.ESTIMATED_MINUTES_PER_CLIP
    print(f"{len(todo)} clip(s) to bake ≈ {minutes} min "
          f"(one at a time, ~26 GB peak each)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("status", "bake"))
    parser.add_argument("--run-dir", type=Path, action="append", required=True)
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env")
    parser.add_argument("--max-wait", type=float, default=4 * 3600,
                        help="seconds to wait for a free machine before giving up on a clip")
    args = parser.parse_args()
    try:
        shots = _shots(args.run_dir)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.action == "status":
        return _status(shots)
    paths = MotionPaths.from_env(motion_env(args.env_file))
    if paths is None:
        print("Error: set CF_MLX_VIDEO_HOME (see scripts/ai_motion.py docstring)", file=sys.stderr)
        return 1

    def locked_gate() -> float:
        return _gate(args.max_wait)

    def generate(paths: MotionPaths, run_dir: Path, request: wan.WanRequest, gate) -> dict:
        with render_lock(None, functools.partial(print, " ", flush=True)):
            return wan.generate(paths, run_dir, request, gate)

    try:
        records = bake(shots, paths, locked_gate, log=functools.partial(print, flush=True), generate=generate)
    except (FileNotFoundError, RuntimeError, TimeoutError, ValueError, OSError) as exc:
        print(f"bake failed: {exc}", file=sys.stderr)
        return 1
    print(f"{len(records)} Wan clip(s) baked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
