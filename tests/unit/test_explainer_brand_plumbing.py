"""brand= reaches every page the media stage renders (overlay, title card, placeholder, animated)."""

from __future__ import annotations

from pathlib import Path

import pytest

from content_farm.explainer.brands import brand_css_path
from content_farm.explainer.cards import overlay_html, placeholder_html, title_card_html
from content_farm.explainer.deck import Media, MediaKind, load_deck
from content_farm.explainer.media_run import MediaOptions, jobs_for
from content_farm.explainer.pages import _css
from content_farm.explainer.timeline import SlideClip

DECK = load_deck(Path(__file__).resolve().parents[2] / "docs" / "examples" / "explainer-cowos" / "deck.json")


def _first(kind: str):
    for section in DECK.sections:
        for slide in section.slides:
            if slide.media_kind.value == kind:
                return section, slide, DECK.slides.index(slide) + 1
    raise LookupError(kind)


def _marker(code: str) -> str:
    """A line unique to the brand stylesheet."""
    brand_lines = set(brand_css_path(code).read_text(encoding="utf-8").splitlines())
    theme_lines = set(_css("themes/tech.css").splitlines())
    return next(line for line in sorted(brand_lines - theme_lines) if len(line.strip()) > 12)


@pytest.mark.parametrize("code", ["chipcat", "yokai"])
def test_cards_use_brand_css(code: str) -> None:
    marker = _marker(code)
    section, slide, index = _first("title_card")
    assert marker in title_card_html(DECK, section, slide, index, brand=code)
    assert marker not in title_card_html(DECK, section, slide, index)
    # The example deck no longer has AI images (2026-10-15); give one slide an ai_image request.
    section, slide, index = _first("stock")
    slide = slide.model_copy(update={"media": Media(kind=MediaKind.AI_IMAGE, prompt="a cat")})
    assert marker in placeholder_html(DECK, section, slide, index, "assets/x.png", brand=code)
    section, slide, index = _first("stock")
    assert marker in overlay_html(DECK, section, slide, index, brand=code)


def test_animated_pages_follow_media_options_brand() -> None:
    clips = [SlideClip(index=i, start_ms=i * 1000, end_ms=(i + 1) * 1000)
             for i in range(1, len(DECK.slides) + 1)]
    marker = _marker("cel")
    jobs = jobs_for(DECK, clips, brand=MediaOptions(brand="cel").brand)
    assert all(marker in job.animated_page.html for job in jobs)
    assert not any(marker in job.animated_page.html for job in jobs_for(DECK, clips))
