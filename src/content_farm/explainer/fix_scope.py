"""What an edit to deck.json puts back in the queue (修改範圍連動).

Given the deck before and after an edit, :func:`analyse` lists:

* **sentences** changed / added / removed (by stable sentence id, explainer.sentence_ids);
* **terms** whose wording changed — numbers, Latin names, and the clause a rewrite
  touched — plus any term the editor names; every place each term still appears in the
  *old* wording (narration sentences, headings, slide body, mascot bubble, chapter titles,
  deck title/description, thumbnail text, upload title/description) is flagged, because a
  correction that fixes one occurrence and leaves the others is a contradiction on screen;
* **voice windows**: each changed sentence plus ``radius`` neighbours on each side, never
  crossing into another scene (research: fix-scope-2026-10 §2);
* **scenes** whose pieces are redrawn (any change on that slide) vs. scenes that only move
  in time (everything after a scene whose length may change). Scene identities make the
  second group free: their media and mascot clips are position-independent.

Pure functions over dicts; :func:`load_texts` reads the run-dir files that carry wording.
"""

from __future__ import annotations

import difflib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from content_farm.explainer.sentence_ids import LedgerEntry, assign, deck_sentences, ledger_from_deck

_NUMBER = re.compile(r"\d[\d,.]*\s*(?:萬|億|千|百|%|％|倍|片|個|年|月|週|天|奈米|nm|mm²?)?")
_LATIN = re.compile(r"[A-Za-z][A-Za-z0-9\-+.]*")
_CLAUSE_SPLIT = re.compile(r"[，。、！？!?；;：:「」『』（）()]")
_SPACE = re.compile(r"\s+")


def _squash(text: str) -> str:
    return _SPACE.sub("", text)


@dataclass(frozen=True)
class Occurrence:
    term: str
    where: str          # e.g. "narration s12.3", "heading k1", "title", "thumbnail.json lines[1]"
    text: str


@dataclass(frozen=True)
class Scope:
    changed: tuple[str, ...]                     # new ids of rewritten sentences
    added: tuple[str, ...]
    removed: tuple[str, ...]                     # old ids no longer in the deck
    terms: tuple[str, ...]
    occurrences: tuple[Occurrence, ...]
    voice_windows: dict[str, tuple[str, ...]]    # slide id -> sentence ids to re-voice (new ids)
    redraw_scenes: tuple[str, ...]               # slide ids whose clips are rebuilt
    shifted_scenes: tuple[str, ...]              # slide ids that only move in time
    notes: tuple[str, ...] = field(default=())

    def to_json(self) -> dict:
        return {
            "changed": list(self.changed), "added": list(self.added), "removed": list(self.removed),
            "terms": list(self.terms),
            "occurrences": [{"term": o.term, "where": o.where, "text": o.text} for o in self.occurrences],
            "voice_windows": {k: list(v) for k, v in self.voice_windows.items()},
            "redraw_scenes": list(self.redraw_scenes), "shifted_scenes": list(self.shifted_scenes),
            "notes": list(self.notes),
        }


# --- terms ------------------------------------------------------------------------------------

def _tokens(text: str) -> set[str]:
    return {_squash(m.group(0)) for m in _NUMBER.finditer(text)} | {m.group(0) for m in _LATIN.finditer(text)}


def _clauses(text: str) -> list[str]:
    return [c for c in _CLAUSE_SPLIT.split(_squash(text)) if len(c) >= 2]


def changed_terms(old: str, new: str) -> list[str]:
    """Wording that left the sentence: numbers / Latin tokens no longer present, and each
    clause (between punctuation) a rewrite touched — insertions included — in its old form."""
    terms = sorted(_tokens(old) - _tokens(new))
    flat_old, new_clauses = _squash(old), set(_clauses(new))
    matcher = difflib.SequenceMatcher(a=flat_old, b=_squash(new), autojunk=False)
    edits = [(i1, i2) for tag, i1, i2, _j1, _j2 in matcher.get_opcodes() if tag != "equal"]
    start = 0
    for clause in _CLAUSE_SPLIT.split(flat_old):
        lo, hi = start, start + len(clause)
        start = hi + 1
        touched = any(i1 <= hi and i2 >= lo for i1, i2 in edits)   # inside, overlapping or at its edge
        if len(clause) >= 2 and clause not in new_clauses and touched:
            terms.append(clause)
    seen: list[str] = []
    for term in terms:
        if term and term not in seen:
            seen.append(term)
    return seen


