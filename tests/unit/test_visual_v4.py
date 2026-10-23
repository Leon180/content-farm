"""Visual v4 (Leon 2026-10-24): the picture leads, the slide text supports. Lint rules, text-panel frames."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from content_farm.explainer.cards import overlay_html, panel_content
from content_farm.explainer.deck import Deck, Frame
from content_farm.explainer.lint import lint_deck
from tests.unit.explainer_helpers import deck_dict, slide

AI = {"kind": "ai_image", "prompt": "flat editorial illustration, original generic scene"}


def _ai(sid: str, layout: str = "bullets", **media: Any) -> dict[str, Any]:
    return slide(sid, layout, media={**AI, **media})


def _pad(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The deck schema wants >= 3 sections."""
    return sections + [{"title": f"補{n}", "slides": [_ai(f"p{n}", "quote", frame="panel_right")]} for n in range(3 - len(sections))]


def _codes(sections: list[dict[str, Any]]) -> list[str]:
    sections = _pad(sections)
    return [i.code for i in lint_deck(Deck.model_validate(deck_dict(sections=sections)))]


def test_a_section_without_an_ai_picture_is_flagged():
    sections = [{"title": "甲", "slides": [_ai("a1", "title")]}, {"title": "乙", "slides": [slide("b1", "bullets")]},
                {"title": "丙", "slides": [_ai("c1", "quote")]}]
    assert _codes(sections).count("section-no-ai-image") == 1


def test_text_only_pages_are_capped_at_thirty_percent():
    texty = [{"title": "甲", "slides": [_ai("a1", "title"), slide("a2", "bullets"), slide("a3", "compare")]},
             {"title": "乙", "slides": [_ai("b1", "quote", frame="panel_left")]},
             {"title": "丙", "slides": [_ai("c1", "bullets", frame="panel_right")]}]
    assert "text-only-share" in _codes(texty)                       # 2 of 5 = 40 %
    fine = [{"title": "甲", "slides": [_ai("a1", "title"), slide("a2", "bullets"), _ai("a3", "compare", frame="panel_left")]},
            {"title": "乙", "slides": [_ai("b1", "quote", frame="panel_right"), _ai("b2", "big_number")]},
            {"title": "丙", "slides": [_ai("c1", "bullets", frame="panel_left")]}]
    assert "text-only-share" not in _codes(fine) and "section-no-ai-image" not in _codes(fine)  # 1 of 6


def test_consecutive_slides_must_not_share_a_form():
    sections = [{"title": "甲", "slides": [_ai("a1", "title"), _ai("a2", "bullets"), _ai("a3", "bullets", frame="panel_left")]},
                {"title": "乙", "slides": [slide("b1", "bullets"), slide("b2", "bullets")]},
                {"title": "丙", "slides": [_ai("c1", "quote", frame="panel_right")]}]
    repeats = [i.message for i in lint_deck(Deck.model_validate(deck_dict(sections=_pad(sections)))) if i.code == "form-repeat"]
    assert len(repeats) == 2 and "'a2'" in repeats[0] and "'b2'" in repeats[1]       # lower/lower and text:bullets x2


def test_a_long_deck_needs_two_or_three_wan_key_shots():
    slides = [_ai(f"s{i}", "bullets" if i % 2 else "quote", frame="panel_left" if i % 3 else "lower") for i in range(12)]
    assert "wan-shots" in _codes([{"title": "甲", "slides": slides}])
    slides = [{**s, "media": {**s["media"], "motion": "wan", "motion_prompt": "mist drifts"}} if n in (0, 5) else s
              for n, s in enumerate(slides)]
    assert "wan-shots" not in _codes([{"title": "甲", "slides": slides}])


def test_a_wan_shot_must_not_show_a_person_or_face():
    def codes(prompt: str, motion: str = "wan") -> list[str]:
        sections = [{"title": "甲", "slides": [_ai("a1", "quote", prompt=prompt, motion=motion, motion_prompt="mist drifts")]}]
        return _codes(sections)

    assert "wan-face" in codes("A tired animator asleep at a desk, original generic character")
    assert "wan-face" in codes("close-up portrait with a smiling expression")
    assert "wan-face" not in codes("A cluttered desk with two newspapers and a lamp, original generic scene")
    assert "wan-face" not in codes("An empty desk with a lamp, no people, original generic scene")
    assert "wan-face" not in codes("A tired animator asleep at a desk", motion="parallax")   # parallax is fine


def test_wan_prompt_keeps_figures_still_and_adds_a_face_negative():
    from pathlib import Path

    from content_farm.explainer import wan

    request = wan.request_for("s1", Path("x.png"), {"prompt": "a desk"}, "lamp flickers")
    assert "stays perfectly still" in request.prompt and "lamp flickers" in request.prompt
    command = wan.argv(wan.MotionPaths(Path("py"), Path("d"), Path("w")), request, Path("o.mp4"))
    assert command[command.index("--negative-prompt") + 1] == wan.NEGATIVE_PROMPT
    assert "morphing face" in wan.NEGATIVE_PROMPT


def test_frame_only_applies_to_ai_images():
    with pytest.raises(ValidationError, match="frame only applies"):
        Deck.model_validate(deck_dict(sections=[
            {"title": "甲", "slides": [slide("a1", "title", media={"kind": "stock", "query": "chip", "frame": "panel_left"})]},
            {"title": "乙", "slides": [slide("b1", "quote")]}, {"title": "丙", "slides": [slide("c1", "quote")]}]))


@pytest.mark.parametrize(("layout", "big", "first"), [
    ("big_number", "60%", "說明"), ("bullets", "", "第一點"), ("compare", "", "左：a"), ("timeline", "", "1987　成立"),
    ("quote", "", "「引言」"), ("title", "", "副標")])
def test_panel_content_carries_the_slide_body(layout: str, big: str, first: str):
    deck = Deck.model_validate(deck_dict())
    target = Deck.model_validate(deck_dict(sections=[{"title": "甲", "slides": [slide("x1", layout)]},
                                                      {"title": "乙", "slides": [slide("x2", "quote")]},
                                                      {"title": "丙", "slides": [slide("x3", "quote")]}]))
    got_big, lines = panel_content(target.slides[0])
    assert got_big == big and lines[0] == first
    assert deck.slides  # control: the helper deck itself is valid


def test_panel_overlay_replaces_the_lower_third_and_keeps_the_ai_badge():
    deck = Deck.model_validate(deck_dict())
    section, target = deck.sections[1], deck.sections[1].slides[0]
    lower = overlay_html(deck, section, target, 2, ai_label="AI 示意圖")
    panel = overlay_html(deck, section, target, 2, ai_label="AI 示意圖", frame="panel_right")
    assert 'class="lower-third"' in lower and 'class="text-panel' not in lower
    assert 'class="text-panel panel-right"' in panel and 'class="lower-third"' not in panel
    assert "AI 示意圖" in panel and "60%" in panel
    assert Frame.PANEL_LEFT.value == "panel_left"
