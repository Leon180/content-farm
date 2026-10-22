#!/usr/bin/env python3
"""Cost / token / rounds of a run-dir's review panels and producer agents (from the scorecards and
``review/producers/producers.jsonl`` the pipeline already writes). Used for the before / after numbers in
REPORT-cost-fix.md.

    python3 scripts/review_cost_report.py output/<run> [--json]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

TOKEN_KEYS = ("input", "output", "cache_read", "cache_write")


def _cards(review: Path):
    for path in sorted(review.glob("*/**/scorecard.json")):
        parts = path.relative_to(review).parts
        if "snapshot" in parts or "prompts" in parts:
            continue
        yield parts[0], path, json.loads(path.read_text(encoding="utf-8"))


def _tok(usage: dict) -> dict:
    return {k: int((usage.get("tokens") or {}).get(k) or 0) for k in TOKEN_KEYS}


def summarize(run_dir: Path) -> dict:
    review = run_dir / "review"
    stages: dict[str, dict] = defaultdict(lambda: {"rounds": 0, "cost": 0.0, "seconds": 0.0, "seats": 0, "cached": 0,
                                                    "carried": 0, "tokens": dict.fromkeys(TOKEN_KEYS, 0),
                                                    "models": defaultdict(float), "roles": defaultdict(float),
                                                    "input_per_seat": []})
    for stage, _, card in _cards(review):
        s = stages[stage]
        s["rounds"] += 1
        s["seconds"] += float(card.get("seconds") or 0)
        for seat in card.get("seats", []):
            s["seats"] += 1
            s["cost"] += float(seat.get("cost_usd") or 0)
            s["cached"] += 1 if seat.get("cached") else 0
            s["carried"] += 1 if seat.get("carried") else 0
            for key, value in _tok(seat).items():
                s["tokens"][key] += value
            fresh = _tok(seat)["input"] + _tok(seat)["cache_write"]
            if fresh and not seat.get("cached") and not seat.get("carried"):
                s["input_per_seat"].append(fresh)
            s["models"][f"{seat.get('model')}·{seat.get('effort')}"] += float(seat.get("cost_usd") or 0)
            s["roles"][seat.get("role", "?")] += float(seat.get("cost_usd") or 0)
    producers: dict[str, dict] = defaultdict(lambda: {"runs": 0, "cost": 0.0, "seconds": 0.0,
                                                       "tokens": dict.fromkeys(TOKEN_KEYS, 0), "models": set()})
    log = review / "producers" / "producers.jsonl"
    if log.is_file():
        for line in log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            p = producers[row.get("step", "?")]
            p["runs"] += 1
            p["cost"] += float(row.get("cost_usd") or 0)
            p["seconds"] += float(row.get("seconds") or 0)
            p["models"].add(f"{row.get('model')}·{row.get('effort')}")
            for key, value in _tok(row).items():
                p["tokens"][key] += value
    return {"stages": {k: _plain(v) for k, v in stages.items()}, "producers": {k: _plain(v) for k, v in producers.items()}}


def _plain(value):
    if isinstance(value, defaultdict | dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, float):
        return round(value, 2)
    return value


def render(summary: dict) -> str:
    lines = ["| 階段 | 輪數 | 席次數 | 快取／沿用 | 名目 $ | 牆鐘 s | 新輸入 token／席（中位） | 模型·effort → $ |",
             "|---|---|---|---|---|---|---|---|"]
    total = 0.0
    for stage, s in sorted(summary["stages"].items()):
        per = sorted(s["input_per_seat"])
        median = per[len(per) // 2] if per else 0
        models = "、".join(f"{k} ${v:.2f}" for k, v in sorted(s["models"].items()))
        lines.append(f"| {stage} | {s['rounds']} | {s['seats']} | {s['cached']}／{s['carried']} | {s['cost']:.2f} | "
                     f"{s['seconds']:.0f} | {median:,} | {models} |")
        total += s["cost"]
    lines += ["", "| 產出 agent | 次數 | 名目 $ | 牆鐘 s | 模型·effort |", "|---|---|---|---|---|"]
    for step, p in sorted(summary["producers"].items()):
        lines.append(f"| {step} | {p['runs']} | {p['cost']:.2f} | {p['seconds']:.0f} | {'、'.join(p['models'])} |")
        total += p["cost"]
    lines.append(f"\n合計名目 ${total:.2f}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = summarize(args.run_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=1) if args.json else render(summary))


if __name__ == "__main__":
    main()