# --- where wording lives ------------------------------------------------------------------------

def deck_texts(deck: Mapping) -> list[tuple[str, str]]:
    """(where, text) for every on-screen / spoken string in a raw deck dict."""
    out: list[tuple[str, str]] = [("title", deck.get("title", "")), ("description", deck.get("description", ""))]
    for section in deck.get("sections", []):
        out.append((f"chapter {section.get('title', '')}", section.get("title", "")))
        for slide in section.get("slides", []):
            sid = slide["id"]
            out.append((f"heading {sid}", slide.get("heading", "")))
            out.append((f"body {sid}", json.dumps(slide.get("body", {}), ensure_ascii=False)))
            say = (slide.get("mascot") or {}).get("say")
            if say:
                out.append((f"mascot {sid}", say))
            media = slide.get("media") or {}
            for key in ("headline", "summary"):
                if media.get(key):
                    out.append((f"media.{key} {sid}", media[key]))
    return [(w, t) for w, t in out if t]


def load_texts(run_dir: Path) -> list[tuple[str, str]]:
    """Wording outside deck.json: thumbnail text, upload title / description."""
    out: list[tuple[str, str]] = []
    for name in ("thumbnail.json", "thumbnail_variants.json"):
        path = run_dir / name
        if path.is_file():
            out.extend((f"{name} {where}", text) for where, text in _strings(json.loads(path.read_text("utf-8"))))
    for name in ("upload/youtube_meta.json",):
        path = run_dir / name
        if path.is_file():
            out.extend((f"{name} {where}", text) for where, text in _strings(json.loads(path.read_text("utf-8"))))
    for name in ("upload/manual/title.txt", "upload/manual/description.txt"):
        path = run_dir / name
        if path.is_file():
            out.append((name, path.read_text(encoding="utf-8")))
    return out


def _strings(value: object, where: str = "") -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(where or "$", value)]
    if isinstance(value, Mapping):
        return [item for k, v in value.items() for item in _strings(v, f"{where}.{k}" if where else str(k))]
    if isinstance(value, Sequence):
        return [item for i, v in enumerate(value) for item in _strings(v, f"{where}[{i}]")]
    return []


# --- the analysis ----------------------------------------------------------------------------

REWRITE_SIMILARITY = 0.5


def _closest(text: str, candidates: Sequence[str]) -> str | None:
    best, score = None, REWRITE_SIMILARITY
    for candidate in candidates:
        ratio = difflib.SequenceMatcher(a=_squash(candidate), b=_squash(text), autojunk=False).ratio()
        if ratio >= score:
            best, score = candidate, ratio
    return best


def voice_window(ids: Sequence[str], target: str, radius: int) -> tuple[str, ...]:
    i = list(ids).index(target)
    return tuple(ids[max(0, i - radius): i + radius + 1])


def _old_ids(old: Mapping, ledger: Mapping[str, LedgerEntry] | None) -> dict[str, tuple[str, ...]]:
    stamp = assign(deck_sentences(old), ledger if ledger is not None else ledger_from_deck(old))
    return stamp.ids


def _slide_fields(deck: Mapping) -> dict[str, str]:
    return {s["id"]: json.dumps({k: v for k, v in s.items() if k not in ("narration", "sentence_ids", "notes")},
                                ensure_ascii=False, sort_keys=True)
            for section in deck.get("sections", []) for s in section.get("slides", [])}


