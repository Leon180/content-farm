"""Route a failed round's verified issues back to the steps that caused them.

Each fix carries its linked scope (Leon 2026-10-18 fix-scope rules): every other place the same
number / term appears (sentences, titles, thumbnail text, description), and the whole chapter
when the fix changes a chapter's argument. A plan whose fixes have no scope is refused.

How this meets feat/incremental-render (merged 1352879): the fix list here is the *pre-edit*
scope (what the producer must touch). After the producer edits deck.json, their pieces take over
by themselves: stable ``slide.sentence_ids`` keep unchanged sentences' audio/clips, the voice step
re-voices only changed sentences ±2 within a scene, media/mascot caches redraw only changed scenes,
and ``scripts/fix_scope.py`` (``explainer.fix_scope.analyse`` against ``review/deck.approved.json``,
which panel approval also writes) lists every leftover old wording. ``scope_provider`` /
``range_provider`` look for ``issue_scope`` / ``rerender_ranges`` in ``content_farm.explainer.fix_scope``
and fall back to the simple versions here (that module has neither yet).
"""

from __future__ import annotations

import importlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from content_farm.review.sentences import Sentence

PIPELINE_ORDER = ("topic", "article", "deck", "thumbnail_spec", "voice", "illustrate", "media", "assembly",
                  "mascot", "mix")
COMMON_TERM_HITS = 6          # a linked term found in more sentences than this does not link
MAX_AFFECTED_SLIDES = 3       # extra slides a claim_change issue may name (ref: ``affected_slides``)
_TOKENS = re.compile(r"\d[\d,.]*\s*[%倍萬億年月週片顆]?|[A-Za-z][A-Za-z0-9\-]{1,}|「([^」]{2,12})」")


class PlanError(ValueError):
    """A rework plan that would not be safe to act on."""


@dataclass(frozen=True)
class Scope:
    sentence_ids: tuple[str, ...]
    titles: tuple[str, ...] = ()
    thumbnail: bool = False
    description: bool = False
    chapters: tuple[str, ...] = ()           # sections to send back to review as a whole
    terms: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {"sentence_ids": list(self.sentence_ids), "titles": list(self.titles), "thumbnail": self.thumbnail,
                "description": self.description, "chapters": list(self.chapters), "terms": list(self.terms)}


@dataclass
class Texts:
    sentences: list[Sentence]
    titles: dict[str, str] = field(default_factory=dict)
    thumbnail: str = ""
    description: str = ""


def terms_of(text: str) -> list[str]:
    found = []
    for match in _TOKENS.finditer(text or ""):
        term = (match.group(1) or match.group(0)).strip()
        if len(term) >= 2 and term not in found:
            found.append(term)
    return found


def simple_scope(issue: dict[str, Any], texts: Texts) -> Scope:
    """Fallback linkage: numbers, Latin terms and quoted words of the evidence, found everywhere."""
    ref = issue.get("ref") or {}
    named = [str(i) for i in ref.get("sentence_ids") or []]
    terms = terms_of(issue.get("evidence", ""))
    # a term found in more than COMMON_TERM_HITS sentences is a common word, not a linked claim (it would drag in half the script)
    hits = {t: sum(t in s.text for s in texts.sentences) for t in terms}
    linking = [t for t in terms if hits[t] <= COMMON_TERM_HITS]
    linked = [s.id for s in texts.sentences if s.id in named or any(t in s.text for t in linking)]
    titles = tuple(k for k, v in texts.titles.items() if any(t in v for t in terms))
    chapters: tuple[str, ...] = ()
    if issue.get("claim_change"):
        # the chapter goes back to review as a whole, but only the slides the issue names must be rewritten
        # (reject-list-analysis: whole-chapter expansion added 118 sentences, 8 of them were changed)
        chapters = tuple(sorted({s.section for s in texts.sentences if s.id in named}))
        slides = {s.slide_id for s in texts.sentences if s.id in named} | set(
            str(x) for x in (issue.get("affected_slides") or [])[:MAX_AFFECTED_SLIDES])
        linked += [s.id for s in texts.sentences if s.slide_id in slides and s.id not in linked]
    return Scope(tuple(dict.fromkeys(linked)), titles, any(t in texts.thumbnail for t in terms),
                 any(t in texts.description for t in terms), chapters, tuple(terms))


