"""Validate ``deck.json`` and derive ``script.json`` from it (explainer line).

Usage:
    python scripts/deck_to_script.py --run-dir output/20261014_tsmc
    python scripts/deck_to_script.py --deck path/to/deck.json --out path/to/script.json
    python scripts/deck_to_script.py --run-dir <dir> --strict   # lint warnings fail too

Exit codes: 0 ok, 1 invalid deck / I/O error, 2 lint failed under --strict.
No network, no paid API.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from content_farm.explainer.deck import load_deck
from content_farm.explainer.lint import lint_deck
from content_farm.explainer.to_script import deck_to_script


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, help="run directory holding deck.json")
    parser.add_argument("--deck", type=Path, help="deck.json path (default <run-dir>/deck.json)")
    parser.add_argument("--out", type=Path, help="script.json path (default <run-dir>/script.json)")
    parser.add_argument("--strict", action="store_true", help="treat lint warnings as errors")
    args = parser.parse_args(argv)
    if args.deck is None and args.run_dir is None:
        parser.error("give --run-dir or --deck")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    deck_path = args.deck or args.run_dir / "deck.json"
    out_path = args.out or (args.run_dir or deck_path.parent) / "script.json"

    try:
        deck = load_deck(deck_path)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"Invalid deck {deck_path}:\n{exc}", file=sys.stderr)
        return 1

    issues = lint_deck(deck)
    for issue in issues:
        print(f"[lint:{issue.code}] {issue.message}", file=sys.stderr)
    if issues and args.strict:
        print(f"{len(issues)} lint issue(s); refusing under --strict", file=sys.stderr)
        return 2

    script = deck_to_script(deck)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(script.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"script.json: {len(script.scenes)} scenes, {len(script.chapters)} chapters, "
        f"~{script.total_duration_seconds / 60:.1f} min (estimate) -> {out_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
