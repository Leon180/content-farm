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

from content_farm.production.news import guard
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
            "format_reason": {"type": "string"},
            # ent guardrail: the seat flags a story that touches a forbidden topic; any flag excludes it
            "sensitive": {"type": "boolean"},
            "sensitive_reason": {"type": "string"}}}}}}

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


SENSITIVE_RULE = ("\n另外請標記 sensitive：只要這則牽涉未成年人、性醜聞細節、病情或死因的臆測、私人住址或家人，"
                  "或內容主要是未經證實的傳聞，sensitive 填 true 並在 sensitive_reason 寫一句理由（這類題目一律排除，不做）；"
                  "其他填 false。")


def prompt_for(seat: Seat, items: list[dict[str, Any]], channel_name: str, brief: str = "",
               topic_guard: bool = False) -> str:
    rows = []
    for it in items:
        read = it["read"]
        rows.append(f"### {it['id']}｜{it['title']}\n來源：{it['domain']}｜原文可讀字數：{read.get('chars', 0)}｜"
                    f"熱度：{it['popularity']}\n摘錄：{excerpt(read)}")
    traits = "；".join(seat.traits)
    about = brief or "台灣中文的每日科技新知頻道，沒有主持角色，畫面是新聞卡片與圖表"
    return (f"你是{seat.who}（{traits}）。你要幫「{channel_name}」（{about}）從下面的候選挑要做的題目。\n"
            "對每一則：1) score 1–10：以你的身分，看到這則的中文講解會不會點開、看完（10＝一定看；6 以下＝不值得做）；"
            "2) format：這則內容撐得起 6–10 分鐘長片（有多個層面、足夠的背景與數字，能講出 3 個以上不同的重點）就判 long，"
            "只有一個結論或一個數字的消息判 short（≤60 秒）；3) 各給一句理由。\n"
            "只憑摘錄判斷，不要編造原文沒有的事。依 id 逐則回答。" + (SENSITIVE_RULE if topic_guard else "")
            + "\n\n" + "\n\n".join(rows))


@dataclass(frozen=True)
class Outcome:
    chosen: list[dict[str, Any]]
    selection: dict[str, Any]


def _ask(seat: Seat, items: list[dict[str, Any]], channel_name: str, cwd: Path,
         client: Callable[[Call], CallResult], timeout_s: int, brief: str = "", topic_guard: bool = False) -> CallResult:
    call = Call(f"select-{seat.id}", prompt_for(seat, items, channel_name, brief, topic_guard), SCHEMA, SEAT_MODEL, SEAT_EFFORT,
                tools=(), cwd=cwd, timeout_s=timeout_s, retries=1)
    return client(call)


def _format_for(votes: list[str], read_chars: int) -> tuple[str, str]:
    long_votes = votes.count("long")
    if long_votes * 2 > len(votes) and read_chars >= MIN_LONG_CHARS:
        return "long", f"{long_votes}/{len(votes)} 席判長片，原文可讀 {read_chars} 字 ≥ {MIN_LONG_CHARS}"
    if long_votes * 2 > len(votes):
        return "short", f"{long_votes}/{len(votes)} 席判長片，但原文只有 {read_chars} 字 < {MIN_LONG_CHARS}（素材不夠撐 6 分鐘）→ Shorts"
    return "short", f"{len(votes) - long_votes}/{len(votes)} 席判 Shorts"


def cap_longs(rows: list[dict[str, Any]], max_long: int) -> list[dict[str, Any]]:
    """At most ``max_long`` picked stories stay long (a long video is hours of machine time and a full fact-check
    pipeline); the rest become Shorts, the demotion written into ``format_why``. Rows are in score order."""
    kept, out = 0, []
    for row in rows:
        if row["decision"] == "pick" and row["format"] == "long":
            if kept >= max_long:
                row = {**row, "format": "short",
                       "format_why": row["format_why"] + f"；每日長片上限 {max_long} 支，改做 Shorts"}
            else:
                kept += 1
        out.append(row)
    return out


