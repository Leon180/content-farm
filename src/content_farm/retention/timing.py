"""Where each narration sentence lands on the video timeline.

Scene boundaries come from ``script.json`` (the voice step writes the measured audio length
back into every scene). Inside a scene the sentence times come from the whisper-aligned
``subtitles.srt`` when its text matches the narration, else from the character position
(the narration speed is close to constant within one take).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from content_farm.visual.timeline import parse_srt

_SENTENCE_END = re.compile(r"(?<=[。！？!?；;])")
_NOT_SPOKEN = re.compile(r"[\s，。、！？!?；;：:「」『』（）()\"'“”‘’…—\-,.]")


def normalise(text: str) -> str:
    """Drop whitespace and punctuation so script text and subtitle text compare char by char."""
    return _NOT_SPOKEN.sub("", text)


@dataclass(frozen=True)
class Scene:
    index: int          # 1-based, matches audio/scene_NNN.mp3
    slide_id: str
    chapter: int        # 1-based section index
    start: float
    end: float
    narration: str


@dataclass(frozen=True)
class Sentence:
    scene: int
    slide_id: str
    text: str
    start: float
    end: float


def split_sentences(narration: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_END.split(narration) if part.strip()]


def load_scenes(run_dir: Path) -> list[Scene]:
    """Scenes with absolute start/end seconds, from script.json durations (+ deck slide ids)."""
    script = json.loads((run_dir / "script.json").read_text(encoding="utf-8"))
    ids = _slide_ids(run_dir)
    scenes: list[Scene] = []
    clock = 0.0
    for position, scene in enumerate(script["scenes"]):
        seconds = float(scene["duration_seconds"])
        scenes.append(Scene(index=int(scene.get("scene_number", position + 1)),
                            slide_id=ids[position] if position < len(ids) else f"scene{position + 1}",
                            chapter=int(scene.get("chapter_number") or 1),
                            start=round(clock, 3), end=round(clock + seconds, 3),
                            narration=scene["narration"]))
        clock += seconds
    return scenes


def _slide_ids(run_dir: Path) -> list[str]:
    deck_path = run_dir / "deck.json"
    if not deck_path.is_file():
        return []
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    return [slide["id"] for section in deck.get("sections", []) for slide in section["slides"]]


def _srt_char_clock(run_dir: Path) -> tuple[str, list[float]] | None:
    """Every spoken character of the subtitles with its (interpolated) time."""
    srt = run_dir / "subtitles" / "subtitles.srt"
    if not srt.is_file():
        return None
    chars: list[str] = []
    times: list[float] = []
    for start, end, text in parse_srt(srt.read_text(encoding="utf-8")):
        spoken = normalise(text)
        for k, char in enumerate(spoken):
            chars.append(char)
            times.append(start + (end - start) * k / max(len(spoken), 1))
    return "".join(chars), times


def sentence_timeline(run_dir: Path, scenes: list[Scene] | None = None) -> list[Sentence]:
    scenes = scenes if scenes is not None else load_scenes(run_dir)
    clock = _srt_char_clock(run_dir)
    narration = "".join(normalise(s.narration) for s in scenes)
    aligned = clock is not None and clock[0] == narration
    sentences: list[Sentence] = []
    offset = 0
    for scene in scenes:
        parts = split_sentences(scene.narration)
        scene_chars = max(sum(len(normalise(p)) for p in parts), 1)
        used = 0
        for part in parts:
            n = len(normalise(part))
            if aligned and n:
                start, end = clock[1][offset + used], clock[1][offset + used + n - 1]
            else:
                span = scene.end - scene.start
                start = scene.start + span * used / scene_chars
                end = scene.start + span * (used + n) / scene_chars
            sentences.append(Sentence(scene.index, scene.slide_id, part, round(start, 2), round(end, 2)))
            used += n
        offset += used
    return sentences


def speech_rate(run_dir: Path, scenes: list[Scene] | None = None) -> float:
    """Spoken characters per second over the narration (whole video, pauses included)."""
    scenes = scenes if scenes is not None else load_scenes(run_dir)
    total = sum(len(normalise(s.narration)) for s in scenes)
    seconds = sum(s.end - s.start for s in scenes)
    return round(total / seconds, 2) if seconds else 0.0
