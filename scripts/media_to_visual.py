"""Build per-slide media clips (animated / stock / ai_image / title_card) onto visual/.

The v2 replacement for ``slides_to_visual.py`` (which still works for PNG-only
decks). Run after voice so slots use measured durations.

Usage:
    python scripts/media_to_visual.py --run-dir output/<run>
    python scripts/media_to_visual.py --run-dir <dir> --transition none      # hard cuts
    python scripts/media_to_visual.py --run-dir <dir> --transition push --transition-seconds 0.5
    python scripts/media_to_visual.py --run-dir <dir> --replace              # redo
    python scripts/media_to_visual.py --run-dir <dir> --no-stock             # offline
    python scripts/media_to_visual.py --run-dir <dir> --brand chipcat        # channel brand

ai_image slides move (2.5D parallax by default, baked Wan clips for ``motion: wan``) when
CF_MLX_VIDEO_HOME (or its per-path overrides, see explainer/motion_cache.py) is set in the
environment or ``--env-file``; otherwise they fall back to Ken Burns.

Needs ``<run-dir>/deck.json``, ``script.json``, ``slides/slide_NNN.png`` (render_slides)
and voice output. Stock keys come from CF_PEXELS_API_KEY / CF_PIXABAY_API_KEY
(environment, else ``--env-file``, default ``.env``). Downloads are cached in
``--stock-cache`` per query. Writes:
  visual/MM:SS.mmm~MM:SS.mmm.{mp4,png}   timeline clips for assembly_timeline
  credits.json                            stock author / URL / licence (+ description text)
  ai_image_prompts.{md,json}              prompts for generate_visuals.py (ai_image slides)
  media/media_report.json                 per-slide kind used, fallbacks, timings
  media/contact_sheet.png                 review sheet; placeholders/fallbacks flagged red
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from pydantic import ValidationError

from content_farm.explainer.brands import brand_codes
from content_farm.explainer.deck import load_deck
from content_farm.explainer.ffmpeg_ops import FFmpegError
from content_farm.explainer.media_run import TRANSITION_CHOICES, MediaOptions, media_to_visual
from content_farm.explainer.motion_cache import MotionPaths, motion_env
from content_farm.explainer.footage.client import FootageClient
from content_farm.explainer.stock import StockClient
from content_farm.explainer.timeline import (
    DURATION_SOURCES,
    plan_slide_timeline,
    resolve_durations,
)
from content_farm.script_gen.schemas import Script

KEY_NAMES = ("CF_PEXELS_API_KEY", "CF_PIXABAY_API_KEY")


def _stock_keys(env_file: Path) -> dict[str, str]:
    keys = {name: os.environ.get(name, "") for name in KEY_NAMES}
    if all(keys.values()) or not env_file.is_file():
        return keys
    from dotenv import dotenv_values

    file_values = dotenv_values(env_file)
    return {name: keys[name] or (file_values.get(name) or "") for name in KEY_NAMES}


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--source", choices=DURATION_SOURCES, default="auto")
    parser.add_argument("--transition", choices=TRANSITION_CHOICES, default="crossfade")
    parser.add_argument("--transition-seconds", type=float, default=0.25)   # v3: 0.4 s let two pages' text overlap
    parser.add_argument("--replace", action="store_true", help="remove old timeline files first")
    parser.add_argument("--no-stock", action="store_true", help="never call Pexels/Pixabay")
    parser.add_argument("--clip-rank", action="store_true",
                        help="re-rank stock_video candidates against the narration with local CLIP (needs CF_CLIP_MODEL_DIR; off by default)")
    parser.add_argument("--no-cache", action="store_true",
                        help="rebuild every slot (default: reuse slots whose scene identity is unchanged)")
    parser.add_argument("--stock-cache", type=Path, default=Path(".cache/explainer_stock"))
    parser.add_argument("--footage-cache", type=Path, default=Path(".cache/footage"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--brand", choices=brand_codes(),
                        help="channel brand for overlays/cards (default: deck category theme)")
    parser.add_argument("--require-measured", action="store_true",
                        help="exit 3 instead of warning when only estimated durations exist")
    return parser.parse_args(argv)


def _clip_ranker():
    """Local CLIP re-ranking of footage candidates when CF_CLIP_MODEL_DIR points at weights; else keyword order."""
    from content_farm.explainer.footage import clip_rank

    try:
        return clip_rank.with_embedder(clip_rank.from_env())
    except clip_rank.ClipUnavailable as exc:
        print(f"CLIP ranking off: {exc}", file=sys.stderr)
        return None


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_dir: Path = args.run_dir
    started = time.monotonic()
    try:
        motion_paths = MotionPaths.from_env(motion_env(args.env_file))
        options = MediaOptions(transition=args.transition,
                               transition_seconds=args.transition_seconds, replace=args.replace,
                               brand=args.brand, motion_paths=motion_paths, cache=not args.no_cache)
        deck = load_deck(run_dir / "deck.json")
        script = Script.model_validate_json((run_dir / "script.json").read_text(encoding="utf-8"))
        used, durations = resolve_durations(run_dir, script, args.source)
        if used == "script" and args.require_measured:
            print("Error: only estimated durations found; run voice first", file=sys.stderr)
            return 3
        clips = plan_slide_timeline(durations)
        stock = footage = None
        if not args.no_stock:
            keys = _stock_keys(args.env_file)
            stock = StockClient(pexels_key=keys["CF_PEXELS_API_KEY"],
                                pixabay_key=keys["CF_PIXABAY_API_KEY"], cache_dir=args.stock_cache)
            footage = FootageClient(cache_dir=args.footage_cache, stock=stock, ranker=_clip_ranker() if args.clip_rank else None)
        run = media_to_visual(deck, run_dir, clips, stock=stock, options=options, footage=footage)
    except (OSError, ValueError, ValidationError, FFmpegError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if used == "script":
        print("WARNING: estimated durations — do not assemble from this", file=sys.stderr)
    reused = run.reused or (False,) * len(run.results)
    for r, hit in zip(run.results, reused):
        flag = "  <-- " if r.requested != r.used else ("  [review]" if r.review else "")
        flag += "  (cached)" if hit else ""
        print(f"{r.index:02d} {r.slide_id:<10} {r.requested:<10} -> {r.used:<14} "
              f"{r.build_seconds:5.1f}s  {r.note}{flag}")
    print(f"Reused {sum(reused)}/{len(reused)} slot(s) from the scene cache")
    print(f"Placed {len(run.placed)} clips from {used} durations in "
          f"{time.monotonic() - started:.1f}s; ends at {run.placed[-1].stem}")
    print(f"Credits: {run.credits_path}\nReport: {run.report_path}\nContact sheet: {run.contact_sheet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
