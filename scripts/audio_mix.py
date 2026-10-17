"""BGM bed + stingers + SFX + -14 LUFS master → assembly/release.mp4 (the file that gets uploaded).

Usage:
    python scripts/audio_mix.py --run-dir output/cowos --channel chipcat
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from content_farm.audio_mix.run import run_mix
from content_farm.production.channels import load_channel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--channel", required=True)
    args = parser.parse_args(argv)
    try:
        data = run_mix(args.run_dir.resolve(), load_channel(args.channel))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    stats = data.get("master", {})
    print(f"release.mp4: {len(data['bgm'])} bed(s), {len(data['cues'])} cue(s), "
          f"master I={stats.get('output_i')} LUFS TP={stats.get('output_tp')} dBTP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
