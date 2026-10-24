"""The script panel's fable questions: where did each synthetic viewer guess the concept, and was the reveal a surprise?

Viewers read the script in two parts (before the reveal / the reveal and after), write down a guess from the first
part and the sentence where they guessed it, then score the reveal. This module reads those answers back
(``review/**/results/viewer-*.json``, latest round of the script stage) and turns them into seconds into the video.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from content_farm.explainer.deck import CHARS_PER_SECOND, visible_len
from content_farm.production.fable.check import concept_terms
from content_farm.production.fable.model import Fable, load
from content_farm.review.sentences import script_sentences

STAGE_DIR = "shorts_script"


def _latest_results(run_dir: Path) -> list[Path]:
    rounds = sorted((run_dir / "review" / STAGE_DIR).glob("round-[0-9]*"), key=lambda p: int(p.name.split("-")[1]))
    return sorted((rounds[-1] / "results").glob("viewer-*.json")) if rounds else []


def seconds_at(fable: Fable, script: dict[str, Any], sentence_id: str | None) -> float | None:
    """Estimated seconds of narration before ``sentence_id`` (None = never guessed / unknown id)."""
    if not sentence_id:
        return None
    heard = 0
    for sentence in script_sentences(script):
        if sentence.id == sentence_id:
            return round(heard / CHARS_PER_SECOND, 1)
        heard += visible_len(sentence.text)
    return None


def _correct(fable: Fable, guess: str) -> bool:
    squashed = "".join(guess.split()).lower()
    return any(term in squashed or squashed in term for term in concept_terms(fable) if squashed)


def collect(run_dir: Path) -> list[dict[str, Any]]:
    fable = load(run_dir)
    script = json.loads((run_dir / "script.json").read_text(encoding="utf-8"))
    total = sum(visible_len(b.narration) for b in fable.beats) / CHARS_PER_SECOND
    rows = []
    for path in _latest_results(run_dir):
        data = json.loads(path.read_text(encoding="utf-8"))
        guess = data.get("guess") or {}
        at = guess.get("at_sentence")
        rows.append({"viewer": data.get("persona", path.stem)[:40], "guess": guess.get("concept", ""),
                     "correct": _correct(fable, str(guess.get("concept", ""))), "at_sentence": at,
                     "seconds": seconds_at(fable, script, at), "of_total": round(total, 1),
                     "surprise": data.get("reveal_surprise")})
    return rows


def table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "no viewer results with a guess yet (the script panel has not run)"
    lines = ["viewer | guess | right | guessed at | surprise", "---|---|---|---|---"]
    for r in rows:
        when = f"{r['at_sentence']} (~{r['seconds']:g} s of {r['of_total']:g} s)" if r["seconds"] is not None else "never before the reveal"
        lines.append(f"{r['viewer']} | {r['guess'] or '—'} | {'yes' if r['correct'] else 'no'} | {when} | {r['surprise']}")
    return "\n".join(lines)
