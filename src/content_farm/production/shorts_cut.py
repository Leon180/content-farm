"""Cut a vertical Short out of a finished long video (roadmap R5, 「一個數字」).

A Short re-uses one slide of an approved long run: that slide's narration
audio (``audio/scene_NNN.mp3``) and its subtitle cues, re-laid for 9:16.
Nothing is re-voiced and no new facts are spoken, so the long video's
article / deck / media approvals still cover what the Short says; only the
final gate is needed.

This module is the pure part (spec, timing, subtitles, script); rendering
lives in :mod:`content_farm.production.shorts_render`.

Timeline of the Short (narration starts at 0 so the first second is never silent)::

    [intro card ─ intro_seconds][count-up panel ─ rest of the narration][outro card ─ outro_seconds]
    [────────────── slide narration audio ──────────────][── silence ──]
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from content_farm.explainer.deck import Deck, Slide
from content_farm.production.channels import Channel
from content_farm.script_gen.schemas import Script
from content_farm.subtitle.line_wrap import wrap_text
from content_farm.types import Orientation, VideoLength

SOURCE_FILE = "short_source.json"
MAX_SHORT_SECONDS = 60.0

# Portrait subtitle style, shared by the renderer (ASS) and QC (width check).
FRAME_W, FRAME_H = 1080, 1920
SUB_FONT_SIZE = 66
SUB_OUTLINE = 6
SUB_MARGIN_X = 70
SUB_MARGIN_V = 500          # bottom of the subtitle block, above the Shorts UI
SUB_MAX_CHARS = 13
SUB_MAX_LINES = 2

CUE_TOLERANCE = 0.35        # seconds a cue may start before the scene (alignment jitter)


class ShortSpec(BaseModel):
    """What ``produce.py short-from-long`` writes to ``short_source.json``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    long_run_dir: str
    slide_id: str = Field(min_length=1, max_length=32)
    label: str = Field(default="一個數字", min_length=1, max_length=12)
    number: str = Field(min_length=1, max_length=12)       # "7,722"
    unit: str = Field(default="", max_length=12)           # "mm²"
    caption: str = Field(min_length=1, max_length=40)
    aside: str = Field(default="", max_length=40)          # a derived comparison, e.g. 約 8.8 × 8.8 公分
    hook: str = Field(default="這是多大？", min_length=1, max_length=16)
    title: str = Field(min_length=1, max_length=90)        # YouTube title, " #Shorts" is appended
    long_channel: str = Field(min_length=1, max_length=20)  # where the full video lives
    long_title: str = Field(min_length=1, max_length=40)
    intro_seconds: float = Field(default=1.5, ge=0.5, le=4)
    outro_seconds: float = Field(default=2.5, ge=1, le=5)

    @field_validator("long_run_dir")
    @classmethod
    def _absolute(cls, value: str) -> str:
        if not Path(value).is_absolute():
            raise ValueError("long_run_dir must be an absolute path")
        return value


def write_spec(run_dir: Path, spec: ShortSpec) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / SOURCE_FILE
    path.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_spec(run_dir: Path) -> ShortSpec:
    return ShortSpec.model_validate_json((run_dir / SOURCE_FILE).read_text(encoding="utf-8"))


def is_short_cut(run_dir: Path | None) -> bool:
    return run_dir is not None and (run_dir / SOURCE_FILE).is_file()


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Timing:
    narration: float
    intro: float
    body: float
    outro: float

    @property
    def total(self) -> float:
        return self.narration + self.outro


def slide_index(deck: Deck, slide_id: str) -> int:
    """1-based position of ``slide_id`` (= its scene number in the long run)."""
    for index, slide in enumerate(deck.slides, start=1):
        if slide.id == slide_id:
            return index
    raise ValueError(f"slide {slide_id!r} is not in the deck")


def scene_window(durations: Sequence[float], index: int) -> tuple[float, float]:
    """Start/end of scene ``index`` (1-based) on the long timeline: scenes play back to back."""
    if not 1 <= index <= len(durations):
        raise ValueError(f"scene {index} out of range 1-{len(durations)}")
    start = sum(durations[: index - 1])
    return start, start + durations[index - 1]


def plan_timing(narration: float, intro: float, outro: float, limit: float = MAX_SHORT_SECONDS) -> Timing:
    if narration <= intro:
        raise ValueError(f"narration {narration:.1f}s is not longer than the {intro:.1f}s intro")
    timing = Timing(narration=narration, intro=intro, body=narration - intro, outro=outro)
    if timing.total > limit:
        raise ValueError(f"short would run {timing.total:.1f}s (limit {limit:.0f}s); pick a shorter slide")
    return timing


def cues_in_window(cues: Sequence[Cue], start: float, end: float) -> list[Cue]:
    """Cues of one scene, shifted so the scene starts at 0 and clipped to its length."""
    length = end - start
    picked = []
    for cue in cues:
        if cue.start < start - CUE_TOLERANCE or cue.start >= end:
            continue
        shifted = Cue(max(0.0, cue.start - start), min(length, cue.end - start), cue.text)
        if shifted.end > shifted.start:
            picked.append(shifted)
    if not picked:
        raise ValueError(f"no subtitle cue between {start:.2f}s and {end:.2f}s")
    return picked


def _wrap_strict(text: str, max_chars: int) -> list[str]:
    """``wrap_text`` lets a line run 4 chars long to end on punctuation; 9:16 allows only 1
    (a trailing 。). Longer lines are wrapped again at a tighter width."""
    out: list[str] = []
    for line in wrap_text(text, max_chars).split("\n"):
        out.extend(wrap_text(line, max_chars - 4).split("\n") if len(line) > max_chars + 1 else [line])
    return out


