"""The script-quality checks as one entry point (quality v5 item 7): hooks ledger and continuity, for the script panel's
materials and for the QC report. Pure over ``deck.json`` (a dict) and ``hooks_ledger.json``; nothing here edits a file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from content_farm.review import coherence, hooks_ledger
from content_farm.review.sentences import deck_sentences


def slide_order(deck: dict[str, Any]) -> list[str]:
    return [str(s.get("id")) for section in deck.get("sections", []) for s in section.get("slides", [])]


def hooks_text(run_dir: Path, deck: dict[str, Any]) -> str | None:
    """Rendered ledger for the reviewer, or None when the run has no ``hooks_ledger.json``."""
    data = _ledger(run_dir)
    return None if data is None else hooks_ledger.render(data, slide_order(deck))


def coherence_text(deck: dict[str, Any]) -> str:
    return coherence.render([(s.id, s.text) for s in deck_sentences(deck)])


def _ledger(run_dir: Path) -> dict | None:
    try:
        return hooks_ledger.load(run_dir)
    except (OSError, ValueError, json.JSONDecodeError):
        return {"version": 1, "hooks": [{"id": "?", "kind": "", "text": "", "status": ""}]}   # unreadable: validate() reports it


def findings(run_dir: Path, deck: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(level, check, message) rows for QC: structural ledger problems and open hooks (warn), continuity suspicions (warn)."""
    rows: list[tuple[str, str, str]] = []
    data = _ledger(run_dir)
    if data is not None:
        issues = hooks_ledger.validate(data) + hooks_ledger.check_against_deck(data, slide_order(deck))
        rows += [("warn", "hooks_ledger", f"{i.hook_id}: {i.message}") for i in issues]
        if not issues:
            rows.append(("ok", "hooks_ledger", f"{len(data['hooks'])} hook(s), all paid or dropped with a reason"))
    sentences = [(s.id, s.text) for s in deck_sentences(deck)]
    suspicious = [s.message() for s in coherence.suspicions(sentences)] + coherence.enumeration_suspicions(sentences)
    rows += [("warn", "continuity", message) for message in suspicious[:12]]
    if not suspicious:
        rows.append(("ok", "continuity", "no conflicting quantities found"))
    return rows
