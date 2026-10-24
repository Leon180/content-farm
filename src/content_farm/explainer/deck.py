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

# Narration speed used for the pre-voice duration estimate; voice overwrites every
# scene with the measured duration anyway. Measured on the Fish Audio voices
# (REPORT-real-voice §2): CoWoS 6.7, cel 6.3, yokai 5.1 chars/s; 5.5 is the
# conservative middle (was 4.5 for macOS `say`, which over-estimated by ~40%).
CHARS_PER_SECOND = 5.5

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
    STOCK_VIDEO = "stock_video"  # free / public-domain footage (Commons, NASA, NOAA, Pexels, Pixabay): 3–8 s cuts, source label
    AI_IMAGE = "ai_image"      # generated illustration, moved by ``media.motion`` (default parallax)
    TITLE_CARD = "title_card"  # self-made news headline card (never a screenshot)
    ARTWORK = "artwork"        # public-domain / CC0 museum image (assets/artwork/artwork.json)
    DIAGRAM = "diagram"        # channel-drawn animated diagram (explainer.diagrams), timed to the narration


class Motion(str, Enum):
    """How an ``ai_image`` still moves (Leon 2026-10-16, decision 2bacb8a2b8b0)."""

    PARALLAX = "parallax"    # default: 2.5D depth parallax, ≤3 s, ping-ponged over the slot
    WAN = "wan"              # key shot: Wan2.2 I2V clip baked overnight (≤3 per video)
    KEN_BURNS = "ken_burns"  # flat push-in (the pre-motion behaviour)


class Frame(str, Enum):
    """How an ``ai_image`` slide carries its text (visual v4, Leon 2026-10-24): the picture always fills the screen and
    moves; the slide's own text sits over it in one of these forms. Consecutive slides must not share a form."""

    LOWER = "lower"              # default: heading + key line in a lower third
    PANEL_LEFT = "panel_left"    # translucent text card on the left (heading + the slide body as short lines)
    PANEL_RIGHT = "panel_right"  # same, on the right


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
    MediaKind.STOCK_VIDEO: "query",
    MediaKind.AI_IMAGE: "prompt",
    MediaKind.ANIMATED: "animation",
    MediaKind.ARTWORK: "artwork",
    MediaKind.DIAGRAM: "diagram",
}


StockKeyword = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{1,23}$")]


