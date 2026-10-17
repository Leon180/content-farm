"""HTML for v2 media frames (pure; no browser): footage overlay, news title card, AI placeholder.

All three share the slide frame (top bar, meta row with 資料截至 / disclaimer,
subtitle safe zone) and the deck theme, so a stock shot or a title card looks
like part of the same video rather than a pasted-in asset.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from content_farm.explainer.deck import Deck, Layout, Section, Slide
from content_farm.explainer.pages import DISCLAIMER, TEMPLATES_DIR, _css, _environment, source_label, theme_css

KEY_LINE_MAX = 40


@dataclass(frozen=True)
class TitleCard:
    publisher: str
    date: str
    headline: str      # the channel's summary line (本頻道摘要)
    summary: str
    source_id: str
    domain: str
    original: str = ""  # the outlet's verbatim headline (媒體原標題); "" = not recorded


def key_line(slide: Slide) -> str:
    """The one line of slide text worth keeping on top of footage."""
    body = slide.body
    if slide.layout == Layout.BULLETS:   # as many whole items as fit — never cut one with 「…」
        kept: list[str] = []
        for item in body.items[:3]:
            if len(" · ".join([*kept, item])) > KEY_LINE_MAX:
                break
            kept.append(item)
        return " · ".join(kept)
    text = {
        Layout.TITLE: lambda: body.subtitle,
        Layout.BIG_NUMBER: lambda: f"{body.value}{body.unit}　{body.caption}".strip(),
        Layout.COMPARE: lambda: f"{body.left.label} vs {body.right.label}",
        Layout.TIMELINE: lambda: f"{body.events[0].when} → {body.events[-1].when}",
        Layout.QUOTE: lambda: f"「{body.text}」",
    }[slide.layout]()
    return text if len(text) <= KEY_LINE_MAX else _cut_at_clause(text, KEY_LINE_MAX)


def _cut_at_clause(text: str, limit: int) -> str:
    """Longest prefix ending at a clause break (no 「…」, CoWoS v3 eval); "" if there is none."""
    cut = max((i for i, ch in enumerate(text[:limit]) if ch in "　，。；：、 "), default=0)
    return text[:cut].rstrip("　，。；：、 ") if cut else ""


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
        original=source.headline,
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
        sources=list(dict.fromkeys(source_label(deck.source_by_id(sid)) for sid in slide.source_ids)),
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
    brand: str | None = None, artwork_caption: str = "", ai_label: str = "", lower_third: bool = True,
) -> str:
    """Transparent page: top bar, lower-third (heading + key line), meta row.

    ``artwork_caption`` names the work on screen (artist, title, year); ``ai_label``
    puts the fixed 「AI 示意圖」 badge in the top-left corner of AI illustrations.
    ``lower_third=False``: no heading box and no footage shade (diagrams draw their own heading).
    """
    line = key_line(slide)
    return _render(deck, section, slide, index, "overlay", style=style, brand=brand,
                   key_line="" if line == slide.heading else line, artwork_caption=artwork_caption,
                   ai_label=ai_label, lower_third=lower_third)


def title_card_html(
    deck: Deck, section: Section, slide: Slide, index: int, brand: str | None = None,
) -> str:
    """News headline card with an entrance animation (``__anim.seek``)."""
    return _render(deck, section, slide, index, "title_card", brand=brand,
                   card=title_card_for(deck, slide), animation="title_card")


def placeholder_html(
    deck: Deck, section: Section, slide: Slide, index: int, expected_path: str,
    brand: str | None = None, tag: str = "AI 插圖待補",
) -> str:
    """Loud stand-in shown until the AI illustration (or artwork) exists."""
    prompt = slide.media.prompt if slide.media else ""
    return _render(deck, section, slide, index, "placeholder", brand=brand,
                   expected_path=expected_path, prompt=prompt[:320], placeholder_tag=tag)
