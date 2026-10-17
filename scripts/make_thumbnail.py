#!/usr/bin/env python3
"""Render a run's channel thumbnail from ``thumbnail.json`` (roadmap R2).

    python scripts/make_thumbnail.py --run-dir output/cowos-chipcat --channel chipcat
    python scripts/make_thumbnail.py --run-dir output/cowos-chipcat --channel chipcat --variants  # A/B a/b/c

Writes ``thumbnails/thumbnail.png`` (1280x720, what manual-kit and the API upload use)
and ``thumbnails/thumbnail_phone.png`` (320x180, to judge legibility in a phone feed),
then prints the QC verdict on the thumbnail (text length, promise, numbers).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from content_farm.production.channels import load_channel
from content_farm.production.thumbnail import (
    VARIANTS_FILE, render_thumbnail, render_variants, thumbnail_findings, variant_findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--channel", required=True)
    parser.add_argument("--variants", action="store_true",
                        help=f"render {VARIANTS_FILE} (up to 3 A/B variants, or Shorts covers) instead")
    args = parser.parse_args(argv)
    channel = load_channel(args.channel)
    try:
        if args.variants:
            for key, path in render_variants(args.run_dir, channel).items():
                print(f"variant {key}: {path} ({path.stat().st_size // 1024} KB)")
            findings = variant_findings(args.run_dir, channel)
        else:
            print(render_thumbnail(args.run_dir, channel))
            findings = thumbnail_findings(args.run_dir, channel)
    except (FileNotFoundError, ValueError) as exc:
        print(f"thumbnail: {exc}", file=sys.stderr)
        return 1
    for finding in findings:
        print(f"[{finding.level}] {finding.check}: {finding.message}")
    return 0  # rendered; QC records any error and the final gate blocks on it


if __name__ == "__main__":
    raise SystemExit(main())
