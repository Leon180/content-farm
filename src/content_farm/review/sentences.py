"""Sentences of a deck, each with an id reviewers can point at.

The stable sentence id is owned by feat/incremental-render (worker 38415991). Until it lands,
a slide without per-sentence ids gets ``<slide id>.<n>`` from splitting its narration at
sentence punctuation — good enough to point at, not stable across edits (``stable=False``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_SPLIT = re.compile(r"(?<=[。！？!?；])")


@dataclass(frozen=True)
class Sentence:
    id: str
    slide_id: str
    section: str
    text: str
    stable: bool


def _split(text: str) -> list[str]:
    return [part.strip() for part in _SPLIT.split(text) if part.strip()]


def deck_sentences(deck: dict[str, Any], id_field: str = "sid") -> list[Sentence]:
    out: list[Sentence] = []
    for section in deck.get("sections", []):
        title = str(section.get("title", ""))
        for slide in section.get("slides", []):
            sid = str(slide.get("id", ""))
            given = slide.get("sentences")
            if isinstance(given, list) and given and all(isinstance(s, dict) and s.get(id_field) for s in given):
                out += [Sentence(str(s[id_field]), sid, title, str(s.get("text") or s.get("tts") or ""), True)
                        for s in given]
                continue
            out += [Sentence(f"{sid}.{n}", sid, title, text, False)
                    for n, text in enumerate(_split(str(slide.get("narration", ""))), 1)]
    return out


def script_sentences(script: dict[str, Any]) -> list[Sentence]:
    """script.json (Shorts): one id per scene sentence, ``c<scene>.<n>``."""
    out = []
    for scene in script.get("scenes", []):
        number = scene.get("scene_number", len(out) + 1)
        out += [Sentence(f"c{number}.{n}", f"c{number}", "", text, False)
                for n, text in enumerate(_split(str(scene.get("narration", ""))), 1)]
    return out


def position_share(sentences: list[Sentence], sentence_id: str | None) -> float:
    """Share of the script (by characters) a viewer heard before leaving at ``sentence_id``;
    1.0 when they stayed or the id is unknown."""
    if not sentence_id:
        return 1.0
    total = sum(len(s.text) for s in sentences) or 1
    heard = 0
    for sentence in sentences:
        if sentence.id == sentence_id:
            return round(heard / total, 3)
        heard += len(sentence.text)
    return 1.0


def listing(sentences: list[Sentence], seconds_per_char: float = 0.22) -> str:
    """One line per sentence: ``[id] ~m:ss section｜text`` with an estimated time."""
    lines, chars, current = [], 0, None
    for sentence in sentences:
        if sentence.section != current:
            current = sentence.section
            lines.append(f"\n## {current}")
        t = int(chars * seconds_per_char)
        lines.append(f"[{sentence.id}] ~{t // 60}:{t % 60:02d} {sentence.text}")
        chars += len(sentence.text)
    return "\n".join(lines).strip() + "\n"
