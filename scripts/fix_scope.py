"""What an edit to deck.json puts back in the queue (修改範圍連動).

Usage:
    python scripts/fix_scope.py --run-dir output/<run>                       # vs review/deck.approved.json
    python scripts/fix_scope.py --run-dir <dir> --old <dir>/deck.v2.json
    python scripts/fix_scope.py --run-dir <dir> --term "晶片卻不一定翻倍" --radius 1

Compares the approved deck (snapshot written when gate_deck is approved) with deck.json and
prints: rewritten sentences (stable ids), every place a changed term still appears in its old
wording (narration, headings, slide body, bubble, chapters, title/description, thumbnail,
upload text), the voice windows to re-voice, and which scenes are redrawn vs. only shifted.
Writes ``<run-dir>/fix_scope.json``. Exit 2 when an old wording still appears somewhere
(a correction that would contradict itself on screen), 0 otherwise. No network.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from content_farm.explainer.fix_scope import analyse, load_texts
from content_farm.explainer.sentence_ids import LEDGER_FILE, load_ledger
from content_farm.production.runner import APPROVED_DECK


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--old", type=Path, help=f"deck before the edit (default <run-dir>/{APPROVED_DECK})")
    parser.add_argument("--term", action="append", default=[], help="wording to chase everywhere (repeatable)")
    parser.add_argument("--radius", type=int, default=2, help="neighbour sentences re-voiced on each side")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    old_path = args.old or args.run_dir / APPROVED_DECK
    try:
        old = json.loads(old_path.read_text(encoding="utf-8"))
        new = json.loads((args.run_dir / "deck.json").read_text(encoding="utf-8"))
        ledger = load_ledger(args.run_dir / LEDGER_FILE) or None
        scope = analyse(old, new, radius=args.radius, extra_terms=args.term,
                        outside=load_texts(args.run_dir), ledger=ledger)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    (args.run_dir / "fix_scope.json").write_text(json.dumps(scope.to_json(), ensure_ascii=False, indent=2),
                                                 encoding="utf-8")
    print(f"rewritten sentences: {', '.join(scope.changed) or '-'}")
    print(f"new / removed: {', '.join(scope.added) or '-'} / {', '.join(scope.removed) or '-'}")
    print(f"terms: {' | '.join(scope.terms) or '-'}")
    for occ in scope.occurrences:
        print(f"  still says 「{occ.term}」 → {occ.where}: {occ.text}")
    for slide, ids in scope.voice_windows.items():
        print(f"re-voice {slide}: {', '.join(ids)}")
    print(f"redraw: {', '.join(scope.redraw_scenes) or '-'}")
    print(f"shift only (cached): {', '.join(scope.shifted_scenes) or '-'}")
    for note in scope.notes:
        print(f"note: {note}")
    return 2 if scope.occurrences else 0


if __name__ == "__main__":
    sys.exit(main())
