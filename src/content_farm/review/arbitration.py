"""Article fact-check arbitration (Leon 2026-10-18 decision 59fdefb32bd7 = D).

The article stage has two independent fact-checkers. An error (wrong / unsourced) both of them
flag counts as is. An error only one of them flags — the other judged it ok / analysis, or did
not list it — goes to a third checker (the stage's ``arbiter`` tier, opus · high), who sees both
sides' reasons and the sources; it counts only if the arbiter upholds it. The threshold stays 0.

Two claims are "the same" when their verbatim evidence quotes overlap the same article sentence
(``article_diff.sentences_for_quote``); a quote that is not found in the article matches nothing,
so it is always arbitrated rather than silently merged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from content_farm.review.article_diff import ArticleSentence, sentences_for_quote

ERROR = ("wrong", "unsourced")
ARBITER_ROLE = "fact_arbiter"

RULING = {"type": "object", "additionalProperties": False, "required": ["item", "status", "note"],
          "properties": {"item": {"type": "string"},
                         "status": {"enum": ["wrong", "unsourced", "ok", "analysis", "unverifiable"]},
                         "note": {"type": "string"}, "source_quote": {"type": ["string", "null"]}}}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["rulings"],
          "properties": {"rulings": {"type": "array", "items": RULING}}}


@dataclass(frozen=True)
class Flag:
    """One checker's error claim: ``key`` = "<rid>#<claim index>"."""
    key: str
    rid: str
    claim: dict[str, Any]
    sentences: frozenset[str]


def _flags(rid: str, output: dict[str, Any] | None, sentences: list[ArticleSentence]) -> list[Flag]:
    out = []
    for n, claim in enumerate((output or {}).get("claims") or []):
        if claim.get("status") in ERROR:
            ids = frozenset(sentences_for_quote(claim.get("evidence", ""), sentences))
            out.append(Flag(f"{rid}#{n}", rid, claim, ids))
    return out


def _counterpart(flag: Flag, other: dict[str, Any] | None, sentences: list[ArticleSentence]) -> list[dict[str, Any]]:
    if not flag.sentences:
        return []
    return [c for c in (other or {}).get("claims") or []
            if flag.sentences & set(sentences_for_quote(c.get("evidence", ""), sentences))]


def split(outputs: dict[str, dict[str, Any] | None], sentences: list[ArticleSentence]) -> dict[str, Any]:
    """Two checkers' outputs → {"agreed": [flag keys both flagged], "disputes": [...]}.

    An agreed pair counts once (under the first checker's key)."""
    if len(outputs) != 2:
        raise ValueError(f"arbitration needs exactly two fact-checkers, got {sorted(outputs)}")
    (a_id, a_out), (b_id, b_out) = sorted(outputs.items())
    agreed, disputes, paired = [], [], set()
    for flag in _flags(a_id, a_out, sentences):
        others = _counterpart(flag, b_out, sentences)
        if any(c.get("status") in ERROR for c in others):
            agreed.append(flag.key)
            paired |= {f.key for f in _flags(b_id, b_out, sentences)
                       if f.sentences & flag.sentences}
        else:
            disputes.append(_dispute(flag, b_id, others))
    for flag in _flags(b_id, b_out, sentences):
        if flag.key not in paired:
            disputes.append(_dispute(flag, a_id, _counterpart(flag, a_out, sentences)))
    return {"agreed": agreed, "disputes": disputes}


def _dispute(flag: Flag, other_rid: str, others: list[dict[str, Any]]) -> dict[str, Any]:
    return {"item": flag.key, "flagged_by": flag.rid, "claim": flag.claim, "sentences": sorted(flag.sentences),
            "other": other_rid, "other_claims": others}


def prompt(disputes: list[dict[str, Any]]) -> str:
    lines = []
    for d in disputes:
        mine = d["claim"]
        other = d["other_claims"]
        other_text = json.dumps(other, ensure_ascii=False) if other else "（沒有列出這條說法）"
        lines.append(f"- item {d['item']}：{d['flagged_by']} 判 {mine.get('status')}——說法「{mine.get('claim')}」；"
                     f"文章原文「{mine.get('evidence')}」；理由：{mine.get('note')}；來源 {mine.get('source_id')}："
                     f"{mine.get('source_quote')}\n  {d['other']} 的判定：{other_text}")
    return ("你是第三位事實查核員，負責仲裁。兩位查核員各自查了同一篇文章（article.md，來源在 sources.json），"
            "下面每一條是只有一位判成錯誤或無來源、另一位判為正確（或沒列出）的說法。\n"
            "逐條回到 sources.json 的原始網址查證（用 WebFetch），不要相信任何一方的轉述，也不要因為有人判錯就傾向判錯。\n"
            "status：ok＝來源原文支持；wrong＝來源說的不一樣；unsourced＝沒附來源或來源沒有這件事；unverifiable＝來源打不開；"
            "analysis＝頻道自己的換算、推論或觀點，而且文中明確寫成換算／推論／判斷、你驗算過（寫成事實的推論算 unsourced）。"
            "rulings 每條 item 照抄、note 寫理由、source_quote 寫來源原文。\n\n" + "\n".join(lines)
            + "\n\n只讀目前資料夾的 article.md 與 sources.json，不要修改任何檔案。用繁體中文寫。完成後用結構化輸出回傳。")


def upheld(rulings: dict[str, Any] | None, disputes: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """(dispute keys the arbiter upheld as errors, dispute keys it did not answer)."""
    answers = {str(r.get("item")): r for r in (rulings or {}).get("rulings") or []}
    keys = [d["item"] for d in disputes]
    return [k for k in keys if answers.get(k, {}).get("status") in ERROR], [k for k in keys if k not in answers]
