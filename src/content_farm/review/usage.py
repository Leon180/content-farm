"""What one video has cost so far: the cloud lane (every ``claude -p`` reviewer and producer agent,
from the CLI's own usage report) and the local lane (wall time of each command step).

Sources, all inside the run-dir and only read: ``review/<stage>/round-*/scorecard.json`` (every seat,
side rounds and holdouts included), ``review/producers/producers.jsonl`` and ``production.log.jsonl``.
Costs are the CLI's notional figures; the calls are billed to the subscription.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from content_farm.review.client import TOKEN_KEYS, call_usage
from content_farm.review.rounds import REVIEW_DIR

# producer step -> review stage it answers (review.producers.STEP_STAGE, kept literal: no import cycle)
PRODUCER_STAGE = {"topic": "topic", "article": "article", "deck": "script_structure", "thumbnail_spec": "title_thumb"}


@dataclass
class Tally:
    calls: int = 0
    seconds: float = 0.0
    cost_usd: float = 0.0
    tokens: dict[str, int] = field(default_factory=lambda: dict.fromkeys(TOKEN_KEYS, 0))
    models: set[str] = field(default_factory=set)

    def add(self, usage: dict[str, Any]) -> Tally:
        self.calls += 1
        self.seconds += usage["seconds"]
        self.cost_usd += usage["cost_usd"]
        self.tokens = {k: self.tokens[k] + usage["tokens"][k] for k in TOKEN_KEYS}
        self.models |= set(usage["models_used"] or [usage["model"]])
        return self

    def merge(self, other: Tally) -> Tally:
        self.calls += other.calls
        self.seconds += other.seconds
        self.cost_usd += other.cost_usd
        self.tokens = {k: self.tokens[k] + other.tokens[k] for k in TOKEN_KEYS}
        self.models |= other.models
        return self

    def to_json(self) -> dict[str, Any]:
        return {"calls": self.calls, "seconds": round(self.seconds, 1), "cost_usd": round(self.cost_usd, 4),
                "tokens": dict(self.tokens), "models": sorted(m for m in self.models if m)}


def card_tally(card: dict[str, Any]) -> Tally:
    tally = Tally()
    for seat in card.get("seats", []):
        tally.add(call_usage(seat))
    return tally


def _json_lines(path: Path) -> Iterable[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def scorecards(run_dir: Path) -> list[tuple[str, str, dict[str, Any]]]:
    """(stage, round label, card) for every round folder with a scorecard, in stage then round order."""
    root = run_dir / REVIEW_DIR
    out = []
    for path in sorted(root.glob("*/round-*/scorecard.json")):
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append((path.parent.parent.name, path.parent.name, card))
    return sorted(out, key=lambda r: (r[0], int(r[1].split("-")[1]) if r[1].split("-")[1].isdigit() else 0, r[1]))


def producers(run_dir: Path) -> list[dict[str, Any]]:
    return list(_json_lines(run_dir / REVIEW_DIR / "producers" / "producers.jsonl"))


def producer_tally_by_stage(run_dir: Path) -> dict[str, Tally]:
    out: dict[str, Tally] = {}
    for row in producers(run_dir):
        stage = PRODUCER_STAGE.get(str(row.get("step")), str(row.get("step")))
        out.setdefault(stage, Tally()).add(call_usage(row))
    return out


def local_steps(run_dir: Path) -> dict[str, dict[str, Any]]:
    """Command steps (``exit_code`` events in production.log.jsonl): runs, total and last wall time."""
    out: dict[str, dict[str, Any]] = {}
    for row in _json_lines(run_dir / "production.log.jsonl"):
        if "exit_code" not in row or "seconds" not in row:
            continue
        step = out.setdefault(str(row.get("step")), {"runs": 0, "seconds": 0.0, "last_seconds": 0.0, "failed": 0})
        step["runs"] += 1
        step["seconds"] = round(step["seconds"] + float(row["seconds"] or 0), 1)
        step["last_seconds"] = float(row["seconds"] or 0)
        step["failed"] += int(row["exit_code"] != 0)
    return out


def _stage_order(stage: str) -> tuple[int, str]:
    from content_farm.review.scorecard_html import STAGE_TITLES

    order = list(STAGE_TITLES)
    return (order.index(stage) if stage in order else len(order), stage)


def report(run_dir: Path) -> dict[str, Any]:
    stages: dict[str, dict[str, Any]] = {}
    for stage, label, card in sorted(scorecards(run_dir), key=lambda r: _stage_order(r[0])):
        entry = stages.setdefault(stage, {"rounds": {}, "review": Tally(), "producer": Tally()})
        tally = card_tally(card)
        entry["rounds"][label] = tally.to_json()
        entry["review"].merge(tally)
    for stage, tally in producer_tally_by_stage(run_dir).items():
        stages.setdefault(stage, {"rounds": {}, "review": Tally(), "producer": Tally()})["producer"].merge(tally)
    stages = dict(sorted(stages.items(), key=lambda item: _stage_order(item[0])))
    total, review_total, producer_total = Tally(), Tally(), Tally()
    for entry in stages.values():
        review_total.merge(entry["review"])
        producer_total.merge(entry["producer"])
    total.merge(review_total).merge(producer_total)
    local = local_steps(run_dir)
    return {
        "run_dir": str(run_dir),
        "cloud": {"stages": {s: {"rounds": e["rounds"], "review": e["review"].to_json(),
                                 "producer": e["producer"].to_json(),
                                 "total": Tally().merge(e["review"]).merge(e["producer"]).to_json()}
                             for s, e in stages.items()},
                  "review": review_total.to_json(), "producer": producer_total.to_json(), "total": total.to_json()},
        "local": {"steps": local, "seconds": round(sum(s["seconds"] for s in local.values()), 1)},
    }


def _tokens(tokens: dict[str, int]) -> str:
    return " ".join(f"{k}={tokens[k]:,}" for k in TOKEN_KEYS)


def format_report(data: dict[str, Any]) -> str:
    cloud, local = data["cloud"], data["local"]
    lines = [f"run: {data['run_dir']}", "", "雲端車道（claude -p；名目費用，訂閱計費）"]
    for stage, entry in cloud["stages"].items():
        t = entry["total"]
        lines.append(f"  {stage:<18} {t['calls']:>3} 次  ${t['cost_usd']:>8.4f}  {t['seconds'] / 60:>6.1f} 分  "
                     f"{_tokens(t['tokens'])}")
        for label, r in entry["rounds"].items():
            lines.append(f"    {label:<16} 評審 {r['calls']:>2} 席  ${r['cost_usd']:>8.4f}  {_tokens(r['tokens'])}")
        p = entry["producer"]
        if p["calls"]:
            lines.append(f"    {'producer':<16} 產出 {p['calls']:>2} 次  ${p['cost_usd']:>8.4f}  {_tokens(p['tokens'])}")
    t = cloud["total"]
    lines += [f"  {'總計':<16} {t['calls']:>3} 次  ${t['cost_usd']:>8.4f}  {t['seconds'] / 60:>6.1f} 分  "
              f"{_tokens(t['tokens'])}",
              f"  （評審 ${cloud['review']['cost_usd']:.4f}、產出 ${cloud['producer']['cost_usd']:.4f}；"
              f"模型 {', '.join(t['models']) or '—'}）", "", "本機車道（指令步驟牆鐘）"]
    for step, s in local["steps"].items():
        failed = f"，失敗 {s['failed']}" if s["failed"] else ""
        lines.append(f"  {step:<20} {s['runs']:>2} 次  合計 {s['seconds']:>8.1f} s  最近 {s['last_seconds']:>7.1f} s{failed}")
    lines.append(f"  {'總計':<18} {local['seconds']:>8.1f} s（{local['seconds'] / 60:.1f} 分）")
    return "\n".join(lines)
