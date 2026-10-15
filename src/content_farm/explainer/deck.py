"""``deck.json`` schema — one slide = one scene = one narration segment.

Hard rules live here as validators (fail fast, before any rendering or TTS).
Softer production rules (slide count, pacing, layout variety) live in
:mod:`content_farm.explainer.lint` so a short sample deck can still be rendered.
"""

from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

# Narration speed used for the pre-voice duration estimate. Empirical guess for
# zh-TW TTS; voice overwrites every scene with the measured duration anyway.
CHARS_PER_SECOND = 4.5

NARRATION_MIN_CHARS = 30
NARRATION_MAX_CHARS = 220
HEADING_MAX_CHARS = 24
MIN_SECTIONS = 3  # YouTube chapters need >= 3 entries

_WHITESPACE = re.compile(r"\s+")


def visible_len(text: str) -> int:
    """Character count ignoring whitespace (CJK and ASCII both count 1)."""
    return len(_WHITESPACE.sub("", text))


def estimate_seconds(narration: str) -> float:
    return round(visible_len(narration) / CHARS_PER_SECOND, 2)


class Category(str, Enum):
    AI = "ai"
    TECH = "tech"  # 台灣科技產業拆解 — MVP default
    KNOWLEDGE = "knowledge"


class Layout(str, Enum):
    TITLE = "title"
    BULLETS = "bullets"
    BIG_NUMBER = "big_number"
    COMPARE = "compare"
    TIMELINE = "timeline"
    QUOTE = "quote"


class _Frozen(BaseModel):
    model_config = {"frozen": True, "extra": "forbid"}


BulletItem = Annotated[str, Field(min_length=1, max_length=18)]
CompareItem = Annotated[str, Field(min_length=1, max_length=16)]


class TitleBody(_Frozen):
    subtitle: str = Field(default="", max_length=40)


class BulletsBody(_Frozen):
    items: tuple[BulletItem, ...] = Field(min_length=3, max_length=5)


class BigNumberBody(_Frozen):
    value: str = Field(min_length=1, max_length=10)
    unit: str = Field(default="", max_length=8)
    caption: str = Field(default="", max_length=40)


class CompareSide(_Frozen):
    label: str = Field(min_length=1, max_length=12)
    items: tuple[CompareItem, ...] = Field(min_length=1, max_length=5)


class CompareBody(_Frozen):
    left: CompareSide
    right: CompareSide


class TimelineEvent(_Frozen):
    when: str = Field(min_length=1, max_length=10)
    what: str = Field(min_length=1, max_length=20)


class TimelineBody(_Frozen):
    events: tuple[TimelineEvent, ...] = Field(min_length=2, max_length=6)


class QuoteBody(_Frozen):
    text: str = Field(min_length=1, max_length=60)
    who: str = Field(default="", max_length=30)


SlideBody = Union[TitleBody, BulletsBody, BigNumberBody, CompareBody, TimelineBody, QuoteBody]

BODY_MODELS: dict[Layout, type[BaseModel]] = {
    Layout.TITLE: TitleBody,
    Layout.BULLETS: BulletsBody,
    Layout.BIG_NUMBER: BigNumberBody,
    Layout.COMPARE: CompareBody,
    Layout.TIMELINE: TimelineBody,
    Layout.QUOTE: QuoteBody,
}


MascotPose = Literal["idle", "point", "think", "shocked", "smug", "deadpan", "wave"]
SAY_MAX_CHARS = 20


class Mascot(_Frozen):
    """Corner mascot (晶片貓).

    The animated overlay (``explainer.mascot``, ``scripts/mascot_overlay.py``)
    plays ``pose`` with a 250 ms transition at the slide change and shows
    ``say`` in a speech bubble. The legacy static slot in the slide template
    still maps ``pose`` to ``<assets>/mascot/<pose>.png`` (missing = empty);
    use one or the other, not both.
    """

    pose: MascotPose = "idle"
    say: str | None = Field(default=None, min_length=1, max_length=SAY_MAX_CHARS)
    # "left" is accepted for the shared interface; the overlay currently keeps
    # the cat bottom-right because bottom-left collides with the meta row.
    position: Literal["right", "left"] = "right"