class Media(_Frozen):
    kind: MediaKind = MediaKind.SLIDE
    query: str = Field(default="", max_length=100)       # stock: English search terms
    # stock: a clip is kept only if its Pexels slug / Pixabay tags contain one of
    # these words (default: the query's specific words). See stock.relevance_terms.
    keywords: tuple[StockKeyword, ...] = Field(default=(), max_length=8)
    prompt: str = Field(default="", max_length=1200)     # ai_image: generation prompt
    animation: Animation | None = None                   # animated
    headline: str = Field(default="", max_length=60)     # title_card: defaults to source title
    summary: str = Field(default="", max_length=80)      # title_card: one-line summary
    source_id: str = Field(default="", max_length=32)    # title_card: must be in deck.sources
    artwork: str = Field(default="", max_length=40)      # artwork: id in assets/artwork/artwork.json
    motion: Motion | None = None                         # ai_image: None = parallax
    motion_prompt: str = Field(default="", max_length=600)  # ai_image + wan: what moves (English)
    # ai_image + wan: more 2.9 s segments, each started from the previous segment's last frame
    # (one continuous 6–9 s shot); one prompt per extra segment. See explainer/wan_chain.py.
    wan_chain: tuple[Annotated[str, Field(min_length=1, max_length=600)], ...] = Field(default=(), max_length=2)
    # ai_image + wan: the first segment is text-to-video (no start frame); the still is only the fallback.
    wan_t2v: bool = False
    frame: Frame | None = None                           # ai_image: text form over the picture (None = lower third)
    # ai_image: a correction shown beside the 「AI 示意圖」 badge when the picture cannot match the
    # text (e.g. the model draws 6 tails for 「九尾」): say so on screen rather than let it mislead.
    ai_note: str = Field(default="", max_length=24)
    # stock_video: a pinned clip (Commons file page, images.nasa.gov/details/<id>, noaa.gov page) instead of a search, and
    # an optional start second inside it. The query is still required (it names what the clip must show).
    url: str = Field(default="", max_length=500)
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, gt=0)    # stock_video: stop cutting here (skips an end title card)
    footage_note: str = Field(default="", max_length=24)  # stock_video: shown after the credit, e.g. 「深海生物示意」
    # diagram: which built-in diagram, and its params ("values"/"labels", | separated; stage times
    # come from the narration — each label is matched to the sentence that says it)
    diagram: str = Field(default="", max_length=32)
    params: dict[str, str] = {}

    @model_validator(mode="after")
    def _required_for_kind(self) -> Media:
        field = _MEDIA_REQUIRED.get(self.kind)
        if field and not getattr(self, field):
            raise ValueError(f"media kind {self.kind.value!r} requires {field!r}")
        if self.kind == MediaKind.DIAGRAM:
            from content_farm.explainer.diagrams.render import DIAGRAMS

            if self.diagram not in DIAGRAMS:
                raise ValueError(f"unknown diagram {self.diagram!r}; known: {', '.join(DIAGRAMS)}")
        elif self.diagram or self.params:
            raise ValueError("diagram / params only apply to media kind 'diagram'")
        if (self.motion is not None or self.motion_prompt) and self.kind != MediaKind.AI_IMAGE:
            raise ValueError("motion / motion_prompt only apply to media kind 'ai_image'")
        if (self.wan_chain or self.wan_t2v) and self.motion_kind != Motion.WAN:
            raise ValueError("wan_chain / wan_t2v need media.motion: wan")
        if self.ai_note and self.kind != MediaKind.AI_IMAGE:
            raise ValueError("ai_note only applies to media kind 'ai_image'")
        if self.frame is not None and self.kind not in (MediaKind.AI_IMAGE, MediaKind.STOCK_VIDEO):
            raise ValueError("frame only applies to media kinds 'ai_image' and 'stock_video'")
        if (self.url or self.start is not None or self.end is not None or self.footage_note) \
                and self.kind != MediaKind.STOCK_VIDEO:
            raise ValueError("url / start / end / footage_note only apply to media kind 'stock_video'")
        if self.end is not None and self.start is not None and self.end <= self.start:
            raise ValueError("media.end must be after media.start")
        return self

    @property
    def motion_kind(self) -> Motion:
        return self.motion or Motion.PARALLAX

    @property
    def frame_kind(self) -> Frame:
        return self.frame or Frame.LOWER


class Source(_Frozen):
    id: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=200)
    url: str = ""
    note: str = ""
    publisher: str = Field(default="", max_length=40)  # title_card: media outlet name
    # title_card: the outlet's headline verbatim (shown as 「媒體原標題」, kept apart from the
    # channel's own summary so viewers never mistake our wording for the outlet's).
    headline: str = Field(default="", max_length=200)
    published: str = Field(default="", pattern=r"^$|^\d{4}-\d{2}(-\d{2})?$")  # YYYY-MM[-DD]


class ReferenceLink(_Frozen):
    """A description-box link to a video we may not show (title + URL + one line on why to watch it)."""

    title: str = Field(min_length=1, max_length=120)
    url: str = Field(pattern=r"^https?://\S+$", max_length=500)
    note: str = Field(min_length=1, max_length=160)


Beat = Literal["gossip", "joke"]


class Slide(_Frozen):
    id: str = Field(min_length=1, max_length=32)
    layout: Layout
    heading: str = Field(min_length=1, max_length=HEADING_MAX_CHARS)
    body: SlideBody
    narration: str
    source_ids: tuple[str, ...] = ()
    beat: Beat | None = None  # light segment: sourced gossip or an original deadpan joke
    # The channel's own view: an argued judgment, our own calculation or comparison — not a
    # summary of sources. Every publishable deck needs one (YPP "inauthentic content" defence).
    take: bool = False
    mascot: Mascot | None = None
    media: Media | None = None  # None = the rendered slide (kind "slide")
    notes: str = ""
    # One stable id per narration sentence (``s12.3``), stamped by explainer.sentence_ids;
    # unchanged sentences keep theirs across edits so cached audio/clips can be reused.
    sentence_ids: tuple[str, ...] = ()

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
    # Copyrighted web video (YouTube, MBARI, TV…) never goes on screen; it is linked from the description (after credits).
    reference_links: tuple[ReferenceLink, ...] = ()
    pronunciation_map: dict[str, str] = {}
    # A deck that deliberately leans on Wan (e.g. the megalophobia cut) raises the 3-shot default;
    # the nightly bake, lint and QC all read it through wan.max_shots(deck).
    wan_budget: int | None = Field(default=None, ge=1, le=10)
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
