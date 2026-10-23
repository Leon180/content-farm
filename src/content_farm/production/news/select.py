"""Automatic topic pick + format decision for a ``series.news`` channel (Leon 2026-10-23).

No inbox for Leon: a small panel (the channel's viewer personas plus a producer) reads every readable
candidate's excerpt and, per story, gives

* a 1–10 score ("would I watch this?"), and
* a format vote — ``short`` (≤ 60 s) or ``long`` (6–10 min) — judged by whether the story can carry
  the longer form (decision 3d9f5448dbbc: no fixed format; the content decides).

The panel's votes are aggregated here, deterministically, with one hard guard: a story can only be
``long`` when the original we read has enough material (``MIN_LONG_CHARS``). Everything — every seat's
score and reason, the vote count, the guard — is written to ``selection.json`` and to each picked
run-dir's ``format_decision.json`` so the reason for a format is on record.

Each seat is one headless ``claude -p`` call on the Claude subscription (review.client), tools off.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

import yaml

from content_farm.review.client import Call, CallResult, run_call

PANELS_FILE = Path(__file__).resolve().parents[4] / "channels" / "shared" / "review_panels.yaml"
EXCERPT_CHARS = 1500
MIN_LONG_CHARS = 5000        # visible chars of original text needed before a story may become a long video
MIN_SCORE = 6.0              # same floor as the topic stage (review_panels.yaml topic_min_score)
SELECTION_FILE = "selection.json"
DECISION_FILE = "format_decision.json"
SEAT_MODEL, SEAT_EFFORT = "sonnet", "low"

SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["id", "score", "reason", "format", "format_reason"],
        "properties": {
            "id": {"type": "string"},
            "score": {"type": "number", "minimum": 1, "maximum": 10},
            "reason": {"type": "string"},
            "format": {"type": "string", "enum": ["short", "long"]},
            "format_reason": {"type": "string"}}}}}}

PRODUCER = {"id": "producer", "who": "頻道製作人",
            "traits": ["在意每則新聞值不值得做、做成哪種格式最划算", "長片要有至少 6 分鐘的內容：多個層面、可講的背景、數字或對比；"
                       "只有一個結論的消息做 Shorts 才不灌水", "原文太短、只是公告或單一數字的消息不要判長片"]}


@dataclass(frozen=True)
class Seat:
    id: str
    who: str
    traits: tuple[str, ...]


def seats_for(channel_code: str, path: Path = PANELS_FILE) -> tuple[Seat, ...]:
    """The first three non-holdout viewer personas of the channel + the producer."""
    personas = yaml.safe_load(path.read_text(encoding="utf-8")).get("personas", {}).get(channel_code, [])
    viewers = [p for p in personas if not p.get("holdout")][:3]
    if not viewers:
        raise ValueError(f"review_panels.yaml has no personas for channel {channel_code!r}")
    return tuple(Seat(p["id"], p["who"], tuple(p.get("traits", ()))) for p in (*viewers, PRODUCER))


def excerpt(read: dict[str, Any]) -> str:
    path = read.get("text_path") or ""
    if not path or not Path(path).is_file():
        return read.get("description", "")
    text = Path(path).read_text(encoding="utf-8").split("\n\n", 1)[-1]
    return " ".join(text.split())[:EXCERPT_CHARS]


def prompt_for(seat: Seat, items: list[dict[str, Any]], channel_name: str) -> str:
    rows = []
    for it in items:
        read = it["read"]
        rows.append(f"### {it['id']}｜{it['title']}\n來源：{it['domain']}｜原文可讀字數：{read.get('chars', 0)}｜"
                    f"熱度：{it['popularity']}\n摘錄：{excerpt(read)}")
    traits = "；".join(seat.traits)
    return (f"你是{seat.who}（{traits}）。你要幫「{channel_name}」（台灣中文的每日科技新知頻道，沒有主持角色，"
            "畫面是新聞卡片與圖表）從下面的候選挑要做的題目。\n"
            "對每一則：1) score 1–10：以你的身分，看到這則的中文講解會不會點開、看完（10＝一定看；6 以下＝不值得做）；"
            "2) format：這則內容撐得起 6–10 分鐘長片（有多個層面、足夠的背景與數字，能講出 3 個以上不同的重點）就判 long，"
            "只有一個結論或一個數字的消息判 short（≤60 秒）；3) 各給一句理由。\n"
            "只憑摘錄判斷，不要編造原文沒有的事。依 id 逐則回答。\n\n" + "\n\n".join(rows))


@dataclass(frozen=True)
class Outcome:
    chosen: list[dict[str, Any]]
    selection: dict[str, Any]


def _ask(seat: Seat, items: list[dict[str, Any]], channel_name: str, cwd: Path,
         client: Callable[[Call], CallResult], timeout_s: int) -> CallResult:
    call = Call(f"select-{seat.id}", prompt_for(seat, items, channel_name), SCHEMA, SEAT_MODEL, SEAT_EFFORT,
                tools=(), cwd=cwd, timeout_s=timeout_s, retries=1)
    return client(call)


def _format_for(votes: list[str], read_chars: int) -> tuple[str, str]:
    long_votes = votes.count("long")
    if long_votes * 2 > len(votes) and read_chars >= MIN_LONG_CHARS:
        return "long", f"{long_votes}/{len(votes)} 席判長片，原文可讀 {read_chars} 字 ≥ {MIN_LONG_CHARS}"
    if long_votes * 2 > len(votes):
        return "short", f"{long_votes}/{len(votes)} 席判長片，但原文只有 {read_chars} 字 < {MIN_LONG_CHARS}（素材不夠撐 6 分鐘）→ Shorts"
    return "short", f"{len(votes) - long_votes}/{len(votes)} 席判 Shorts"


def aggregate(items: list[dict[str, Any]], results: dict[str, CallResult], *, count: int,
              min_score: float = MIN_SCORE) -> Outcome:
    per_seat: dict[str, dict[str, dict[str, Any]]] = {}
    for seat_id, result in results.items():
        if result.ok and result.output:
            per_seat[seat_id] = {row["id"]: row for row in result.output["items"]}
    if not per_seat:
        raise RuntimeError("selection panel: every seat failed (" + "; ".join(
            e for r in results.values() for e in r.errors)[:300] + ")")
    rows = []
    for it in items:
        given = {sid: rows_by_id[it["id"]] for sid, rows_by_id in per_seat.items() if it["id"] in rows_by_id}
        if not given:
            continue
        votes = [g["format"] for g in given.values()]
        fmt, why = _format_for(votes, int(it["read"].get("chars", 0)))
        rows.append({"id": it["id"], "title": it["title"], "position": it["position"],
                     "mean": round(mean(g["score"] for g in given.values()), 2),
                     "seats": {sid: {"score": g["score"], "reason": g["reason"], "format": g["format"],
                                     "format_reason": g["format_reason"]} for sid, g in given.items()},
                     "format": fmt, "format_why": why})
    rows.sort(key=lambda r: (-r["mean"], r["position"]))
    eligible = [r for r in rows if r["mean"] >= min_score]
    chosen = eligible[:count]
    picked = {r["id"] for r in chosen}
    for r in rows:
        r["decision"] = "pick" if r["id"] in picked else ("skip: below floor" if r["mean"] < min_score else "skip: over count")
    usd = round(sum(r.cost_usd for r in results.values()), 4)
    return Outcome(chosen, {"min_score": min_score, "count": count, "usd": usd, "items": rows,
                            "seats": {sid: {"ok": r.ok, "model": r.model, "seconds": r.seconds,
                                            "cost_usd": r.cost_usd, "tokens": r.tokens, "errors": list(r.errors)}
                                      for sid, r in results.items()}})


def select(day_dir: Path, ranked: list[dict[str, Any]], seats: tuple[Seat, ...], channel_name: str, *,
           count: int, client: Callable[[Call], CallResult] | None = None, timeout_s: int = 900) -> Outcome:
    """Run the seats in parallel over the readable candidates; write ``selection.json`` into ``day_dir``."""
    items = [{"id": r["candidate"]["id"], "title": r["candidate"]["title"], "domain": r["candidate"]["domain"],
              "popularity": r["popularity"], "read": r["read"], "position": pos}
             for pos, r in enumerate(ranked, start=1) if r.get("read") and r["read"].get("ok")]
    if not items:
        raise RuntimeError("selection: no readable candidate")
    log_dir = day_dir / "select"
    run = client or (lambda call: run_call(call, log_dir=log_dir))
    with ThreadPoolExecutor(max_workers=len(seats)) as pool:
        futures = {seat.id: pool.submit(_ask, seat, items, channel_name, day_dir, run, timeout_s) for seat in seats}
        results = {sid: future.result() for sid, future in futures.items()}
    outcome = aggregate(items, results, count=count)
    (day_dir / SELECTION_FILE).write_text(json.dumps(outcome.selection, ensure_ascii=False, indent=2), encoding="utf-8")
    return outcome


def write_decision(run_dir: Path, row: dict[str, Any]) -> Path:
    path = run_dir / DECISION_FILE
    path.write_text(json.dumps({"version": 1, "story": row["id"], "title": row["title"], "format": row["format"],
                                "why": row["format_why"], "mean_score": row["mean"], "seats": row["seats"]},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    return path
