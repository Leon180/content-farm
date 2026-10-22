"""Rework only touches what the fix list names (cf-cost-fix, Leon 2026-10-22: "不准整份重寫").

A producer agent that is sent back with a fix list answers in a diff: the sentence ids / titles to change plus the
reason. Everything the list does not name — other sentences, other slides, other titles — is compared by the
program against the file as it was before; a change there means the rewrite is refused and the file restored.

The one exception is a *structure* rewrite: when a fix names no sentence at all (the script as a whole failed, e.g. a
leave-point or pacing complaint), the plan is **open** and the agent may restructure, but its receipt must say why
(``rewrite_reason``). Open or not, the reason is logged with the scorecard so a big rewrite is never silent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content_farm.review.article_diff import normalize
from content_farm.review.sentences import deck_sentences

TOP_LEVEL_FREE = ("sections",)      # structural keys are judged slide by slide below


@dataclass(frozen=True)
class Named:
    """What the fix list gives the agent leave to change."""
    sentence_ids: frozenset[str]
    titles: frozenset[str]
    thumbnail: bool
    description: bool
    open: bool                       # a fix that names no sentence: structure-level rewrite, reason required
    slides: frozenset[str] = frozenset()   # slides a media compliance fix names: that slide's media / card is free

    def to_json(self) -> dict[str, Any]:
        return {"sentence_ids": sorted(self.sentence_ids), "titles": sorted(self.titles),
                "thumbnail": self.thumbnail, "description": self.description, "open": self.open,
                "slides": sorted(self.slides)}


def named_in(plan: dict[str, Any], step: str) -> Named:
    """The ids / titles the fixes routed to ``step`` name (their ``ref`` plus the linked ``scope``)."""
    ids: set[str] = set()
    titles: set[str] = set()
    slides: set[str] = set()
    thumbnail = description = is_open = False
    fixes = (plan.get("steps", {}).get(step) or {}).get("fixes", [])
    for fix in fixes:
        ref, scope = fix.get("ref") or {}, fix.get("scope") or {}
        if ref.get("target") == "media" and ref.get("item") and fix.get("category") == "compliance":
            slides.add(str(ref["item"]))      # credits / licence gap on a live slide: its card and the source list
            description = True
        named = {str(i) for i in [*(ref.get("sentence_ids") or []), *(scope.get("sentence_ids") or [])]}
        ids |= named
        titles |= {str(t) for t in scope.get("titles") or []}
        if ref.get("target") == "title" and ref.get("item"):
            titles.add(str(ref["item"]))
        thumbnail |= bool(scope.get("thumbnail")) or ref.get("target") == "thumbnail"
        description |= bool(scope.get("description")) or ref.get("target") == "description"
        if not named and ref.get("target") in ("script", None) and not ref.get("item"):
            is_open = True
    return Named(frozenset(ids), frozenset(titles), thumbnail, description, is_open, frozenset(slides))


def _slides(deck: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(s.get("id")): s for sec in deck.get("sections", []) for s in sec.get("slides", [])}


def _by_slide(deck: dict[str, Any]) -> dict[str, list[tuple[str, str]]]:
    out: dict[str, list[tuple[str, str]]] = {}
    for s in deck_sentences(deck):
        out.setdefault(s.slide_id, []).append((s.id, s.text))
    return out


def deck_problems(before: dict[str, Any], after: dict[str, Any], named: Named) -> list[str]:
    """Why ``after`` is not a scoped edit of ``before`` ([] = it is). Open plans are not scoped (see module doc)."""
    if named.open:
        return []
    old_slides, new_slides = _slides(before), _slides(after)
    old_by, new_by = _by_slide(before), _by_slide(after)
    touched = {sid for sid, sents in old_by.items() if any(i in named.sentence_ids for i, _ in sents)}
    problems = []
    for sid in old_slides.keys() - new_slides.keys():
        if sid not in touched:
            problems.append(f"投影片 {sid} 沒有被點名，不能刪除")
    for sid in new_slides.keys() - old_slides.keys():
        problems.append(f"新增投影片 {sid}（修改清單沒有要求；結構大改要先讓清單指到整個腳本）")
    for sid in old_slides.keys() & new_slides.keys():
        if sid in named.slides:
            continue
        if sid in touched:
            keep = [(i, t) for i, t in old_by.get(sid, []) if i not in named.sentence_ids]
            after_texts = [normalize(t) for _, t in new_by.get(sid, [])]
            problems += [f"{i} 沒有被點名，不能改：「{t[:30]}」" for i, t in keep if normalize(t) not in after_texts]
        elif old_slides[sid] != new_slides[sid]:
            fields = sorted(k for k in old_slides[sid].keys() | new_slides[sid].keys()
                            if old_slides[sid].get(k) != new_slides[sid].get(k))
            problems.append(f"投影片 {sid} 沒有被點名，但 {'、'.join(fields)} 被改了")
    if before.get("title") != after.get("title"):
        problems.append("deck 標題沒有被點名，不能改")
    if before.get("description") != after.get("description") and not named.description:
        problems.append("說明欄沒有被點名，不能改")
    return problems


def titles_problems(before: dict[str, Any] | list[Any], after: dict[str, Any] | list[Any], named: Named) -> list[str]:
    """titles.json: a title nobody flagged must keep its text; flagged ones may change or go."""
    def texts(data: dict[str, Any] | list[Any]) -> dict[str, str]:
        items = data["titles"] if isinstance(data, dict) else data
        return {str(t["id"]): str(t["text"]) for t in items}

    if named.open:
        return []
    old, new = texts(before), texts(after)
    problems = [f"標題 {i} 沒有被點名，不能改：「{t[:30]}」" for i, t in old.items()
                if i not in named.titles and new.get(i) != t]
    return problems


@dataclass(frozen=True)
class ScopedGuard:
    """The scoped-rework check for one file (deck.json or titles.json), same shape as ``_DeleteOnly``."""
    path: Path
    before: str
    named: Named
    kind: str                          # "deck" | "titles"

    def check(self) -> list[str]:
        try:
            after = json.loads(self.path.read_text(encoding="utf-8")) if self.path.is_file() else {}
        except json.JSONDecodeError as exc:
            return [f"{self.path.name} 不是合法 JSON：{exc}"]
        before = json.loads(self.before)
        return (deck_problems if self.kind == "deck" else titles_problems)(before, after, self.named)

    def restore(self) -> None:
        self.path.write_text(self.before, encoding="utf-8")


def scoped_guard(run_dir: Path, step: str, plan: dict[str, Any]) -> ScopedGuard | None:
    """The guard for a rework of ``step`` (deck / thumbnail_spec); None for steps with nothing to compare."""
    if step == "deck":
        path, kind = run_dir / "deck.json", "deck"
    elif step == "thumbnail_spec":
        path, kind = run_dir / "titles.json", "titles"
    else:
        return None
    if not path.is_file():
        return None
    return ScopedGuard(path, path.read_text(encoding="utf-8"), named_in(plan, step), kind)