def aggregate(items: list[dict[str, Any]], results: dict[str, CallResult], *, count: int,
              min_score: float = MIN_SCORE, max_long: int = 1,
              blocked: list[dict[str, Any]] | None = None) -> Outcome:
    """``blocked``: stories the topic guard removed before the panel (recorded as skipped, never picked)."""
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
        flagged = {sid: g.get("sensitive_reason") or "（未寫理由）" for sid, g in given.items() if g.get("sensitive")}
        rows.append({"id": it["id"], "title": it["title"], "position": it["position"],
                     "mean": round(mean(g["score"] for g in given.values()), 2), "sensitive": flagged,
                     "seats": {sid: {"score": g["score"], "reason": g["reason"], "format": g["format"],
                                     "format_reason": g["format_reason"]} for sid, g in given.items()},
                     "format": fmt, "format_why": why})
    rows.sort(key=lambda r: (-r["mean"], r["position"]))
    eligible = [r for r in rows if r["mean"] >= min_score and not r["sensitive"]]
    picked = {r["id"] for r in eligible[:count]}
    for r in rows:
        r["decision"] = ("pick" if r["id"] in picked else
                         "skip: 禁碰題材（評審標記）" if r["sensitive"] else
                         "skip: below floor" if r["mean"] < min_score else "skip: over count")
    rows += [{"id": b["id"], "title": b["title"], "position": b.get("position", 0), "mean": 0.0, "sensitive": {},
              "seats": {}, "format": "short", "format_why": "", "decision": f"skip: 禁碰題材（程式過濾）{b['why']}"}
             for b in blocked or []]
    rows = cap_longs(rows, max_long)
    chosen = [r for r in rows if r["decision"] == "pick"]
    usd = round(sum(r.cost_usd for r in results.values()), 4)
    return Outcome(chosen, {"min_score": min_score, "count": count, "usd": usd, "items": rows,
                            "seats": {sid: {"ok": r.ok, "model": r.model, "seconds": r.seconds,
                                            "cost_usd": r.cost_usd, "tokens": r.tokens, "errors": list(r.errors)}
                                      for sid, r in results.items()}})


def _blocked(r: dict[str, Any]) -> str | None:
    """The topic guard over what the story says about itself: headline, feed summary, page description."""
    return guard.blocked_reason(r["candidate"]["title"], r["candidate"].get("summary", ""),
                                (r.get("read") or {}).get("description", ""))


def select(day_dir: Path, ranked: list[dict[str, Any]], seats: tuple[Seat, ...], channel_name: str, *,
           count: int, client: Callable[[Call], CallResult] | None = None, timeout_s: int = 900,
           brief: str = "", topic_guard: bool = False) -> Outcome:
    """Run the seats in parallel over the readable candidates; write ``selection.json`` into ``day_dir``.
    ``topic_guard`` (ent): stories touching a forbidden topic are removed here, before any seat sees them."""
    readable = [(pos, r) for pos, r in enumerate(ranked, start=1) if r.get("read") and r["read"].get("ok")]
    blocked = [{"id": r["candidate"]["id"], "title": r["candidate"]["title"], "position": pos, "why": why}
               for pos, r in readable if topic_guard and (why := _blocked(r))]
    skip = {b["id"] for b in blocked}
    items = [{"id": r["candidate"]["id"], "title": r["candidate"]["title"], "domain": r["candidate"]["domain"],
              "popularity": r["popularity"], "read": r["read"], "position": pos}
             for pos, r in readable if r["candidate"]["id"] not in skip]
    if not items:
        raise RuntimeError("selection: no readable candidate")
    log_dir = day_dir / "select"
    run = client or (lambda call: run_call(call, log_dir=log_dir))
    with ThreadPoolExecutor(max_workers=len(seats)) as pool:
        futures = {seat.id: pool.submit(_ask, seat, items, channel_name, day_dir, run, timeout_s, brief, topic_guard) for seat in seats}
        results = {sid: future.result() for sid, future in futures.items()}
    outcome = aggregate(items, results, count=count, blocked=blocked)
    (day_dir / SELECTION_FILE).write_text(json.dumps(outcome.selection, ensure_ascii=False, indent=2), encoding="utf-8")
    return outcome


def write_decision(run_dir: Path, row: dict[str, Any]) -> Path:
    path = run_dir / DECISION_FILE
    path.write_text(json.dumps({"version": 1, "story": row["id"], "title": row["title"], "format": row["format"],
                                "why": row["format_why"], "mean_score": row["mean"], "seats": row["seats"]},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    return path
