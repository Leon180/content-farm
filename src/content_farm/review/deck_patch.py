"""Apply a sentence patch ``{sentence_id: new text, "deletes": [ids]}`` to ``deck.json``.

A rework answers in a diff (cf-cost-fix), so the program, not the agent, writes the file: the agent only says
which sentence becomes what. Everything not named stays byte-for-byte; the deck keeps its slide order, ids and
every other field. ``scripts/apply_deck_patch.py`` is the whitelisted command-line entry (it re-runs
``deck_to_script --strict`` after applying).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from content_farm.retention.timing import split_sentences

DELETES = "deletes"


class PatchError(ValueError):
    """A patch that cannot be applied as written."""


@dataclass(frozen=True)
class PatchResult:
    deck: dict[str, Any]
    changed: tuple[str, ...] = ()
    deleted: tuple[str, ...] = ()
    problems: tuple[str, ...] = field(default=())


def parse_patch(raw: Any) -> tuple[dict[str, str], list[str]]:
    """(replacements, deletes) from the patch JSON; raises PatchError on a malformed patch."""
    if not isinstance(raw, dict):
        raise PatchError("patch must be a JSON object {sentence_id: text, ..., \"deletes\": [ids]}")
    deletes = raw.get(DELETES, [])
    if not isinstance(deletes, list) or not all(isinstance(i, str) for i in deletes):
        raise PatchError(f"{DELETES} must be a list of sentence ids")
    replace = {k: v for k, v in raw.items() if k != DELETES}
    bad = [k for k, v in replace.items() if not isinstance(v, str) or not v.strip()]
    if bad:
        raise PatchError(f"new text must be a non-empty string: {', '.join(bad)} (use \"{DELETES}\" to remove a sentence)")
    both = sorted(set(replace) & set(deletes))
    if both:
        raise PatchError(f"ids both replaced and deleted: {', '.join(both)}")
    return replace, list(dict.fromkeys(deletes))


def _spans(narration: str, sentences: list[str]) -> list[tuple[int, int]] | None:
    """(start, end) of each sentence inside the narration, or None if they cannot be located in order."""
    spans, cursor = [], 0
    for sentence in sentences:
        start = narration.find(sentence, cursor)
        if start < 0:
            return None
        spans.append((start, start + len(sentence)))
        cursor = start + len(sentence)
    return spans


def _patch_slide(slide: dict[str, Any], replace: dict[str, str], deletes: set[str]) -> dict[str, Any]:
    narration = str(slide.get("narration", ""))
    parts = split_sentences(narration)
    ids = slide.get("sentence_ids")
    if not isinstance(ids, list) or len(ids) != len(parts):
        raise PatchError(f"slide {slide.get('id')}: sentence_ids do not line up with the narration — "
                         "run deck_to_script.py once so every sentence has an id, then patch")
    spans = _spans(narration, parts)
    if spans is None:
        raise PatchError(f"slide {slide.get('id')}: cannot locate its sentences inside the narration")
    text, kept_ids = narration, list(ids)
    for index in range(len(parts) - 1, -1, -1):          # back to front so earlier spans stay valid
        sid = str(ids[index])
        start, end = spans[index]
        if sid in deletes:
            while end < len(text) and text[end].isspace():
                end += 1
            text = text[:start] + text[end:]
            del kept_ids[index]
        elif sid in replace:
            text = text[:start] + replace[sid].strip() + text[end:]
    return {**slide, "narration": text.strip(), "sentence_ids": kept_ids}


def apply_patch(deck: dict[str, Any], replace: dict[str, str], deletes: list[str]) -> PatchResult:
    """A new deck with the patch applied (the input is not touched). Unknown ids are an error, not a skip."""
    wanted = set(replace) | set(deletes)
    known = {str(i) for sec in deck.get("sections", []) for sl in sec.get("slides", []) for i in sl.get("sentence_ids") or []}
    unknown = sorted(wanted - known)
    if unknown:
        raise PatchError(f"unknown sentence id(s): {', '.join(unknown)}")
    remove = set(deletes)
    sections = []
    for section in deck.get("sections", []):
        slides = []
        for slide in section.get("slides", []):
            own = {str(i) for i in slide.get("sentence_ids") or []}
            slides.append(_patch_slide(slide, replace, remove) if own & wanted else slide)
        sections.append({**section, "slides": slides})
    return PatchResult({**deck, "sections": sections}, tuple(sorted(replace)), tuple(sorted(deletes)))


def apply_file(deck_text: str, patch_text: str) -> PatchResult:
    try:
        deck, raw = json.loads(deck_text), json.loads(patch_text)
    except json.JSONDecodeError as exc:
        raise PatchError(f"not valid JSON: {exc}") from exc
    replace, deletes = parse_patch(raw)
    return apply_patch(deck, replace, deletes)
