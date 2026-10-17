"""What the slides put on screen vs. when the narration says it (sync + text density)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from content_farm.retention.timing import Scene, Sentence, normalise

SYNC_LATE = 12.0            # a number on screen not spoken within this many seconds = out of sync
DENSE_CHARS = 60            # visible characters on one page above this = dense (🟡)
_NUMBER = re.compile(r"\d[\d,.]*")


def slide_texts(run_dir: Path) -> dict[str, str]:
    deck_path = run_dir / "deck.json"
    if not deck_path.is_file():
        return {}
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    texts = {}
    for section in deck.get("sections", []):
        for slide in section["slides"]:
            texts[slide["id"]] = f"{slide.get('heading', '')} {_flatten(slide.get('body', {}))}"
    return texts


def _flatten(value: object) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_flatten(v) for v in value)
    return str(value)


def _numbers(text: str) -> list[str]:
    # "2023-09" → 2023 and 9 (spoken 「9 月」); drop thousands commas and leading zeros
    return [n.replace(",", "").rstrip(".").lstrip("0") or "0" for n in _NUMBER.findall(text)]


def sync_findings(scenes: list[Scene], sentences: list[Sentence], texts: dict[str, str]) -> list[dict]:
    """Numbers shown on a slide that its narration says late, or never."""
    issues = []
    for scene in scenes:
        shown = _numbers(texts.get(scene.slide_id, ""))
        said = [s for s in sentences if s.slide_id == scene.slide_id]
        for number in dict.fromkeys(shown):
            when = next((s.start for s in said if number in normalise(s.text).replace(",", "")), None)
            if when is None:
                issues.append({"slide_id": scene.slide_id, "t": round(scene.start, 1), "number": number,
                               "issue": "畫面有、旁白沒講"})
            elif when - scene.start > SYNC_LATE:
                issues.append({"slide_id": scene.slide_id, "t": round(scene.start, 1), "number": number,
                               "issue": f"畫面先出現，旁白 {when - scene.start:.0f} 秒後才講"})
    return issues


def density(texts: dict[str, str]) -> dict[str, int]:
    return {slide_id: len(normalise(text)) for slide_id, text in texts.items()}
