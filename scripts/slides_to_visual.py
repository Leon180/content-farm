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
    TimelineError,
    durations_from_audio,
    durations_from_script,
    durations_from_voice_artifact,
    place_slides,
    plan_slide_timeline,
)
from content_farm.script_gen.schemas import Script

SOURCES = ("auto", "audio", "voice-artifact", "script")


def _durations(run_dir: Path, script: Script, source: str) -> tuple[str, list[float]]:
    count = len(script.scenes)
    audio_dir = run_dir / "audio"
    artifact = run_dir / "voice_artifact.json"
    if source == "audio" or (source == "auto" and (audio_dir / "scene_001.mp3").is_file()):
        return "audio", durations_from_audio(audio_dir, count)
    if source == "voice-artifact" or (source == "auto" and artifact.is_file()):
        return "voice-artifact", durations_from_voice_artifact(artifact, count)
    if source == "script":
        return "script", durations_from_script(script)
    raise TimelineError("no voice output found; run voice first (or --source script to preview)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--source", choices=SOURCES, default="auto")
    parser.add_argument("--replace", action="store_true", help="remove old timeline files first")
    args = parser.parse_args(argv)

    run_dir: Path = args.run_dir
    try:
        script = Script.model_validate_json((run_dir / "script.json").read_text(encoding="utf-8"))
        used, durations = _durations(run_dir, script, args.source)
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
