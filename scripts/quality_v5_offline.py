#!/usr/bin/env python3
"""Offline numbers for quality v5: slideshow risk of a run's deck(s), the new deck lint rules, static-shot scan of its final
cut. Scores only; nothing is re-rendered or regenerated.

    PYTHONPATH=src python scripts/quality_v5_offline.py --out artifacts/quality-v5/offline.json RUN_DIR [RUN_DIR ...]

For a run that also has ``deck.v3.json`` (the deck before the visual-v4 redo) both decks are scored: that pair is the
closest thing to a before / after we have without a new render.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from content_farm.explainer.deck import Deck
from content_farm.explainer.lint import lint_deck
from content_farm.explainer.slideshow_risk import score_deck
from content_farm.production import static_scan

NEW_RULES = {"shot-size-repeat", "shot-size-variety", "text-hold", "must-keep-missing", "must-avoid-present"}


def deck_numbers(path: Path) -> dict:
    deck = Deck.model_validate_json(path.read_text(encoding="utf-8"))
    risk = score_deck(deck)
    new_lint = [{"code": i.code, "message": i.message} for i in lint_deck(deck) if i.code in NEW_RULES]
    return {"file": path.name, "slides": len(risk.slides), "mean_score": round(risk.mean_score, 1),
            "risky_pages": len(risk.risky), "risky_share": round(risk.risky_share, 3), "over_limit": risk.over_limit,
            "risky": [r.to_json() for r in risk.risky], "new_lint_rules": new_lint}


def run_numbers(run_dir: Path) -> dict:
    out: dict = {"run": run_dir.name, "decks": [deck_numbers(run_dir / name) for name in ("deck.v3.json", "deck.json")
                                                 if (run_dir / name).is_file()]}
    video = next((run_dir / "assembly" / n for n in ("release.mp4", "final.mp4", "draft.mp4")
                  if (run_dir / "assembly" / n).is_file()), None)
    if video is not None:
        out["static_scan"] = {"video": video.name, **{k: v for k, v in static_scan.summary(static_scan.scan(video)).items()}}
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    results = []
    for run in args.runs:
        if not (run / "deck.json").is_file():
            print(f"{run}: no deck.json", file=sys.stderr)
            return 2
        results.append(run_numbers(run))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in results:
        for d in r["decks"]:
            print(f"{r['run']:18} {d['file']:14} mean {d['mean_score']:5} risky {d['risky_pages']}/{d['slides']} "
                  f"new-lint {[i['code'] for i in d['new_lint_rules']]}")
        if "static_scan" in r:
            s = r["static_scan"]
            print(f"{r['run']:18} static {s['seconds_by_kind']} dead zones {len(s['dead_zones'])} = {s['dead_zone_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