def relayout(cues: Sequence[Cue], max_chars: int = SUB_MAX_CHARS, max_lines: int = SUB_MAX_LINES) -> list[Cue]:
    """Re-wrap landscape cues for 9:16; a cue that needs more lines is split in time by length."""
    out: list[Cue] = []
    for cue in cues:
        lines = _wrap_strict(" ".join(cue.text.split("\n")), max_chars)
        groups = [lines[i:i + max_lines] for i in range(0, len(lines), max_lines)]
        weights = [sum(len(line) for line in group) for group in groups]
        clock, span = cue.start, cue.end - cue.start
        for group, weight in zip(groups, weights):
            length = span * weight / sum(weights)
            out.append(Cue(round(clock, 3), round(clock + length, 3), "\n".join(group)))
            clock += length
    return out


def _stamp(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def to_srt(cues: Sequence[Cue]) -> str:
    blocks = [f"{i}\n{_stamp(c.start)} --> {_stamp(c.end)}\n{c.text}\n" for i, c in enumerate(cues, start=1)]
    return "\n".join(blocks)


def parse_cues(srt_text: str) -> list[Cue]:
    from content_farm.visual.timeline import parse_srt

    return [Cue(start, end, text) for start, end, text in parse_srt(srt_text)]


_HASHTAG = re.compile(r"#shorts\b", re.IGNORECASE)


def shorts_title(title: str) -> str:
    return title if _HASHTAG.search(title) else f"{title} #Shorts"


def source_lines(deck: Deck, slide: Slide) -> list[str]:
    lines = []
    for source_id in slide.source_ids:
        source = deck.source_by_id(source_id)
        lines.append(f"{source.title} {source.url}".strip())
    return lines


def short_script(long_script: Script, deck: Deck, slide: Slide, spec: ShortSpec, timing: Timing) -> Script:
    """The Short's ``script.json``: one scene (the slide), Short-sized metadata."""
    index = slide_index(deck, slide.id)
    scene = long_script.scenes[index - 1].model_copy(
        update={"scene_number": 1, "duration_seconds": round(timing.total, 2), "chapter_number": None})
    description = "\n".join([
        f"{spec.number} {spec.unit}：{spec.caption}。".replace(" ：", "："),
        f"完整版在「{spec.long_channel}」頻道：《{spec.long_title}》",
        "",
        "#Shorts",
    ])
    tags = tuple(dict.fromkeys(("Shorts", spec.label, *long_script.tags)))
    return long_script.model_copy(update={
        "video_title": shorts_title(spec.title),
        "description": description,
        "scenes": (scene,),
        "chapters": (),
        "tags": tags,
        "sources": tuple(source_lines(deck, slide)),
        "target_length": VideoLength.SHORT,
        "orientation": Orientation.PORTRAIT,
        "total_duration_seconds": round(timing.total, 2),
    })


def source_note(deck: Deck, slide: Slide) -> str:
    """Small on-screen attribution for the number (publisher + date, else title)."""
    if not slide.source_ids:
        return ""
    source = deck.source_by_id(slide.source_ids[0])
    who = source.publisher or source.title[:24]
    return f"來源：{who}" + (f"（{source.published}）" if source.published else "")


def short_spec_from_long(long_run_dir: Path, long_channel: Channel, options: Mapping[str, Any]) -> ShortSpec:
    """Build the spec from CLI options, defaulting the number to the slide's big_number body.

    Refuses a long run whose deck was never approved: the Short repeats its
    narration word for word and has no review of its own before the final gate.
    """
    from content_farm.explainer.deck import BigNumberBody, load_deck
    from content_farm.production.state import load_state

    state = load_state(long_run_dir, long_channel.code)
    deck_decision = state.decisions.get("deck")
    if deck_decision is None or deck_decision.verdict != "approved":
        raise ValueError(f"{long_run_dir}: the long run's deck gate is not approved; cut Shorts after it is")
    for name in ("script.json", "subtitles/subtitles.srt"):
        if not (long_run_dir / name).is_file():
            raise ValueError(f"{long_run_dir}/{name} missing; run the long video through voice first")
    deck = load_deck(long_run_dir / "deck.json")
    slide = deck.slides[slide_index(deck, options["slide"]) - 1]
    body = slide.body if isinstance(slide.body, BigNumberBody) else None
    fields = {
        "number": options.get("number") or (body.value if body else None),
        "unit": options.get("unit") if options.get("unit") is not None else (body.unit if body else ""),
        "caption": options.get("caption") or (body.caption if body else None) or slide.heading,
    }
    if not fields["number"]:
        raise ValueError(f"slide {slide.id} is not a big_number slide; pass --number")
    return ShortSpec(
        long_run_dir=str(long_run_dir), slide_id=slide.id, title=options["title"],
        long_channel=long_channel.name, long_title=(options.get("long_title") or deck.title)[:40],
        aside=options.get("aside") or "", hook=options.get("hook") or "這是多大？",
        label=options.get("label") or "一個數字", **fields,
    )


def scene_durations(long_run_dir: Path) -> list[float]:
    """Measured per-scene seconds the voice stage wrote back into ``script.json``."""
    script = Script.model_validate_json((long_run_dir / "script.json").read_text(encoding="utf-8"))
    return [scene.duration_seconds for scene in script.scenes]


def write_credits(run_dir: Path, spec: ShortSpec) -> Path:
    """No third-party assets: the Short is self-made pages + the long run's narration."""
    payload = {"version": 1, "title": spec.title, "entries": [], "pending": [],
               "description_text": "", "derived_from": {"run_dir": spec.long_run_dir, "slide_id": spec.slide_id}}
    path = run_dir / "credits.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
