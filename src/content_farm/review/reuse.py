"""Re-review only what needs it (cf-cost-fix, Leon 2026-10-22: "一輪不過時，所有席次全部重跑，即使只有一位不過").

After a failed round and a rework, round N+1 runs:

* the seats that did not pass last round (a writer below the bar, a viewer who left early), and
* the seats whose own findings point at sentences the rework changed or the fix list's linked scope names;

every other seat keeps its round N answer (``carried_from``). Fact-checkers are not carried whole: they re-check only
the changed sentences (★ — the delta view of ``review.delta``) and their earlier claims about untouched sentences are
kept, so a one-line fix no longer sends two checkers back through every source.

Nothing is carried when the change is large (more than ``MAX_CHANGED_SHARE`` of the sentences, or a chapter's
argument changed): a big rewrite is a new thing to judge. The holdout viewer is never carried; it sits only in the last
round. A carried answer is a sampled opinion kept across an edit — the scorecard says which seats were carried and why
the others re-ran, so the trade-off is visible.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from content_farm.review.article_diff import ArticleSentence, deck_narration, normalize, sentences_for_quote, split_article
from content_farm.review.config import ReviewConfig, Stage
from content_farm.review.sentences import Sentence, position_share, script_sentences
from content_farm.review.snapshot import SNAPSHOT_DIR

CARRY_STAGES = ("article", "script_structure", "script_facts", "shorts_script")
MAX_CHANGED_SHARE = 0.25
FACT_BAD = ("wrong", "unsourced")


@dataclass(frozen=True)
class Prior:
    rid: str
    output: dict[str, Any]
    seat: dict[str, Any]             # the previous scorecard's seat entry (model, effort, cost …)


@dataclass(frozen=True)
class CarryPlan:
    previous: str                                   # label of the round the answers come from
    carried: dict[str, Prior]                       # rid → answer kept
    delta: frozenset[str] | None                    # ★ ids fact-checkers review; None = they review everything
    prior_fact: dict[str, Prior] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)     # rid → why it re-runs / is carried
    keep_ids: frozenset[str] = frozenset()          # ids that exist now and were not changed (fact claims kept)

    def to_json(self) -> dict[str, Any]:
        return {"previous": self.previous, "carried": sorted(self.carried),
                "delta": sorted(self.delta) if self.delta is not None else None, "reasons": self.reasons}


def _norm(sentences: list[ArticleSentence]) -> set[str]:
    return {normalize(s.text) for s in sentences}


def changed_ids(old: list[ArticleSentence], new: list[ArticleSentence]) -> frozenset[str]:
    """Ids in ``new`` whose wording is not in ``old`` (edited or added); matched by text, not id."""
    before = _norm(old)
    return frozenset(s.id for s in new if normalize(s.text) not in before)


def _read(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.is_file() else None


def versions(run_dir: Path, previous_dir: Path, stage_name: str) -> tuple[list[ArticleSentence], list[ArticleSentence]] | None:
    """(sentences judged last round, sentences now); None when last round kept no snapshot of them."""
    snap = previous_dir / SNAPSHOT_DIR
    if stage_name == "article":
        old, new = _read(snap / "article.md"), _read(run_dir / "article.md")
        return (split_article(old), split_article(new)) if old is not None and new is not None else None
    if stage_name == "shorts_script":
        old, new = _read(snap / "script.json"), _read(run_dir / "script.json")
        if old is None or new is None:
            return None
        return ([ArticleSentence(s.id, s.text) for s in script_sentences(json.loads(old))],
                [ArticleSentence(s.id, s.text) for s in script_sentences(json.loads(new))])
    old, new = _read(snap / "deck.json"), _read(run_dir / "deck.json")
    if old is None or new is None:
        return None
    return deck_narration(json.loads(old)), deck_narration(json.loads(new))


def refs_of(output: dict[str, Any]) -> set[str]:
    """Every sentence id a seat's answer points at."""
    ids: set[str] = set()
    for item in [*(output.get("issues") or []), *(output.get("top_fixes") or [])]:
        ids |= {str(i) for i in (item.get("ref") or {}).get("sentence_ids") or []}
    for claim in output.get("claims") or []:
        ids |= {str(i) for i in claim.get("sentence_ids") or []}
    if output.get("left_at_sentence"):
        ids.add(str(output["left_at_sentence"]))
    return ids


def passed_last_round(kind: str, role: str, output: dict[str, Any], stage: Stage, old: list[Sentence]) -> bool:
    """Did this seat's own answer clear its bar? (a viewer who left before the threshold, or a writer below the
    minimum, did not.) Seats with no individual bar (director, designer …) count as passed."""
    threshold = stage.threshold
    if kind == "viewer":
        floor = threshold.leave_median_pct
        return floor is None or position_share(old, output.get("left_at_sentence")) >= floor
    if role.startswith("writer") and threshold.writer_min is not None:
        return float(output.get("score", 0)) >= threshold.writer_min
    return True


