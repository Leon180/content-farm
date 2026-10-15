"""HTML for v2 media frames (pure; no browser): footage overlay, news title card, AI placeholder.

All three share the slide frame (top bar, meta row with 資料截至 / disclaimer,
subtitle safe zone) and the deck theme, so a stock shot or a title card looks
like part of the same video rather than a pasted-in asset.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from content_farm.explainer.deck import Deck, Layout, Section, Slide
from content_farm.explainer.pages import DISCLAIMER, TEMPLATES_DIR, _css, _environment, theme_css

KEY_LINE_MAX = 40


@dataclass(frozen=True)
class TitleCard:
    publisher: str
    date: str
    headline: str
    summary: str
    source_id: str
    domain: str


def key_line(slide: Slide) -> str:
    """The one line of slide text worth keeping on top of footage."""
    body = slide.body
    text = {
        Layout.TITLE: lambda: body.subtitle,
        Layout.BULLETS: lambda: " · ".join(body.items[:3]),
        Layout.BIG_NUMBER: lambda: f"{body.value}{body.unit}　{body.caption}".strip(),
        Layout.COMPARE: lambda: f"{body.left.label} vs {body.right.label}",
        Layout.TIMELINE: lambda: f"{body.events[0].when} → {body.events[-1].when}",
        Layout.QUOTE: lambda: f"「{body.text}」",
    }[slide.layout]()
    return text if len(text) <= KEY_LINE_MAX else text[: KEY_LINE_MAX - 1] + "…"


def title_card_for(deck: Deck, slide: Slide) -> TitleCard:
    if slide.media is None or not slide.media.source_id:
        raise ValueError(f"slide {slide.id!r} has no title_card source_id")
    source = deck.source_by_id(slide.media.source_id)
    domain = urlparse(source.url).netloc.removeprefix("www.") if source.url else ""
    summary = slide.media.summary or key_line(slide)
    return TitleCard(
        publisher=source.publisher or domain or "媒體待補",
        date=source.published or "日期待補",
        headline=slide.media.headline or source.title,
        summary=summary,
        source_id=source.id,
        domain=domain,
    )


def _render(
    deck: Deck, section: Section, slide: Slide, index: int, kind: str,
    style: str | None = None, brand: str | None = None, **extra: object,
) -> str:
    template = _environment().get_template("media/frame.html.j2")
    return template.render(
        deck=deck,
        section=section,
        slide=slide,
        index=index,
        total=len(deck.slides),
        kind=kind,
        sources=[deck.source_by_id(sid).title for sid in slide.source_ids],
        disclaimer=DISCLAIMER[deck.category],
        base_css=_css("base.css"),
        theme_css=theme_css(deck, style, brand),
        media_css=(TEMPLATES_DIR / "media" / "media.css").read_text(encoding="utf-8"),
        animation=extra.pop("animation", None),
        animate_js=_css("animate.js"),
        **extra,
    )


def overlay_html(
    deck: Deck, section: Section, slide: Slide, index: int, style: str | None = None,
    brand: str | None = None,
) -> str:
    """Transparent page: top bar, lower-third (heading + key line), meta row."""
    line = key_line(slide)
    return _render(deck, section, slide, index, "overlay", style=style, brand=brand,
                   key_line="" if line == slide.heading else line)


def title_card_html(deck: Deck, section: Section, slide: Slide, index: int) -> str:
    """News headline card with an entrance animation (``__anim.seek``)."""
    return _render(deck, section, slide, index, "title_card",
                   card=title_card_for(deck, slide), animation="title_card")


def placeholder_html(
    deck: Deck, section: Section, slide: Slide, index: int, expected_path: str,
) -> str:
    """Loud stand-in shown until the AI illustration exists."""
    prompt = slide.media.prompt if slide.media else ""
    return _render(deck, section, slide, index, "placeholder",
                   expected_path=expected_path, prompt=prompt[:320])
