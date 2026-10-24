"""Slideshow risk: how much a deck page will read as "a slide being read aloud" instead of a moving picture.

The idea (a slideshow-risk score per page, with a threshold that triggers a fix request) is OpenMontage's; the factors,
weights and code here are our own. Each slide collects points for the things that make a page feel static:

* ``repeat``    - same on-screen form as the page before (and again within the last four pages)
* ``text``      - too many characters on the page itself
* ``long_hold`` - one picture held for a long narration
* ``plain``     - a bare text page (no picture, no animation)
* ``generic``   - an AI picture whose prompt names no concrete subject (decoration, not information)
* ``same_move`` - the same flat camera move as the page before, with no purpose given for it

A page at or above :data:`RISK_THRESHOLD` is "risky". :func:`fix_requests` turns the risky pages into plain-language
requests (change the form / add a picture / split the page) that the deck producer gets once; the run never blocks on it.
Everything is switchable per channel (``channels/<code>.yaml`` ``deck_risk.enabled``) and pure (no I/O).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from content_farm.explainer.deck import Deck, Layout, MediaKind, Motion, Slide
from content_farm.explainer.lint import form_of

RISK_THRESHOLD = 40
MAX_RISKY_SHARE = 0.25            # more risky pages than this share of the deck asks for a fix
TEXT_SOFT_CHARS = 60
TEXT_HARD_CHARS = 90
HOLD_SOFT_SECONDS = 15.0
HOLD_HARD_SECONDS = 25.0
# pages whose picture moves by itself (cut footage, drawn diagram, entrance animation, Wan clip) are not "held"
SELF_MOVING = (MediaKind.STOCK_VIDEO, MediaKind.DIAGRAM, MediaKind.ANIMATED)
GENERIC_PROMPT_CHARS = 40
FORM_WINDOW = 4

POINTS = {"repeat": 25, "repeat_again": 10, "text_soft": 15, "text_hard": 25, "hold_soft": 15, "hold_hard": 30,
          "plain": 20, "generic": 10, "same_move": 15}

REMEDY = {
    "repeat": "換版型或 media.frame（和前一頁長得一樣）",
    "text": "縮短畫面上的字，或拆成兩頁",
    "long_hold": "拆頁，或加一張不同畫面的圖",
    "plain": "加一張圖（ai_image）或動畫",
    "generic": "把 prompt 寫成具體主體（景別、主體、光線），不要只有氣氛",
    "same_move": "換運鏡（push-in / pull-back / pan）或在 motion_prompt 寫目的",
}


@dataclass(frozen=True)
class SlideRisk:
    slide_id: str
    score: int
    factors: tuple[str, ...]
    risky: bool

    def to_json(self) -> dict:
        return {"slide_id": self.slide_id, "score": self.score, "factors": list(self.factors), "risky": self.risky}


@dataclass(frozen=True)
class DeckRisk:
    slides: tuple[SlideRisk, ...]
    mean_score: float
    risky_share: float
    over_limit: bool        # too many risky pages in the deck

    def to_json(self) -> dict:
        return {"mean_score": round(self.mean_score, 1), "risky_share": round(self.risky_share, 3),
                "over_limit": self.over_limit, "threshold": RISK_THRESHOLD,
                "slides": [s.to_json() for s in self.slides]}

    @property
    def risky(self) -> tuple[SlideRisk, ...]:
        return tuple(s for s in self.slides if s.risky)


def screen_text_chars(slide: Slide) -> int:
    """Characters the page itself shows (heading plus its body); narration is spoken, not shown."""
    body = slide.body
    parts: list[str] = [slide.heading]
    if slide.layout == Layout.BULLETS:
        parts += list(body.items)                        # type: ignore[union-attr]
    elif slide.layout == Layout.BIG_NUMBER:
        parts += [body.value, body.unit, body.caption]   # type: ignore[union-attr]
    elif slide.layout == Layout.COMPARE:
        for side in (body.left, body.right):             # type: ignore[union-attr]
            parts += [side.label, *side.items]
    elif slide.layout == Layout.TIMELINE:
        for event in body.events:                         # type: ignore[union-attr]
            parts += [event.when, event.what]
    elif slide.layout == Layout.QUOTE:
        parts += [body.text, body.who]                    # type: ignore[union-attr]
    elif slide.layout == Layout.TITLE:
        parts.append(body.subtitle)                       # type: ignore[union-attr]
    return sum(len(p) for p in parts)


def _covers_screen(slide: Slide) -> bool:
    """The picture fills the frame (so the page text is a caption, not the content)."""
    return slide.media_kind not in (MediaKind.SLIDE, MediaKind.ANIMATED)


def _move(slide: Slide) -> str | None:
    media = slide.media
    if slide.media_kind != MediaKind.AI_IMAGE or media is None or media.motion_kind == Motion.WAN:
        return None
    return "flat" if not media.motion_prompt else None


def _slide_points(slide: Slide, previous: list[Slide], seconds: float) -> dict[str, int]:
    got: dict[str, int] = {}
    form = form_of(slide)
    if previous and form_of(previous[-1]) == form:
        got["repeat"] = POINTS["repeat"]
    elif sum(form_of(p) == form for p in previous[-FORM_WINDOW:]) >= 2:
        got["repeat"] = POINTS["repeat_again"]
    chars = screen_text_chars(slide)
    # a caption over a full-screen picture is allowed more text than a bare page, but a wall of text is a wall of text
    if chars > TEXT_HARD_CHARS:
        got["text"] = POINTS["text_hard"]
    elif chars > TEXT_SOFT_CHARS and not _covers_screen(slide):
        got["text"] = POINTS["text_soft"]
    wan = slide.media is not None and slide.media_kind == MediaKind.AI_IMAGE and slide.media.motion_kind == Motion.WAN
    held = seconds if slide.media_kind not in SELF_MOVING and not wan else 0.0
    if held > HOLD_HARD_SECONDS:
        got["long_hold"] = POINTS["hold_hard"]
    elif held > HOLD_SOFT_SECONDS:
        got["long_hold"] = POINTS["hold_soft"]
    if slide.media_kind == MediaKind.SLIDE:
        got["plain"] = POINTS["plain"]
    media = slide.media
    if slide.media_kind == MediaKind.AI_IMAGE and media is not None and len(media.prompt.strip()) < GENERIC_PROMPT_CHARS:
        got["generic"] = POINTS["generic"]
    if previous and _move(slide) and _move(previous[-1]) and slide.media_kind == previous[-1].media_kind:
        got["same_move"] = POINTS["same_move"]
    return got


def score_deck(deck: Deck, durations: Mapping[str, float] | None = None) -> DeckRisk:
    """Score every slide. ``durations``: measured seconds per slide id (after voice); default is the narration estimate."""
    slides = list(deck.slides)
    risks: list[SlideRisk] = []
    for index, slide in enumerate(slides):
        seconds = (durations or {}).get(slide.id, slide.estimated_seconds)
        points = _slide_points(slide, slides[:index], seconds)
        score = min(100, sum(points.values()))
        risks.append(SlideRisk(slide.id, score, tuple(sorted(points)), score >= RISK_THRESHOLD))
    mean = sum(r.score for r in risks) / len(risks) if risks else 0.0
    share = sum(r.risky for r in risks) / len(risks) if risks else 0.0
    return DeckRisk(tuple(risks), mean, share, share > MAX_RISKY_SHARE)


def fix_requests(risk: DeckRisk) -> list[str]:
    """One plain-language request per risky page, worst first; empty when the deck is within limits."""
    if not risk.over_limit:
        return []
    out = []
    for item in sorted(risk.risky, key=lambda r: -r.score):
        wants = "；".join(REMEDY["text" if f.startswith("text") else f] for f in dict.fromkeys(
            "text" if f.startswith("text") else f for f in item.factors))
        out.append(f"{item.slide_id}（投影片感 {item.score} 分：{'、'.join(item.factors)}）→ {wants}")
    return out


def producer_note(risk: DeckRisk) -> str:
    """The extra brief for the deck producer's one redo."""
    lines = fix_requests(risk)
    if not lines:
        return ""
    return ("以下頁面「像在念投影片」，請在不改事實與講稿意思的前提下，各自換版型／加圖／拆頁／縮短畫面字（只改這些頁，"
            "其他頁不動；改完仍要符合頻道素材政策與 deck lint）：\n- " + "\n- ".join(lines))
