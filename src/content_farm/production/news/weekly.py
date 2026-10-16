"""``produce.py news weekly``: the week's 3–5 most important Shorts → one long video.

Selection: Shorts of the ISO week whose final gate is approved ("已發"), ranked
by the script's ``importance`` (set when the Short was written), then the day's
ranking score. Each picked story becomes one deck section = one YouTube chapter.

The weekly run-dir (``output/hn-weekly-<YYYY-Www>/``) holds ``news_weekly.json``
(the plan; marks the run-dir) and ``weekly_plan.md`` (what /news-weekly reads to
write ``deck.json``). From the deck on it is the normal explainer pipeline:
slides → deck gate → voice → media → assembly → mascot → final gate.
No article gate: every story was read and approved as a Short already; the
deck gate is where Leon checks the deeper material.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from content_farm.explainer.deck import Deck
from content_farm.production.channels import Channel, Gate
from content_farm.production.news import script as ns
from content_farm.production.news.series import NewsSeries
from content_farm.production.state import load_state
from content_farm.production.steps import NEWS_WEEKLY_FILE

WEEKLY_FILE = NEWS_WEEKLY_FILE
PLAN_MD = "weekly_plan.md"


@dataclass(frozen=True)
class WeeklyItem:
    run_dir: Path
    day: str
    news: ns.NewsScript
    score: float
    approved: bool


def weekly_dir(root: Path, week: str) -> Path:
    return root / f"hn-weekly-{week}"


def parse_week(week: str) -> tuple[date, date]:
    year_text, week_text = week.upper().split("-W")
    monday = date.fromisocalendar(int(year_text), int(week_text), 1)
    return monday, date.fromisocalendar(int(year_text), int(week_text), 7)


def _approved(run_dir: Path, channel: Channel) -> bool:
    decision = load_state(run_dir, channel.code).decisions.get(Gate.FINAL.value)
    return decision is not None and decision.verdict == "approved"


def week_items(root: Path, week: str, channel: Channel) -> list[WeeklyItem]:
    first, last = parse_week(week)
    items = []
    for item_file in sorted(root.glob(f"hn-*-*/{ns.ITEM_FILE}")):
        run_dir = item_file.parent
        meta = json.loads(item_file.read_text(encoding="utf-8"))
        day = str(meta.get("day", ""))
        if not day or not first <= date.fromisoformat(day) <= last or not (run_dir / ns.SCRIPT_FILE).is_file():
            continue
        items.append(WeeklyItem(run_dir, day, ns.load_script(run_dir), float(meta.get("score", 0.0)),
                                _approved(run_dir, channel)))
    return items


def select(items: list[WeeklyItem], series: NewsSeries, *, include_unapproved: bool = False) -> list[WeeklyItem]:
    low, high = series.weekly.items
    pool = [i for i in items if i.approved or include_unapproved]
    ranked = sorted(pool, key=lambda i: (-i.news.importance, -i.score, i.day))
    if len(ranked) < low:
        hint = "" if include_unapproved else "（只算 final gate 已核可的；試做可加 --include-unapproved）"
        raise ValueError(f"only {len(ranked)} Short(s) this week, need ≥ {low}{hint}")
    return sorted(ranked[:high], key=lambda i: i.day)   # chapters in calendar order


def _item_block(n: int, item: WeeklyItem) -> list[str]:
    beats = {b.kind: b.narration for b in item.news.beats}
    lines = [f"## 第 {n} 章：{item.news.title}", "",
             f"- 日期：{item.day}・重要度 {item.news.importance}・{'已核可' if item.approved else '⚠ 未核可（試做）'}",
             f"- Short run-dir：`{item.run_dir}`", "- 來源（讀取時間）："]
    lines += [f"  - [{s.kind}] {s.publisher or ''} {s.title} — {s.url}（{s.read_at or '—'}）" for s in item.news.sources]
    read_cache = json.loads((item.run_dir / ns.ITEM_FILE).read_text(encoding="utf-8")).get("read") or {}
    if read_cache.get("text_path"):
        lines.append(f"- 原文快取（只供寫稿查證，不轉貼）：`{read_cache['text_path']}`")
    lines += ["", "Short 怎麼講的：", *(f"- {k}：{v}" for k, v in beats.items()), "",
              "長片要多講的（寫稿時回原文再讀一次）：背景脈絡、數字口徑、反方說法、台灣廠商／使用者具體影響；"
              "觀點段延續 Short 的 take，但要多一層理由。", ""]
    return lines


def write_plan(root: Path, week: str, picked: list[WeeklyItem], series: NewsSeries) -> Path:
    directory = weekly_dir(root, week)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "series": "hn", "week": week,
               "target_seconds": list(series.weekly.target_seconds),
               "items": [{"run_dir": str(i.run_dir), "day": i.day, "item_id": i.news.item_id,
                          "title": i.news.title, "importance": i.news.importance, "approved": i.approved,
                          "sources": [s.model_dump() for s in i.news.sources]} for i in picked]}
    (directory / WEEKLY_FILE).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    low, high = series.weekly.target_seconds
    lines = [f"# {series.name}・週整理 {week}", "",
             f"目標長度 {low // 60}–{high // 60} 分（內容撐得起就 ≥ 8:00）。章節＝每則一章，開場一節、收尾一節。", ""]
    for n, item in enumerate(picked, start=1):
        lines += _item_block(n, item)
    (directory / PLAN_MD).write_text("\n".join(lines), encoding="utf-8")
    return directory


def check_deck(deck: Deck, plan: dict) -> list[str]:
    """Each story is its own section (chapter) and cites its read original."""
    problems = []
    items = plan["items"]
    if len(deck.sections) < len(items) + 1:
        problems.append(f"{len(deck.sections)} sections for {len(items)} stories; want one section per story "
                        "plus an opening (and a closing)")
    cited = {s.url for s in deck.sources}
    for item in items:
        primary = [s["url"] for s in item["sources"] if s["kind"] in ("article", "abstract")]
        if primary and not cited.intersection(primary):
            problems.append(f"{item['item_id']}: none of its read originals is in deck.sources ({primary[0]})")
    return problems
