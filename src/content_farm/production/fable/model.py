"""The fable script (``fable.json``): a story that teaches a graduate-level concept, named only near the end.

One file per video, written by the ``fable_script`` producer agent (skill ``/fable-script``). Acts, in order:
``hook`` (one curious line, never the concept name) → ``story`` beats (the fable) → ``reveal`` (the first
beat that says the name) → ``explain`` beats (story elements mapped to the concept's parts) → ``apply``
(one real-world sentence). ``fable_prepare`` turns it into the run's ``script.json`` (one scene per beat).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FABLE_FILE = "fable.json"
Act = Literal["hook", "story", "reveal", "explain", "apply"]
Format = Literal["short", "mid"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class WanSpec(_Frozen):
    """Turn this shot's picture into a Wan clip: ``motion`` moves segment 1, each ``chain`` prompt adds a 2.9 s segment
    that starts from the previous last frame (Leon 2026-10-25: ~4 shots per video, 2 segments each, faceless scenes)."""

    motion: str = Field(min_length=10, max_length=300)
    chain: tuple[str, ...] = Field(default=("keep drifting slowly in the same direction, static camera",), min_length=1, max_length=2)


class Shot(_Frozen):
    """One picture. ``reuse`` names an earlier shot (``b3.1``) to show again instead of drawing a new one."""

    image_prompt: str = Field(default="", max_length=420)
    reuse: str = ""
    wan: WanSpec | None = None


class Row(_Frozen):
    story: str = Field(min_length=1, max_length=24)      # what happened in the fable
    concept: str = Field(min_length=1, max_length=28)    # the concept part it stands for


class Card(_Frozen):
    title: str = Field(default="", max_length=20)
    rows: tuple[Row, ...] = Field(default=(), max_length=4)


class Beat(_Frozen):
    id: str = Field(pattern=r"^b\d{1,2}$")
    act: Act
    narration: str = Field(min_length=6, max_length=260)
    must_keep: tuple[str, ...] = ()       # what this beat must carry (InkOS-style intent)
    must_avoid: tuple[str, ...] = ()      # what it must not say yet / at all
    shots: tuple[Shot, ...] = Field(min_length=1, max_length=3)
    plants: tuple[str, ...] = ()          # hook ids planted here
    resolves: tuple[str, ...] = ()        # hook ids paid off here
    maps: tuple[str, ...] = ()            # element ids this explain beat shows
    card: Card | None = None


class Element(_Frozen):
    id: str = Field(pattern=r"^e\d$")
    concept_part: str = Field(min_length=2, max_length=60)   # a part / premise / mechanism of the concept
    story_ref: str = Field(min_length=2, max_length=60)      # where the fable shows it


class Hook(_Frozen):
    id: str = Field(pattern=r"^h\d$")
    text: str = Field(min_length=2, max_length=80)            # the thread laid down in the story


class Concept(_Frozen):
    name: str = Field(min_length=2, max_length=30)
    aliases: tuple[str, ...] = ()        # synonyms and translations that would give it away
    english: tuple[str, ...] = ()        # English names, also kept out of the story
    domain: str = Field(min_length=2, max_length=20)          # e.g. 經濟學
    references: tuple[str, ...] = ()     # textbook / paper the explanation follows (the fact checker's anchor)


THUMB_HOOK_MAX = 8      # big thumbnail words (ideal 4–8): the title already says the rest


class ThumbOption(_Frozen):
    """One thumbnail candidate: a short hook (not the title) and a picture composed for the thumbnail."""

    hook: str = Field(min_length=2, max_length=THUMB_HOOK_MAX + 2)    # + punctuation; QC counts the visible ones
    image_prompt: str = Field(min_length=10, max_length=420)           # close-up, one subject, simple background
    layout: Literal["left", "right", "bottom"] = "bottom"              # where the hook sits


class Fable(_Frozen):
    version: Literal[1] = 1
    format: Format
    title: str = Field(min_length=4, max_length=40)
    thumb: tuple[ThumbOption, ...] = Field(default=(), max_length=3)   # candidates from the script panel (optional)
    concept: Concept
    elements: tuple[Element, ...] = Field(min_length=2, max_length=5)
    hooks: tuple[Hook, ...] = Field(default=(), max_length=5)
    beats: tuple[Beat, ...] = Field(min_length=5, max_length=40)
    pronunciation_map: dict[str, str] = Field(default_factory=dict)   # TTS only: 「熵」→「商」, subtitles keep the original

    def beat(self, beat_id: str) -> Beat | None:
        return next((b for b in self.beats if b.id == beat_id), None)

    def reveal_index(self) -> int | None:
        """Position of the reveal beat, None when there is none."""
        return next((i for i, b in enumerate(self.beats) if b.act == "reveal"), None)


def load(run_dir: Path) -> Fable:
    return Fable.model_validate_json((run_dir / FABLE_FILE).read_text(encoding="utf-8"))


def format_of(run_dir: Path) -> Format | None:
    """``short`` / ``mid`` for a fable run, None when the run-dir has no ``fable.json``."""
    path = run_dir / FABLE_FILE
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("format")
    except (OSError, json.JSONDecodeError):
        return None
    return value if value in ("short", "mid") else None


def is_fable_run(run_dir: Path | None) -> bool:
    return run_dir is not None and (run_dir / FABLE_FILE).is_file()