def _sentences(stage_name: str, items: list[ArticleSentence]) -> list[Sentence]:
    return [Sentence(s.id, "", "", s.text, True) for s in items]


def plan_carry(run_dir: Path, *, stage_name: str, stage: Stage, config: ReviewConfig, members: list[Any],
               previous_dir: Path, fixes: dict[str, Any] | None) -> CarryPlan | None:
    """What round N+1 keeps from round N. None = run everything (round 1, big change, nothing kept)."""
    if stage_name not in CARRY_STAGES:
        return None
    card = json.loads((previous_dir / "scorecard.json").read_text(encoding="utf-8"))
    if card.get("holdout_only") or (fixes or {}).get("chapters_to_rereview"):
        return None
    seen = versions(run_dir, previous_dir, stage_name)
    if seen is None:
        return None
    old, new = seen
    changed = changed_ids(old, new)
    scope = {str(i) for step in (fixes or {}).get("steps", {}).values() for i in step.get("sentence_ids", [])}
    touched = set(changed) | scope
    small = len(changed) <= MAX_CHANGED_SHARE * max(len(new), 1)
    old_sentences = _sentences(stage_name, old)
    by_rid = {s["rid"]: s for s in card.get("seats", []) if s.get("ok") and not s.get("holdout")}
    carried: dict[str, Prior] = {}
    prior_fact: dict[str, Prior] = {}
    reasons: dict[str, str] = {}
    for member in members:
        prior = _prior(previous_dir, by_rid.get(member.rid), member)
        if prior is None or member.holdout:
            reasons[member.rid] = "新席次" if prior is None else "holdout"
            continue
        if member.kind == "fact":
            prior_fact[member.rid] = prior
            reasons[member.rid] = "查核員：只重查改過的句子"
            continue
        if not small:
            reasons[member.rid] = f"改動 {len(changed)}/{len(new)} 句超過 {MAX_CHANGED_SHARE:.0%}，整批重評"
        elif not passed_last_round(member.kind, member.role, prior.output, stage, old_sentences):
            reasons[member.rid] = "上一輪沒過自己的門檻"
        elif refs_of(prior.output) & touched:
            reasons[member.rid] = "它指出的句子被改了或在連動範圍內"
        else:
            carried[member.rid] = prior
            reasons[member.rid] = "沿用上一輪（過了門檻，指出的句子沒被動到）"
    if not carried and not prior_fact:
        return None
    if not prior_fact and all(m.rid in carried for m in members):
        return None           # nothing would re-run: the verdict could only repeat itself
    keep = frozenset(s.id for s in new if s.id not in changed)
    return CarryPlan(previous_dir.name, carried, frozenset(changed) if prior_fact else None, prior_fact, reasons, keep)


def _prior(previous_dir: Path, seat: dict[str, Any] | None, member: Any) -> Prior | None:
    """The previous answer of this seat, if it is the same seat (role, model, effort) and has a valid output."""
    if seat is None or seat.get("role") != member.role:
        return None
    if (seat.get("model"), seat.get("effort")) != (member.model, member.effort):
        return None
    path = previous_dir / "results" / f"{member.rid}.json"
    if not path.is_file():
        return None
    body = json.loads(path.read_text(encoding="utf-8"))
    if body.get("_failed"):
        return None
    return Prior(member.rid, {k: v for k, v in body.items() if k != "_usage"}, seat)


def claim_ids(item: dict[str, Any]) -> list[str]:
    return [str(i) for i in item.get("sentence_ids") or (item.get("ref") or {}).get("sentence_ids") or []]


def merge_fact(prior: dict[str, Any], fresh: dict[str, Any], plan: CarryPlan, *, new_article: list[ArticleSentence] | None
               ) -> dict[str, Any]:
    """A fact-checker's answer for this round: its new claims about the changed (★) sentences plus the earlier claims
    about sentences that are still there, unchanged. For an article (no sentence ids on claims) a claim is matched by
    the quote it carries."""
    def keep(item: dict[str, Any]) -> bool:
        ids = claim_ids(item)
        if ids:
            return all(i in plan.keep_ids for i in ids)
        if new_article is None:
            return False
        quote = str(item.get("evidence") or item.get("claim") or "")
        hits = sentences_for_quote(quote, new_article)
        return bool(hits) and all(h in plan.keep_ids for h in hits)

    claims = [c for c in prior.get("claims", []) if keep(c)] + list(fresh.get("claims", []))
    issues = [i for i in prior.get("issues", []) if keep(i)] + list(fresh.get("issues", []))
    return {**fresh, "claims": claims, "issues": issues}