class MediaKind(str, Enum):
    """What fills the screen for a slide (v2). Absent ``media`` means ``slide``."""

    SLIDE = "slide"            # the rendered static slide PNG (v1 behaviour)
    ANIMATED = "animated"      # the same slide with an entrance animation (mp4)
    STOCK = "stock"            # Pexels/Pixabay B-roll + key-text overlay
    AI_IMAGE = "ai_image"      # user-generated illustration + Ken Burns
    TITLE_CARD = "title_card"  # self-made news headline card (never a screenshot)


class Animation(str, Enum):
    COUNT_UP = "count_up"
    GROW_BARS = "grow_bars"
    REVEAL_LIST = "reveal_list"
    DRAW_LINE = "draw_line"
    FADE_IN = "fade_in"


# Which layouts each animation knows how to move. ``fade_in`` works everywhere.
ANIMATION_LAYOUTS: dict[Animation, frozenset[Layout]] = {
    Animation.COUNT_UP: frozenset({Layout.BIG_NUMBER}),
    Animation.GROW_BARS: frozenset({Layout.BIG_NUMBER, Layout.COMPARE, Layout.BULLETS}),
    Animation.REVEAL_LIST: frozenset({Layout.BULLETS, Layout.COMPARE, Layout.TIMELINE}),
    Animation.DRAW_LINE: frozenset({Layout.TIMELINE}),
    Animation.FADE_IN: frozenset(Layout),
}

# The animation a slide falls back to when its stock/ai media is unavailable.
DEFAULT_ANIMATION: dict[Layout, Animation] = {
    Layout.TITLE: Animation.FADE_IN,
    Layout.BULLETS: Animation.REVEAL_LIST,
    Layout.BIG_NUMBER: Animation.COUNT_UP,
    Layout.COMPARE: Animation.GROW_BARS,
    Layout.TIMELINE: Animation.DRAW_LINE,
    Layout.QUOTE: Animation.FADE_IN,
}

_MEDIA_REQUIRED: dict[MediaKind, str] = {
    MediaKind.TITLE_CARD: "source_id",
    MediaKind.STOCK: "query",
    MediaKind.AI_IMAGE: "prompt",
    MediaKind.ANIMATED: "animation",
}


class Media(_Frozen):
    kind: MediaKind = MediaKind.SLIDE
    query: str = Field(default="", max_length=100)       # stock: English search terms
    prompt: str = Field(default="", max_length=1200)     # ai_image: generation prompt
    animation: Animation | None = None                   # animated
    headline: str = Field(default="", max_length=60)     # title_card: defaults to source title
    summary: str = Field(default="", max_length=80)      # title_card: one-line summary
    source_id: str = Field(default="", max_length=32)    # title_card: must be in deck.sources

    @model_validator(mode="after")
    def _required_for_kind(self) -> Media:
        field = _MEDIA_REQUIRED.get(self.kind)
        if field and not getattr(self, field):
            raise ValueError(f"media kind {self.kind.value!r} requires {field!r}")
        return self


class Source(_Frozen):
    id: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=200)
    url: str = ""
    note: str = ""
    publisher: str = Field(default="", max_length=40)  # title_card: media outlet name
    published: str = Field(default="", pattern=r"^$|^\d{4}-\d{2}(-\d{2})?$")  # YYYY-MM[-DD]


Beat = Literal["gossip", "joke"]