def analyse(old: Mapping, new: Mapping, *, radius: int = 2, extra_terms: Sequence[str] = (),
            outside: Sequence[tuple[str, str]] = (), ledger: Mapping[str, LedgerEntry] | None = None) -> Scope:
    """``old``/``new``: raw deck dicts; ``outside``: (where, text) from :func:`load_texts`."""
    old_ids = _old_ids(old, ledger)
    old_text = {sid: text for slide_id, sentences in deck_sentences(old)
                for sid, text in zip(old_ids[slide_id], sentences)}
    base = {sid: LedgerEntry(slide, text) for slide, sentences in deck_sentences(old)
            for sid, text in zip(old_ids[slide], sentences)}
    stamp = assign(deck_sentences(new), base)
    new_text = {sid: text for slide_id, sentences in deck_sentences(new)
                for sid, text in zip(stamp.ids[slide_id], sentences)}
    slide_of = {sid: slide_id for slide_id, ids in stamp.ids.items() for sid in ids}

    # A rewritten sentence = a fresh id; its old wording = the most similar retired sentence of
    # the same slide (when similar enough to be a rewrite rather than a new sentence).
    changed: list[str] = []
    terms: list[str] = list(extra_terms)
    for slide_id, ids in stamp.ids.items():
        retired_here = [sid for sid in old_ids.get(slide_id, ()) if sid in stamp.retired]
        for sid in ids:
            if sid not in stamp.added:
                continue
            changed.append(sid)
            before = _closest(new_text[sid], [old_text[r] for r in retired_here])
            if before is not None:
                terms.extend(t for t in changed_terms(before, new_text[sid]) if t not in terms)

    occurrences = _occurrences(terms, new, new_text, outside)
    windows: dict[str, set[str]] = {}
    for sid in changed:
        slide_id = slide_of[sid]
        windows.setdefault(slide_id, set()).update(voice_window(stamp.ids[slide_id], sid, radius))
    for occ in occurrences:
        if occ.where.startswith("narration "):
            sid = occ.where.split(" ", 1)[1]
            windows.setdefault(slide_of[sid], set()).update(voice_window(stamp.ids[slide_of[sid]], sid, radius))
    ordered_windows = {slide: tuple(s for s in stamp.ids[slide] if s in ids) for slide, ids in windows.items()}

    old_fields, new_fields = _slide_fields(old), _slide_fields(new)
    order = [slide_id for slide_id, _ in deck_sentences(new)]
    flagged_slides = {o.where.split(" ", 1)[1] for o in occurrences
                      if o.where.split(" ", 1)[0] in ("heading", "body", "mascot", "media.headline", "media.summary")}
    redraw = [s for s in order if s in ordered_windows or old_fields.get(s) != new_fields.get(s) or s in flagged_slides]
    first_redraw = min((order.index(s) for s in redraw), default=len(order))
    shifted = [s for s in order[first_redraw + 1:] if s not in redraw]
    notes = []
    if [s for s, _ in deck_sentences(old)] != [s for s, _ in deck_sentences(new)]:
        notes.append("slide order or count changed: page numbers on every frame move, those slides redraw")
    return Scope(changed=tuple(changed), added=tuple(s for s in stamp.added if s not in changed),
                 removed=stamp.retired, terms=tuple(terms), occurrences=tuple(occurrences),
                 voice_windows=ordered_windows, redraw_scenes=tuple(redraw), shifted_scenes=tuple(shifted),
                 notes=tuple(notes))


def _occurrences(terms: Sequence[str], deck: Mapping, sentences: Mapping[str, str],
                 outside: Sequence[tuple[str, str]]) -> list[Occurrence]:
    """Every place a term still appears (whitespace-insensitive)."""
    places = [(f"narration {sid}", text) for sid, text in sentences.items()]
    places += deck_texts(deck) + list(outside)
    found = []
    for term in terms:
        needle = _squash(term)
        if not needle:
            continue
        for where, text in places:
            if needle in _squash(text):
                found.append(Occurrence(term, where, text if len(text) <= 120 else text[:117] + "…"))
    return found
