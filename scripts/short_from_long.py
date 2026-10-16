"""Render the vertical Short described by ``<run-dir>/short_source.json``.

Normally run by ``produce.py short-from-long`` (step ``cut``); usable alone:
    python scripts/short_from_long.py --run-dir output/offwork-7722
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from content_farm.explainer.ffmpeg_ops import FFmpegError
from content_farm.production.channels import load_channel
from content_farm.production.shorts_cut import load_spec
from content_farm.production.shorts_render import render_short
from content_farm.production.shorts_scripted_render import render_scripted
from content_farm.production.state import read_channel_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        channel = load_channel(read_channel_code(args.run_dir))
        if load_spec(args.run_dir).scripted:
            done = render_scripted(args.run_dir, channel)
            print(f"{done.video}: {done.seconds:.1f}s, {done.beats} beats, longest still stage {done.longest_hold:.1f}s")
            return 0
        result = render_short(args.run_dir, channel)
    except (OSError, ValueError, ValidationError, FFmpegError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    t = result.timing
    print(f"{result.video}: {t.total:.1f}s (narration {t.narration:.1f}s = intro {t.intro:.1f}s "
          f"+ body {t.body:.1f}s, outro {t.outro:.1f}s), {result.cues} subtitle cues")
    return 0


if __name__ == "__main__":
    sys.exit(main())
