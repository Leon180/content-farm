"""Render deck.json to slides/slide_NNN.{html,png} + slides/contact_sheet.png.

Usage:
    python scripts/render_slides.py --run-dir output/20261014_tsmc
    python scripts/render_slides.py --deck docs/examples/tsmc/deck.json --out-dir /tmp/slides
    python scripts/render_slides.py --run-dir <dir> --show-safe-zone   # debug overlay
    python scripts/render_slides.py --run-dir <dir> --brand chipcat    # channel brand

Mascot PNGs are looked up as <mascot-dir>/<pose>.png (default <run-dir>/assets/mascot);
a missing pose just leaves the corner empty. Needs the ``browser`` extra
(playwright + chromium). Exit 1 on an invalid deck or any slide overflow
(each failing slide is listed). Independent of voice; no network, no paid API.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from pydantic import ValidationError

from content_farm.explainer.brands import brand_codes
from content_farm.explainer.deck import load_deck
from content_farm.explainer.pages import build_pages
from content_farm.explainer.render import SlideOverflowError, make_contact_sheet, render_pages


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--deck", type=Path, help="default <run-dir>/deck.json")
    parser.add_argument("--out-dir", type=Path, help="default <run-dir>/slides")
    parser.add_argument("--mascot-dir", type=Path, help="default <run-dir>/assets/mascot")
    parser.add_argument("--show-safe-zone", action="store_true", help="hatch the subtitle zone")
    parser.add_argument("--brand", choices=brand_codes(),
                        help="channel brand stylesheet (default: the deck category theme)")
    args = parser.parse_args(argv)
    if args.run_dir is None and (args.deck is None or args.out_dir is None):
        parser.error("give --run-dir, or both --deck and --out-dir")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    deck_path = args.deck or args.run_dir / "deck.json"
    out_dir = args.out_dir or args.run_dir / "slides"
    mascot_dir = args.mascot_dir or (args.run_dir / "assets" / "mascot" if args.run_dir else None)

    try:
        deck = load_deck(deck_path)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"Invalid deck {deck_path}:\n{exc}", file=sys.stderr)
        return 1

    started = time.monotonic()
    pages = build_pages(deck, mascot_dir=mascot_dir, show_safe_zone=args.show_safe_zone,
                        brand=args.brand)
    try:
        rendered = render_pages(pages, out_dir)
    except SlideOverflowError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    sheet = make_contact_sheet(rendered, out_dir / "contact_sheet.png")
    print(f"Rendered {len(rendered)} slides in {time.monotonic() - started:.1f}s -> {out_dir}")
    print(f"Contact sheet: {sheet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
