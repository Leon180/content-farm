"""Offline estimate of one rework round: whole chain vs. only the scenes the fix list touches.

Usage:
    python scripts/estimate_rework.py --run-dir output/<run> --fixes review/final.fixes.json
Reads the run's deck.json, the fix list and production.log.jsonl; prints per-step full / floor / incremental
seconds and the totals (see content_farm.production.rework_estimate for the method and its limits).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from content_farm.production import rework_estimate as est


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--fixes", type=Path, required=True, help="path relative to the run-dir, or absolute")
    args = parser.parse_args()
    fixes_path = args.fixes if args.fixes.is_absolute() else args.run_dir / args.fixes
    fixes = json.loads(fixes_path.read_text(encoding="utf-8"))
    deck = json.loads((args.run_dir / "deck.json").read_text(encoding="utf-8"))
    rows = est.estimate(fixes, deck, est.read_jsonl(args.run_dir / "production.log.jsonl"))
    scenes = est.affected_scenes(fixes)
    print(f"{fixes_path.name}: {len(scenes)} of {est.slide_count(deck)} scenes touched: {', '.join(sorted(scenes))}")
    print(f"{'step':<12}{'full':>8}{'floor':>8}{'incremental':>13}")
    for row in rows:
        print(f"{row.step:<12}{row.full_s:>8.0f}{row.floor_s:>8.0f}{row.incremental_s:>13.0f}")
    print(f"{'total':<12}{sum(r.full_s for r in rows):>8.0f}{sum(r.floor_s for r in rows):>8.0f}"
          f"{sum(r.incremental_s for r in rows):>13.0f}   (seconds, machine time only; queue and agent time excluded)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
