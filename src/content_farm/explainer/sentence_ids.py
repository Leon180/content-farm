"""Stable sentence ids for deck narration (``s12.3``), kept across edits.

Every narration sentence (split like :func:`content_farm.retention.timing.split_sentences`)
carries an id in ``slide.sentence_ids``. Re-stamping after an edit keeps the id of every
sentence whose text did not change — even when its slide moved or it moved to another
slide — and gives new or rewritten sentences a fresh id. Ids are never reused: the ledger
(``sentence_ledger.json`` next to deck.json) remembers every id ever handed out and the
text it last named, which is what an edited deck is matched against.

A deck written before ids existed is migrated by the same call: with no ledger, sentence
``k`` of slide ``s12`` becomes ``s12.k``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from content_farm.retention.timing import split_sentences

LEDGER_FILE = "sentence_ledger.json"
_ID = re.compile(r"^(?P<slide>.+)\.(?P<n>\d+)$")


@dataclass(frozen=True)
class LedgerEntry:
    slide_id: str
    text: str
    retired: bool = False


@dataclass(frozen=True)
class Stamp:
    ids: dict[str, tuple[str, ...]]      # slide id -> sentence ids, in narration order
    ledger: dict[str, LedgerEntry]
    kept: tuple[str, ...]                # ids whose text is unchanged
    moved: tuple[str, ...]               # kept ids now on a different slide
    added: tuple[str, ...]               # fresh ids (new or rewritten sentences)
    retired: tuple[str, ...]             # ids whose sentence is gone


def _next_numbers(ledger: Mapping[str, LedgerEntry]) -> dict[str, int]:
    """Highest suffix ever used per slide prefix (so a retired id is never handed out again)."""
    highest: dict[str, int] = {}
    for sentence_id in ledger:
        match = _ID.match(sentence_id)
        if match:
            prefix, n = match["slide"], int(match["n"])
            highest[prefix] = max(highest.get(prefix, 0), n)
    return highest


def _claim(candidates: Sequence[str], taken: set[str]) -> str | None:
    for sentence_id in candidates:
        if sentence_id not in taken:
            return sentence_id
    return None


def assign(slides: Sequence[tuple[str, Sequence[str]]],
           ledger: Mapping[str, LedgerEntry] | None = None) -> Stamp:
    """Ids for ``slides`` = [(slide id, sentences)], matched against ``ledger``.

    Matching order per sentence: same text on the same slide, then same text anywhere
    (a moved sentence). Identical sentences are matched in order, one id each.
    """
    ledger = dict(ledger or {})
    live = {sid: e for sid, e in ledger.items() if not e.retired}
    by_slide_text: dict[tuple[str, str], list[str]] = {}
    by_text: dict[str, list[str]] = {}
    for sentence_id, entry in live.items():
        by_slide_text.setdefault((entry.slide_id, entry.text), []).append(sentence_id)
        by_text.setdefault(entry.text, []).append(sentence_id)
    taken: set[str] = set()
    pending: list[tuple[str, int, str]] = []
    out: dict[str, list[str | None]] = {}
    # Pass 1: same slide; pass 2: anywhere. Two passes so a sentence that stayed is never
    # robbed of its id by an identical sentence elsewhere that comes first in the deck.
    for slide_id, sentences in slides:
        row: list[str | None] = []
        for position, text in enumerate(sentences):
            sentence_id = _claim(by_slide_text.get((slide_id, text), []), taken)
            if sentence_id:
                taken.add(sentence_id)
            else:
                pending.append((slide_id, position, text))
            row.append(sentence_id)
        out[slide_id] = row
    # A sentence that comes back after being cut (an undo) gets its old id back.
    revivable: dict[str, list[str]] = {}
    for sentence_id, entry in ledger.items():
        if entry.retired:
            revivable.setdefault(entry.text, []).append(sentence_id)
    moved: list[str] = []
    fresh: list[tuple[str, int, str]] = []
    for slide_id, position, text in pending:
        sentence_id = _claim(by_text.get(text, []), taken) or _claim(revivable.get(text, []), taken)
        if sentence_id:
            taken.add(sentence_id)
            out[slide_id][position] = sentence_id
            moved.append(sentence_id)
        else:
            fresh.append((slide_id, position, text))
    numbers = _next_numbers(ledger)
    added: list[str] = []
    for slide_id, position, _text in fresh:
        numbers[slide_id] = numbers.get(slide_id, 0) + 1
        sentence_id = f"{slide_id}.{numbers[slide_id]}"
        out[slide_id][position] = sentence_id
        added.append(sentence_id)
    texts = {slide_id: list(sentences) for slide_id, sentences in slides}
    new_ledger = {sid: LedgerEntry(e.slide_id, e.text, retired=True) for sid, e in ledger.items()}
    for slide_id, row in out.items():
        for sentence_id, text in zip(row, texts[slide_id]):
            new_ledger[sentence_id] = LedgerEntry(slide_id, text)
    retired = tuple(sorted(sid for sid in live if sid not in taken))
    ids = {slide_id: tuple(str(s) for s in row) for slide_id, row in out.items()}
    kept = tuple(sid for row in ids.values() for sid in row if sid in live)
    return Stamp(ids=ids, ledger=new_ledger, kept=kept, moved=tuple(moved), added=tuple(added),
                 retired=retired)


def deck_sentences(deck: Mapping) -> list[tuple[str, list[str]]]:
    """[(slide id, narration sentences)] from a raw deck.json dict, in deck order."""
    return [(slide["id"], split_sentences(slide["narration"]))
            for section in deck.get("sections", []) for slide in section.get("slides", [])]


def ledger_from_deck(deck: Mapping) -> dict[str, LedgerEntry]:
    """A ledger rebuilt from ids already in the deck (only where they still line up with the
    narration): a deck stamped elsewhere, or a lost ledger file."""
    ledger: dict[str, LedgerEntry] = {}
    for section in deck.get("sections", []):
        for slide in section.get("slides", []):
            ids = slide.get("sentence_ids") or []
            sentences = split_sentences(slide["narration"])
            if len(ids) == len(sentences):
                ledger.update({sid: LedgerEntry(slide["id"], text) for sid, text in zip(ids, sentences)})
    return ledger


def load_ledger(path: Path) -> dict[str, LedgerEntry]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("sentences"), dict):
        raise ValueError(f"{path}: expected {{\"sentences\": {{id: {{slide_id, text}}}}}}")
    return {sid: LedgerEntry(str(e["slide_id"]), str(e["text"]), bool(e.get("retired", False)))
            for sid, e in data["sentences"].items()}


def write_ledger(path: Path, ledger: Mapping[str, LedgerEntry]) -> Path:
    payload = {"version": 1, "sentences": {
        sid: {"slide_id": e.slide_id, "text": e.text, **({"retired": True} if e.retired else {})}
        for sid, e in sorted(ledger.items())}}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def stamp_deck(deck: Mapping, ledger: Mapping[str, LedgerEntry] | None) -> tuple[dict, Stamp]:
    """A copy of the raw ``deck`` with ``sentence_ids`` on every slide (input untouched).

    The ledger file wins over ids in the deck; ids in the deck seed a missing ledger."""
    base = dict(ledger) if ledger else ledger_from_deck(deck)
    stamp = assign(deck_sentences(deck), base)
    sections = []
    for section in deck.get("sections", []):
        slides = [{**slide, "sentence_ids": list(stamp.ids[slide["id"]])} for slide in section.get("slides", [])]
        sections.append({**section, "slides": slides})
    return {**deck, "sections": sections}, stamp


def stamp_run(run_dir: Path, deck_path: Path | None = None) -> Stamp:
    """Stamp ``deck.json`` in place (only rewritten when an id changed) and update the ledger."""
    deck_path = deck_path or run_dir / "deck.json"
    raw = json.loads(deck_path.read_text(encoding="utf-8"))
    ledger_path = deck_path.parent / LEDGER_FILE
    stamped, stamp = stamp_deck(raw, load_ledger(ledger_path))
    if stamped != raw:
        deck_path.write_text(json.dumps(stamped, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_ledger(ledger_path, stamp.ledger)
    return stamp