class Slide(_Frozen):
    id: str = Field(min_length=1, max_length=32)
    layout: Layout
    heading: str = Field(min_length=1, max_length=HEADING_MAX_CHARS)
    body: SlideBody
    narration: str
    source_ids: tuple[str, ...] = ()
    beat: Beat | None = None  # light segment: sourced gossip or an original deadpan joke
    mascot: Mascot | None = None
    media: Media | None = None
    notes: str = ""

    @model_validator(mode="before")
    @classmethod
    def _body_matches_layout(cls, data: object) -> object:
        """Validate ``body`` against the model of its own ``layout`` (no guessing)."""
        if not isinstance(data, dict) or isinstance(data.get("body"), BaseModel):
            return data
        try:
            layout = Layout(data.get("layout"))
        except ValueError:
            return data  # the enum field reports the bad layout
        model = BODY_MODELS[layout]
        return {**data, "body": model.model_validate(data.get("body") or {})}

    @field_validator("narration")
    @classmethod
    def _narration_length(cls, value: str) -> str:
        n = visible_len(value)
        if not NARRATION_MIN_CHARS <= n <= NARRATION_MAX_CHARS:
            raise ValueError(
                f"narration has {n} chars; must be {NARRATION_MIN_CHARS}-{NARRATION_MAX_CHARS}"
            )
        return value

    @model_validator(mode="after")
    def _body_type(self) -> Slide:
        expected = BODY_MODELS[self.layout]
        if not isinstance(self.body, expected):
            raise ValueError(f"layout {self.layout.value!r} needs a {expected.__name__} body")
        if self.beat == "gossip" and not self.source_ids:
            raise ValueError("gossip beat must cite source_ids (no unsourced rumours)")
        animation = self.media.animation if self.media else None
        if animation and self.layout not in ANIMATION_LAYOUTS[animation]:
            allowed = sorted(layout.value for layout in ANIMATION_LAYOUTS[animation])
            raise ValueError(
                f"animation {animation.value!r} does not fit layout {self.layout.value!r} "
                f"(fits {allowed})"
            )
        return self

    @property
    def estimated_seconds(self) -> float:
        return estimate_seconds(self.narration)

    @property
    def media_kind(self) -> MediaKind:
        return self.media.kind if self.media else MediaKind.SLIDE

    @property
    def animation(self) -> Animation:
        """Animation to use when this slide is rendered as ``animated`` (incl. fallbacks)."""
        if self.media and self.media.animation:
            return self.media.animation
        return DEFAULT_ANIMATION[self.layout]


class Section(_Frozen):
    """One section = one YouTube chapter."""

    title: str = Field(min_length=1, max_length=40)
    slides: tuple[Slide, ...] = Field(min_length=1)


class Deck(_Frozen):
    version: Literal[1] = 1
    category: Category = Category.TECH
    title: str = Field(min_length=1, max_length=100)
    description: str = ""
    tags: tuple[str, ...] = ()
    as_of: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    # True while numbers are placeholders: every slide gets a visible
    # "示意數字・待查證" badge and lint refuses to call the deck publishable.
    draft_data: bool = False
    sources: tuple[Source, ...] = ()
    pronunciation_map: dict[str, str] = {}
    sections: tuple[Section, ...] = Field(min_length=MIN_SECTIONS)

    @model_validator(mode="after")
    def _cross_checks(self) -> Deck:
        if self.category in (Category.AI, Category.TECH) and not self.as_of:
            raise ValueError(f"category {self.category.value!r} requires as_of (YYYY-MM)")
        source_ids = [s.id for s in self.sources]
        _ensure_unique("source id", source_ids)
        _ensure_unique("slide id", [s.id for s in self.slides])
        known = set(source_ids)
        for slide in self.slides:
            missing = [sid for sid in slide.source_ids if sid not in known]
            if missing:
                raise ValueError(f"slide {slide.id!r} cites unknown source_ids {missing}")
            card_source = slide.media.source_id if slide.media else ""
            if card_source and card_source not in known:
                raise ValueError(
                    f"slide {slide.id!r} media.source_id {card_source!r} is not in sources"
                )
        return self

    @property
    def slides(self) -> tuple[Slide, ...]:
        return tuple(slide for section in self.sections for slide in section.slides)

    def source_by_id(self, source_id: str) -> Source:
        return next(s for s in self.sources if s.id == source_id)


def _ensure_unique(label: str, values: list[str]) -> None:
    dupes = sorted({v for v in values if values.count(v) > 1})
    if dupes:
        raise ValueError(f"duplicate {label}s: {dupes}")


def load_deck(path: Path) -> Deck:
    """Read and validate ``deck.json``. Raises ``pydantic.ValidationError``."""
    return Deck.model_validate(json.loads(path.read_text(encoding="utf-8")))
