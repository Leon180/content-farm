"""Name rendered slides onto the assembly timeline (explainer line, after voice).

Usage:
    python scripts/slides_to_visual.py --run-dir output/20261014_tsmc
    python scripts/slides_to_visual.py --run-dir <dir> --source script   # preview only
    python scripts/slides_to_visual.py --run-dir <dir> --replace         # redo after re-voice

Duration sources (``--source auto`` tries them in this order):
  audio           ffprobe audio/scene_NNN.mp3 (exact; what full.mp3 is made of)
  voice-artifact  voice_artifact.json (rounded to 10 ms)
  script          script.json estimates — never automatic, preview only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from content_farm.explainer.timeline import (
    DURATION_SOURCES,
    place_slides,
    plan_slide_timeline,
    resolve_durations,
)
from content_farm.script_gen.schemas import Script

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--source", choices=DURATION_SOURCES, default="auto")
    parser.add_argument("--replace", action="store_true", help="remove old timeline files first")
    args = parser.parse_args(argv)

    run_dir: Path = args.run_dir
    try:
        script = Script.model_validate_json((run_dir / "script.json").read_text(encoding="utf-8"))
        used, durations = resolve_durations(run_dir, script, args.source)
        clips = plan_slide_timeline(durations)
        placed = place_slides(clips, run_dir / "slides", run_dir / "visual", replace=args.replace)
    except (OSError, ValueError) as exc:  # TimelineError and pydantic errors are ValueErrors
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if used == "script":
        print("WARNING: estimated durations — do not assemble from this", file=sys.stderr)
    print(f"Placed {len(placed)} slides from {used} durations; ends at {placed[-1].stem}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
