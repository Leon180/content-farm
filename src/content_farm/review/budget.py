"""Cloud-lane budget per video (cf-cost-fix, Leon 2026-10-22).

Every ``claude -p`` call — reviewers, arbiters, producer agents — reports a nominal list-price cost, and the
pipeline already writes it down (scorecards, ``review/producers/producers.jsonl``). The budget is the sum of
those, for one run-dir. Before each new review round and each producer run the runner asks ``check``; over the
limit it stops, writes ``review/budget.stop.json`` and reports. It never continues by itself: raising the limit is a
person's decision (``produce.py run --budget-usd N`` records it in ``review/budget.json``).

Limit: ``--budget-usd`` / ``review/budget.json`` > ``CF_BUDGET_USD`` > ``review.budget.usd_per_video`` (default 15).
``review/budget.json`` may carry ``since`` (an ISO time): only calls after it count, so a video that was already
over a newly introduced limit can continue under a fresh allowance.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

BUDGET_FILE = Path("review") / "budget.json"
STOP_FILE = Path("review") / "budget.stop.json"
BUDGET_ENV = "CF_BUDGET_USD"
DEFAULT_USD = 15.0


@dataclass(frozen=True)
class Spend:
    total: float
    cards: float
    producers: float
    calls: int


def _after(at: str | None, since: str | None) -> bool:
    if not since:
        return True
    if not at:
        return False  # undated legacy rows predate ``since``; every row written now carries ``at``
    try:
        return datetime.fromisoformat(at) >= datetime.fromisoformat(since)
    except ValueError:
        return True


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def spent(run_dir: Path, since: str | None = None) -> Spend:
    """Nominal USD of every ``claude -p`` call recorded under ``run_dir/review`` (after ``since``)."""
    review = run_dir / "review"
    cards, calls = 0.0, 0
    for path in review.glob("*/**/scorecard.json"):
        if "snapshot" in path.relative_to(review).parts:
            continue
        card = _read(path)
        if _after(card.get("at"), since):
            cards += float(card.get("cost_usd") or 0)
            calls += sum(1 for s in card.get("seats", []) if not s.get("cached") and not s.get("carried_from"))
    producers = 0.0
    log = review / "producers" / "producers.jsonl"
    if log.is_file():
        for line in log.read_text(encoding="utf-8").splitlines():
            row = json.loads(line) if line.strip() else {}
            if _after(row.get("at"), since):
                producers += float(row.get("cost_usd") or 0)
                calls += 1
    return Spend(round(cards + producers, 4), round(cards, 4), round(producers, 4), calls)


def limit(run_dir: Path, *, configured: float | None = None, override: float | None = None) -> tuple[float, str | None]:
    """(limit in USD, ``since``): the explicit override, else the run-dir's budget file, else the environment,
    else the config's ``usd_per_video``, else ``DEFAULT_USD``."""
    stored = _read(run_dir / BUDGET_FILE)
    since = stored.get("since")
    if override is not None:
        return float(override), since
    if stored.get("usd") is not None:
        return float(stored["usd"]), since
    env = os.environ.get(BUDGET_ENV, "").strip()
    if env:
        return float(env), since
    return float(configured if configured is not None else DEFAULT_USD), since


def record_raise(run_dir: Path, usd: float, *, since: str | None = None) -> None:
    """Remember a person's decision to allow ``usd`` for this video (and from when it counts)."""
    path = run_dir / BUDGET_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    old = _read(path)
    data = {"usd": usd, "since": since if since is not None else old.get("since"),
            "set_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def check(run_dir: Path, *, configured: float | None = None, override: float | None = None) -> str | None:
    """None while the video is within budget; else the message that stops the run (also written to
    ``review/budget.stop.json``)."""
    cap, since = limit(run_dir, configured=configured, override=override)
    used = spent(run_dir, since)
    if used.total < cap:
        return None
    message = (f"雲端車道預算用完：名目 ${used.total:.2f}（評審 ${used.cards:.2f}＋產出 agent ${used.producers:.2f}，"
               f"{used.calls} 次呼叫）≥ 上限 ${cap:.2f}。不自動繼續；要繼續請 `produce.py run --budget-usd <新上限>`。")
    stop = run_dir / STOP_FILE
    stop.parent.mkdir(parents=True, exist_ok=True)
    stop.write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "limit_usd": cap,
                                "spent_usd": used.total, "reviewers_usd": used.cards, "producers_usd": used.producers,
                                "since": since, "message": message}, ensure_ascii=False, indent=1), encoding="utf-8")
    return message
