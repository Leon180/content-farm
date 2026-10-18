"""Stage thresholds: turn a round's reviewer outputs into scores, a pass / fail verdict with
reasons, and the verified issue list. Pure functions — no I/O — so every rule has a unit test.

Holdout viewers are scored separately and never feed the verdict or the fix list (anti-overfitting).
A seat without a valid output fails the round: the gate never opens on a partial panel.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import Any

from content_farm.review.config import Stage
from content_farm.review.sentences import Sentence, position_share

_NORMALIZE = re.compile(r"[\s「」『』“”\"'‘’，,。．.！!？?：:；;、（）()\[\]【】—\-…~～]+")


@dataclass(frozen=True)
class Seat:
    rid: str
    role: str
    kind: str
    holdout: bool
    ok: bool
    output: dict[str, Any] | None


@dataclass
class Verdict:
    passed: bool
    reasons: list[str]
    scores: dict[str, Any]
    issues: list[dict[str, Any]] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)     # unverifiable issues
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {"pass": self.passed, "reasons": self.reasons, "scores": self.scores, "issues": self.issues,
                "dropped": self.dropped, **self.extra}


def normalize(text: str) -> str:
    return _NORMALIZE.sub("", text or "").lower()


def seconds(text: str | None) -> float | None:
    match = re.match(r"^\s*(\d+):(\d{1,2})", str(text or ""))
    return int(match.group(1)) * 60 + int(match.group(2)) if match else None


def verify_issue(issue: dict[str, Any], *, corpus: str, sentence_ids: set[str], items: set[str],
                 duration: float) -> str:
    """'' when the issue points at something real, else why it was dropped."""
    ref = issue.get("ref") or {}
    target = ref.get("target")
    ids = [str(i) for i in ref.get("sentence_ids") or []]
    unknown = [i for i in ids if i not in sentence_ids]
    if unknown and sentence_ids:
        return f"unknown sentence id(s) {unknown}"
    if target in ("video", "audio"):
        t = seconds(ref.get("t"))
        if t is None or (duration and t > duration + 1):
            return f"time {ref.get('t')!r} not in the video"
        return ""
    if target in ("thumbnail", "media", "topic") and str(ref.get("item") or "").upper() in {i.upper() for i in items}:
        return ""
    evidence = normalize(issue.get("evidence", ""))
    if len(evidence) < 2:
        return "no evidence quote"
    if evidence not in normalize(corpus):
        return "evidence quote not found in the material"
    return ""


def split_issues(raw: list[dict[str, Any]], **context: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept, dropped = [], []
    for issue in raw:
        why = verify_issue(issue, **context)
        (dropped if why else kept).append({**issue, **({"dropped_because": why} if why else {})})
    return kept, dropped


def _collect(seats: list[Seat]) -> list[dict[str, Any]]:
    out = []
    for seat in seats:
        if seat.holdout or not seat.output:
            continue
        for issue in [*(seat.output.get("issues") or []), *(seat.output.get("top_fixes") or [])]:
            out.append({**issue, "who": seat.rid})
        for n, claim in enumerate(seat.output.get("claims") or []):
            if claim.get("status") in ("wrong", "unsourced"):
                out.append({"ref": {"target": "script" if claim.get("sentence_ids") else "article",
                                    "sentence_ids": claim.get("sentence_ids") or []},
                            "category": "fact", "severity": "high", "problem": f"{claim['status']}：{claim['claim']}",
                            "fix": claim.get("note", ""), "evidence": claim.get("evidence", ""),
                            "caused_by": "article" if not claim.get("sentence_ids") else "deck", "who": seat.rid,
                            "claim_key": f"{seat.rid}#{n}"})
    return out


def _missing(seats: list[Seat]) -> list[str]:
    return [s.rid for s in seats if not s.ok]


def _fact_errors(seat: Seat) -> int:
    return sum(1 for c in (seat.output or {}).get("claims") or [] if c.get("status") in ("wrong", "unsourced"))


def _base(seats: list[Seat]) -> tuple[list[str], list[Seat]]:
    missing = _missing(seats)
    reasons = [f"評審沒有合格輸出：{', '.join(missing)}"] if missing else []
    return reasons, [s for s in seats if s.ok and not s.holdout]


def topic(stage: Stage, seats: list[Seat], *, candidate_ids: list[str], short: bool = False, **_: Any) -> Verdict:
    reasons, regular = _base(seats)
    clicks: dict[str, list[float]] = {c: [] for c in candidate_ids}
    pro: dict[str, list[float]] = {c: [] for c in candidate_ids}
    vetoed: set[str] = set()
    for seat in regular:
        for pick in (seat.output or {}).get("picks") or []:
            clicks.setdefault(str(pick["candidate_id"]), []).append(float(pick["click"]))
        for score in (seat.output or {}).get("scores") or []:
            pro.setdefault(str(score["candidate_id"]), []).append(float(score["score"]))
            if score.get("veto"):
                vetoed.add(str(score["candidate_id"]))
    ranking = []
    for cid in candidate_ids:
        viewer = statistics.mean(clicks[cid]) if clicks[cid] else 0.0
        panel = statistics.mean(pro[cid]) if pro[cid] else viewer
        ranking.append({"id": cid, "viewer": round(viewer, 2), "pro": round(panel, 2),
                        "score": round(0.5 * viewer + 0.5 * panel, 2), "vetoed": cid in vetoed})
    ranking.sort(key=lambda r: (r["vetoed"], -r["score"]))
    need = stage.threshold.top_n_short if short else stage.threshold.top_n_long
    floor = stage.threshold.topic_min_score or 0
    chosen = [r["id"] for r in ranking if not r["vetoed"] and r["score"] >= floor][:need]
    if len(chosen) < need:
        reasons.append(f"只有 {len(chosen)} 題 ≥ {floor} 且未被否決，需要 {need}")
    return Verdict(not reasons, reasons, {"ranking": ranking}, extra={"chosen": chosen})


def article(stage: Stage, seats: list[Seat], *, arbitration: dict[str, Any] | None = None,
            **context: Any) -> Verdict:
    reasons, regular = _base(seats)
    checkers = [s for s in regular if s.kind == "fact"]
    errors = {s.rid: _fact_errors(s) for s in checkers}
    limit = stage.threshold.fact_errors_max or 0
    scores: dict[str, Any] = {"fact_errors": errors}
    if arbitration is None:
        for rid, count in errors.items():
            if count > limit:
                reasons.append(f"{rid} 找到 {count} 個錯誤或無來源說法（門檻 {limit}）")
        raw = _collect(seats)
    else:
        confirmed = set(arbitration["agreed"]) | set(arbitration["upheld"]) | set(arbitration["unanswered"])
        scores.update(confirmed_errors=len(confirmed), agreed=len(arbitration["agreed"]),
                      disputes=len(arbitration["disputes"]), upheld=len(arbitration["upheld"]),
                      unanswered=len(arbitration["unanswered"]), arbiter_ruled=arbitration["ruled"])
        if arbitration["disputes"] and not arbitration["ruled"]:
            reasons.append("仲裁查核員沒有合格輸出")
        if len(confirmed) > limit:
            reasons.append(f"確認 {len(confirmed)} 個錯誤或無來源說法（兩位一致 {len(arbitration['agreed'])}、"
                           f"仲裁維持 {len(arbitration['upheld'])}、仲裁未答 {len(arbitration['unanswered'])}；門檻 {limit}）")
        raw = [i for i in _collect(seats) if i.get("category") != "fact" or i.get("claim_key") in confirmed]
    kept, dropped = split_issues(raw, **_context(context))
    scores["writers"] = {s.rid: s.output.get("score") for s in regular if s.kind == "pro" and s.output}
    return Verdict(not reasons, reasons, scores, kept, dropped,
                   extra={"arbitration": arbitration} if arbitration is not None else {})


def _context(context: dict[str, Any]) -> dict[str, Any]:
    sentences: list[Sentence] = context.get("sentences") or []
    return {"corpus": context.get("corpus", ""), "sentence_ids": {s.id for s in sentences},
            "items": set(context.get("items") or []), "duration": float(context.get("duration") or 0)}


def _leave(viewers: list[Seat], sentences: list[Sentence], duration: float) -> list[float]:
    out = []
    for seat in viewers:
        data = seat.output or {}
        if "left_at_sentence" in data:
            out.append(position_share(sentences, data.get("left_at_sentence")))
        else:
            left = seconds(data.get("left_at"))
            out.append(1.0 if left is None or not duration else min(left / duration, 1.0))
    return out


def script(stage: Stage, seats: list[Seat], *, sentences: list[Sentence], **context: Any) -> Verdict:
    reasons, regular = _base(seats)
    viewers = [s for s in regular if s.kind == "viewer"]
    leave = _leave(viewers, sentences, 0)
    median = round(statistics.median(leave), 3) if leave else 0.0
    t = stage.threshold
    if t.leave_median_pct is not None and median < t.leave_median_pct:
        reasons.append(f"觀眾離開中位 {median:.0%} < {t.leave_median_pct:.0%}")
    writers = {s.rid: float(s.output.get("score", 0)) for s in regular if s.role.startswith("writer") and s.output}
    for rid, score in writers.items():
        if t.writer_min is not None and score < t.writer_min:
            reasons.append(f"{rid} {score:g}/10 < {t.writer_min:g}")
    errors = {s.rid: _fact_errors(s) for s in regular if s.kind == "fact"}
    for rid, count in errors.items():
        if t.fact_errors_max is not None and count > t.fact_errors_max:
            reasons.append(f"{rid} 找到 {count} 個事實錯誤")
    holdout = [s for s in seats if s.holdout and s.ok]
    kept, dropped = split_issues(_collect(seats), **_context({**context, "sentences": sentences}))
    advisory = t.fact_errors_max is None      # script_structure: facts are listed for the fix list, never block
    if advisory:
        kept = [{**i, "advisory": True} if i.get("category") == "fact" else i for i in kept]
    scores = {"leave_median_pct": median, "leave": leave, "writers": writers,
              ("fact_errors_advisory" if advisory else "fact_errors"): errors,
              "pros": {s.rid: s.output.get("score") for s in regular if s.kind == "pro" and s.output},
              "holdout_leave": _leave(holdout, sentences, 0) if holdout else None}
    return Verdict(not reasons, reasons, scores, kept, dropped)


_FEED_NO = re.compile(r"feed\s*(\d+)", re.IGNORECASE)


def feed_key(rid: str, answer: str, keys: dict[str, dict]) -> dict | None:
    """The answer key for a viewer's feed, however loosely they named it (``feeds/x_feed1.jpg``,
    ``x_feed1``, ``feed1``): only that viewer's own feeds can match."""
    name = str(answer).split("/")[-1]
    if name in keys:
        return keys[name]
    match = _FEED_NO.search(name)
    return keys.get(f"{rid}_feed{match.group(1)}.jpg") if match else None