def simple_ranges(sentence_ids: list[str], sentences: list[Sentence]) -> dict[str, list[str]]:
    """Fallback for "sentence ids → what to re-render": the slides (scenes) holding them."""
    slides: dict[str, list[str]] = {}
    for sentence in sentences:
        if sentence.id in sentence_ids:
            slides.setdefault(sentence.slide_id, []).append(sentence.id)
    return {"scenes": sorted(slides), "sentences": sorted(sentence_ids)}


def _provider(name: str, fallback: Callable) -> Callable:
    try:
        module = importlib.import_module("content_farm.explainer.fix_scope")
    except ImportError:
        return fallback
    return getattr(module, name, fallback)


def scope_provider() -> Callable[[dict[str, Any], Texts], Scope]:
    return _provider("issue_scope", simple_scope)


def range_provider() -> Callable[[list[str], list[Sentence]], dict[str, list[str]]]:
    return _provider("rerender_ranges", simple_ranges)


def unfrozen(step: str, frozen: frozenset[str]) -> str:
    """``step``, or the first later pipeline step that is not frozen."""
    if step not in frozen:
        return step
    later = [s for s in PIPELINE_ORDER[PIPELINE_ORDER.index(step) + 1:] if s not in frozen]
    if not later:
        raise PlanError(f"{step} is frozen and every later step is frozen too")
    return later[0]


def plan(issues: list[dict[str, Any]], texts: Texts, *, stage: str, round_no: int,
         default_step: str, frozen: frozenset[str] = frozenset()) -> dict[str, Any]:
    scope_of, ranges_of = scope_provider(), range_provider()
    steps: dict[str, dict[str, Any]] = {}
    for issue in issues:
        caused = issue.get("caused_by") or default_step
        if caused not in PIPELINE_ORDER:
            caused = default_step
        step = unfrozen(caused, frozen)
        scope = scope_of(issue, texts)
        slot = steps.setdefault(step, {"fixes": [], "sentence_ids": [], "items": []})
        fix = {**{k: issue.get(k) for k in ("ref", "category", "severity", "problem", "fix", "evidence", "who")},
               "scope": scope.to_json()}
        if step != caused:
            fix["rerouted_from"] = caused
        slot["fixes"].append(fix)
        slot["sentence_ids"] = sorted(set(slot["sentence_ids"]) | set(scope.sentence_ids))
        item = (issue.get("ref") or {}).get("item")
        if item and item not in slot["items"]:
            slot["items"].append(item)
    for slot in steps.values():
        slot["rerender"] = ranges_of(slot["sentence_ids"], texts.sentences)
    restart = min(steps, key=PIPELINE_ORDER.index) if steps else unfrozen(default_step, frozen)
    result = {"stage": stage, "round": round_no, "restart": restart, "frozen": sorted(frozen),
              "downstream": list(PIPELINE_ORDER[PIPELINE_ORDER.index(restart):]), "steps": steps,
              "chapters_to_rereview": sorted({c for s in steps.values() for f in s["fixes"] for c in f["scope"]["chapters"]})}
    check(result)
    return result


def check(rework: dict[str, Any]) -> None:
    """Refuse a plan that could not be acted on safely."""
    for step, slot in rework["steps"].items():
        if not slot["fixes"]:
            raise PlanError(f"{step}: no fixes")
        for fix in slot["fixes"]:
            scope = fix.get("scope")
            if not isinstance(scope, dict) or "sentence_ids" not in scope:
                raise PlanError(f"{step}: fix {fix.get('problem', '')[:40]!r} has no linked scope")


def write(run_dir: Path, gate: str, rework: dict[str, Any]) -> Path:
    check(rework)
    path = run_dir / "review" / f"{gate}.fixes.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rework, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
