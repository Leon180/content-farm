"""Apply a sentence patch to deck.json, then re-run ``deck_to_script.py --strict``.

Usage:
    python scripts/apply_deck_patch.py --run-dir <run-dir> --patch <patch.json>

patch.json: {"s03.2": "new sentence text", "s05.1": "...", "deletes": ["s07.4"]}
Only the named sentences change; unknown ids, empty text, or a sentence that is both replaced and deleted
refuse the whole patch (deck.json untouched). No network, no paid API.
Exit codes: 0 ok, 1 patch refused / I/O error, otherwise deck_to_script's exit code (2 = lint failed).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from content_farm.review.deck_patch import PatchError, apply_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--no-check", action="store_true", help="skip the deck_to_script --strict run")
    args = parser.parse_args(argv)
    deck_path = args.run_dir / "deck.json"
    try:
        result = apply_file(deck_path.read_text(encoding="utf-8"), args.patch.read_text(encoding="utf-8"))
    except (OSError, PatchError) as exc:
        print(f"patch refused: {exc}", file=sys.stderr)
        return 1
    deck_path.write_text(json.dumps(result.deck, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"patched {len(result.changed)} sentence(s), deleted {len(result.deleted)}")
    if args.no_check:
        return 0
    import deck_to_script   # sibling script (scripts/ is sys.path[0] when this file runs)

    return deck_to_script.main(["--run-dir", str(args.run_dir), "--strict"])


if __name__ == "__main__":
    sys.exit(main())