def homepage_stats(viewers: list[Seat], keys: dict[str, dict]) -> dict[str, dict]:
    slots: dict[str, dict[str, list]] = {}
    for seat in viewers:
        for answer in (seat.output or {}).get("homepage") or []:
            key = feed_key(seat.rid, answer.get("feed", ""), keys)
            if key is None:
                continue
            noticed = [int(n) for n in answer.get("noticed") or []]
            rank = noticed.index(key["ours_card"]) + 1 if key["ours_card"] in noticed else len(noticed) + 1
            slot = slots.setdefault(key["variant"], {"ranks": [], "picked": [], "cards": []})
            slot["ranks"].append(rank)
            slot["picked"].append(int(answer.get("picked", -1)) == key["ours_card"])
            slot["cards"].append(key["cards"])
    return {v: {"noticed_median": statistics.median(s["ranks"]), "pick_rate": round(sum(s["picked"]) / len(s["picked"]), 2),
                "chance": round(1 / statistics.mean(s["cards"]), 3), "answers": len(s["ranks"])}
            for v, s in sorted(slots.items())}


def title_thumb(stage: Stage, seats: list[Seat], *, keys: dict[str, dict] | None = None,
                auto: dict[str, list[str]] | None = None, **context: Any) -> Verdict:
    reasons, regular = _base(seats)
    viewers = [s for s in regular if s.kind == "viewer"]
    home = homepage_stats(viewers, keys or {})
    t = stage.threshold
    if t.noticed_median_max is not None:
        if not home:
            reasons.append("沒有首頁情境結果（缺競品首頁或評審沒作答）")
        else:
            best = min(home.values(), key=lambda h: (h["noticed_median"], -h["pick_rate"]))
            if best["noticed_median"] > t.noticed_median_max:
                reasons.append(f"首頁被注意名次中位 {best['noticed_median']} > {t.noticed_median_max:g}")
            if t.pick_factor is not None and best["pick_rate"] < t.pick_factor * best["chance"]:
                reasons.append(f"首頁被選比例 {best['pick_rate']:.0%} < {t.pick_factor:g}×{best['chance']:.0%}")
    failed_auto = {k: v for k, v in (auto or {}).items() if v}
    if t.auto_checks and failed_auto:
        reasons += [f"縮圖 {k} 自動檢查未過：{'、'.join(v)}" for k, v in sorted(failed_auto.items())]
    flagged = [c for s in regular if s.kind == "producer" for c in (s.output or {}).get("checks") or []
               if c.get("exaggerated") or not c.get("consistent", True)]
    if t.producer_honest and flagged:
        reasons += [f"製作人判定 {c['item']} 誇大或與內容不一致：{c.get('why', '')}" for c in flagged]
    title_clicks: dict[str, list[float]] = {}
    for seat in viewers:
        for item in (seat.output or {}).get("titles") or []:
            title_clicks.setdefault(str(item["title_id"]), []).append(float(item["click"]))
    titles = {k: round(statistics.mean(v), 2) for k, v in title_clicks.items()}
    honest = [k for k in titles if k not in {str(c["item"]) for c in flagged}]
    best_title = max(honest, key=titles.get) if honest else None
    kept, dropped = split_issues(_collect(seats), **_context(context))
    scores = {"homepage": home, "titles": titles, "best_title": best_title, "auto": auto or {},
              "designer": {s.rid: (s.output or {}).get("variants") for s in regular if s.kind == "designer"}}
    return Verdict(not reasons, reasons, scores, kept, dropped)


