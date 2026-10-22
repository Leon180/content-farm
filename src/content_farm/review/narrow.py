"""Narrow a failed round's issue list before it becomes a fix list (cf-pipeline-speed, item 2).

Measured on 九尾狐 (docs/pipeline-speed/reject-list-analysis.md): the fix list named 79–95% of the sentences while
35–54% were actually changed. This module is deterministic (no LLM): it ranks the issues, keeps at most
``per_seat`` per reviewer seat, and stops adding issues once the union of the sentences they name passes
``hard`` of the script. Issues that do not name sentences (titles, media, video-time) pass through, and so do
``ref.scope == "global"`` issues that say why (``why_global``). What is cut goes to ``deferred`` — the next round's
reviewers will name it again if it still matters.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from content_farm.review.sentences import Sentence

PER_SEAT = 5            # issues kept per reviewer seat (replay: 35–44% named instead of 60–68%)
WARN_SHARE = 0.25       # above this the scorecard flags the list
HARD_SHARE = 0.30       # above this issues are cut
_SEVERITY = {"high": 0, "med": 1, "low": 2}


def _ids(issue: dict[str, Any]) -> list[str]:
    return [str(i) for i in (issue.get("ref") or {}).get("sentence_ids") or []]


def is_global(issue: dict[str, Any]) -> bool:
    ref = issue.get("ref") or {}
    return ref.get("scope") == "global" and bool(str(ref.get("why_global") or "").strip())


def _votes(issue: dict[str, Any], issues: Sequence[dict[str, Any]]) -> int:
    mine = set(_ids(issue))
    return len({str(o.get("who")) for o in issues if mine & set(_ids(o))})


def _is_fact(issue: dict[str, Any]) -> bool:
    return issue.get("category") == "fact" or str(issue.get("who", "")).startswith("fact_checker")


def narrow(issues: list[dict[str, Any]], sentences: Sequence[Sentence], *, per_seat: int = PER_SEAT,
           hard: float = HARD_SHARE) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """(kept, deferred, stats). Order of ``kept`` is the input order."""
    total = len(sentences)
    scoped = [i for i in issues if _ids(i) and not is_global(i)]
    free = [i for i in issues if i not in scoped]
    before = {x for i in issues for x in _ids(i)}
    if not total or not scoped:
        return list(issues), [], _stats(total, before, before, issues, issues, [])

    def rank(issue: dict[str, Any]) -> tuple:
        return (not _is_fact(issue), _SEVERITY.get(str(issue.get("severity")), 3), -_votes(issue, scoped),
                len(_ids(issue)))

    by_seat: dict[str, list[dict[str, Any]]] = {}
    for issue in sorted(scoped, key=rank):
        by_seat.setdefault(str(issue.get("who")), []).append(issue)
    candidates = [i for seat in by_seat.values() for i in seat[:per_seat]]
    cut_by_seat = [i for seat in by_seat.values() for i in seat[per_seat:]]
    limit = int(hard * total)
    named: set[str] = {x for i in free for x in _ids(i)}
    kept_scoped, over = [], []
    for issue in sorted(candidates, key=rank):
        new = named | set(_ids(issue))
        if kept_scoped and len(new) > limit:
            over.append(issue)
            continue
        named = new
        kept_scoped.append(issue)
    keep = {id(i) for i in [*free, *kept_scoped]}
    kept = [i for i in issues if id(i) in keep]
    deferred = [i for i in issues if id(i) not in keep]
    return kept, deferred, _stats(total, before, named, issues, kept, deferred)


def _stats(total: int, before: set[str], after: set[str], issues: Sequence[Any], kept: Sequence[Any],
           deferred: Sequence[Any]) -> dict[str, Any]:
    share = round(len(after) / total, 3) if total else 0.0
    return {"sentences": total, "issues_before": len(issues), "issues_after": len(kept), "deferred": len(deferred),
            "named_before": len(before), "named_after": len(after),
            "named_share_before": round(len(before) / total, 3) if total else 0.0, "named_share_after": share,
            "over_warn": share > WARN_SHARE}


def sentences_at(times: Sequence[Sequence[Any]], t: float, radius: int = 1) -> list[str]:
    """Sentence ids around second ``t``: ``times`` rows are ``[id, start, end]`` in script order."""
    if not times:
        return []
    index = next((n for n, row in enumerate(times) if float(row[1]) <= t < float(row[2])), None)
    if index is None:
        index = len(times) - 1 if t >= float(times[-1][2]) else 0
    return [str(row[0]) for row in times[max(index - radius, 0): index + radius + 1]]


def with_sentences_from_time(issue: dict[str, Any], times: Sequence[Sequence[Any]], seconds: float | None,
                             radius: int = 1) -> dict[str, Any]:
    """A video / audio issue gets the sentences at its ``ref.t`` (viewers' own ``sentence_ids`` are discarded)."""
    ref = issue.get("ref") or {}
    if ref.get("target") not in ("video", "audio") or seconds is None or not times:
        return issue
    return {**issue, "ref": {**ref, "sentence_ids": sentences_at(times, seconds, radius)}}
