"""The automatic fix never stops a run (Leon 2026-10-24, from the technews run2 stop at gate_article).

Under ``fact_on_fail: auto_fix_then_pass`` (and the script review's ``script_revise_once``) a failed gate hands its
fix list to a producer once. If that producer's rewrite is refused (the delete-or-edit-only guard, a channel rule), or
the agent fails, or it changes nothing, the run used to stop. Now the fallback is, in order:

1. restore the file to what it was before the rewrite;
2. delete the flagged sentences outright (only where a delete-only guard names them: article / script facts);
3. if even that cannot be done (nothing flagged, a slide would be left empty, no such guard), record it and go on.

Every outcome is written to ``review/auto_fix.jsonl``; nothing here raises or returns a failure.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from content_farm.review import score_ledger
from content_farm.review.article_diff import _SENTENCE_END, deck_narration, split_article


def is_auto_fix(run_dir: Path, gate: str | None) -> bool:
    """Is the rework being run for ``gate`` the one automatic fix?"""
    plan = run_dir / "review" / f"{gate}.fixes.json" if gate else None
    if plan is None or not plan.is_file():
        return False
    try:
        return bool(json.loads(plan.read_text(encoding="utf-8")).get("auto_fact_fix"))
    except (OSError, json.JSONDecodeError):
        return False


def delete_from_article(markdown: str, flagged: frozenset[str] | set[str]) -> tuple[str, list[str]]:
    """The article without the flagged sentences (ids as ``split_article``), and the ids actually removed."""
    removed: list[str] = []
    lines: list[str] = []
    paragraph = 0
    for line in markdown.splitlines():
        if not line.strip():
            lines.append("")
            continue
        paragraph += 1
        parts = [p.strip() for p in _SENTENCE_END.split(line.strip()) if p.strip()]
        kept = []
        for n, part in enumerate(parts, 1):
            if f"p{paragraph}.{n}" in flagged:
                removed.append(f"p{paragraph}.{n}")
            else:
                kept.append(part)
        if kept:                    # ids stay the ORIGINAL numbering (the flagged ids were made against it)
            lines.append("".join(kept))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip("\n") + "\n", removed


def delete_from_deck(deck: dict[str, Any], flagged: frozenset[str] | set[str]) -> tuple[dict[str, Any], list[str], list[str]]:
    """A copy of the deck with the flagged narration sentences removed; (deck, removed ids, kept-because-last ids).
    A slide's last sentence is never removed (an empty narration is not a slide)."""
    from content_farm.review.sentences import deck_sentences

    by_slide: dict[str, list[Any]] = {}
    for sentence in deck_sentences(deck):
        by_slide.setdefault(sentence.slide_id, []).append(sentence)
    removed: list[str] = []
    protected: list[str] = []
    sections = []
    for section in deck.get("sections", []):
        slides = []
        for slide in section.get("slides", []):
            sentences = by_slide.get(str(slide.get("id")), [])
            drop = [s for s in sentences if s.id in flagged]
            if drop and len(drop) == len(sentences):
                protected += [s.id for s in drop]
                drop = []
            if drop:
                keep = [s for s in sentences if s.id not in flagged]
                slide = {**slide, "narration": "".join(s.text for s in keep)}
                if isinstance(slide.get("sentence_ids"), list) and len(slide["sentence_ids"]) == len(sentences):
                    slide["sentence_ids"] = [s.id for s in keep]
                removed += [s.id for s in drop]
            slides.append(slide)
        sections.append({**section, "slides": slides})
    return {**deck, "sections": sections}, removed, protected


def apply(run_dir: Path, *, gate: str, stage: str, step_name: str, failure: str, guard: Any | None,
          log: Any = print) -> None:
    """Restore, delete the flagged sentences if a guard names them, record, and let the run go on."""
    detail: dict[str, Any] = {"failure": failure[:300], "step": step_name}
    outcome = "fallback_recorded"
    if guard is not None:
        guard.restore()
        try:
            if guard.deck:
                deck, removed, protected = delete_from_deck(json.loads(guard.before), guard.flagged)
                if removed:
                    guard.path.write_text(json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8")
                detail["kept_last_sentence"] = protected
            else:
                text, removed = delete_from_article(guard.before, guard.flagged)
                if removed:
                    guard.path.write_text(text, encoding="utf-8")
            detail["removed"] = removed
            outcome = "fallback_deleted" if removed else "fallback_nothing_to_delete"
        except (OSError, ValueError) as exc:        # a broken file is restored above; record and go on
            detail["delete_error"] = str(exc)[:200]
    score_ledger.log_auto_fix(run_dir, gate, stage, event=outcome, **detail)
    log(f"⚠ {step_name}: 自動修失敗（{failure[:80]}）→ {outcome.removeprefix('fallback_')}，放行不停")


__all__ = ["apply", "delete_from_article", "delete_from_deck", "deck_narration", "is_auto_fix", "split_article"]