def media(stage: Stage, seats: list[Seat], *, pending: list | None = None, **context: Any) -> Verdict:
    reasons, regular = _base(seats)
    bad = [a for s in regular for a in (s.output or {}).get("assets") or []
           if a.get("logo") or a.get("real_person") or a.get("official_character") or not a.get("license_ok", True)]
    kept, dropped = split_issues(_collect(seats), **_context(context))
    count = len(bad) + len([i for i in kept if i.get("category") == "compliance"])
    t = stage.threshold
    if t.compliance_issues_max is not None and count > t.compliance_issues_max:
        reasons.append(f"合規問題 {count} 個：" + "、".join(str(a.get("asset")) for a in bad[:8]))
    if t.licenses_confirmed and pending:
        reasons.append(f"credits.json 還有 {len(pending)} 筆授權未確定")
    rework = sorted({str(a.get("asset")) for a in bad})
    return Verdict(not reasons, reasons, {"compliance_issues": count, "pending": len(pending or [])}, kept, dropped,
                   extra={"rework_assets": rework})


def final(stage: Stage, seats: list[Seat], *, sentences: list[Sentence] | None = None, duration: float = 0,
          columns: dict[str, dict] | None = None, **context: Any) -> Verdict:
    reasons, regular = _base(seats)
    if columns is None and context.get("objective"):
        from content_farm.evaluation.aggregate import column_scores, objective_checks

        columns = column_scores(objective_checks(context["objective"], context.get("thumbs")))
    viewers = [s for s in regular if s.kind == "viewer"]
    leave = _leave(viewers, [], duration)
    median = round(statistics.median(leave), 3) if leave else 0.0
    t = stage.threshold
    if t.leave_median_pct is not None and median < t.leave_median_pct:
        reasons.append(f"觀眾離開中位 {median:.0%} < {t.leave_median_pct:.0%}")
    if t.objective_all_green:
        reasons += [f"客觀指標 {name} 欄有關鍵項未過" for name, col in (columns or {}).items() if col.get("light") == "red"]
    matches = [bool((s.output or {}).get("thumbnail_matches")) for s in viewers]
    if t.thumbnail_consistent and matches and sum(matches) * 2 < len(matches):
        reasons.append(f"縮圖與影片一致：只有 {sum(matches)}/{len(matches)} 位觀眾認為一致")
    if t.pro_min is not None:
        reasons += [f"{s.rid} {s.output.get('score')}/10 < {t.pro_min:g}" for s in regular
                    if s.kind == "pro" and s.output and float(s.output.get("score", 0)) < t.pro_min]
    holdout = [s for s in seats if s.holdout and s.ok]
    kept, dropped = split_issues(_collect(seats), **_context({**context, "sentences": sentences or [],
                                                               "duration": duration}))
    scores = {"leave_median_pct": median, "leave": leave, "columns": columns or {},
              "thumbnail_matches": f"{sum(matches)}/{len(matches)}",
              "pros": {s.rid: s.output.get("score") for s in regular if s.kind == "pro" and s.output},
              "pronunciation": sorted({w for s in viewers for w in (s.output or {}).get("pronunciation") or []}),
              "holdout_leave": _leave(holdout, [], duration) if holdout else None}
    return Verdict(not reasons, reasons, scores, kept, dropped)


# script_facts uses the article judge: two checkers + arbitration, 0 confirmed errors (7afa95870a4e = A)
JUDGES = {"topic": topic, "shorts_topic": topic, "article": article, "script_structure": script,
          "script_facts": article, "shorts_script": script,
          "title_thumb": title_thumb, "shorts_title": title_thumb, "media": media, "final": final,
          "shorts_final": final}
