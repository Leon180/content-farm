"""Shot language layers, neighbouring-size lint, channel style files (quality v5 items 3 and 4)."""

from __future__ import annotations

from typing import Any

import pytest

from content_farm.explainer import shot_language, style_file
from content_farm.explainer.deck import Deck, Media
from content_farm.explainer.illustrate import Settings, illustrate, requests_for, style_for
from content_farm.explainer.lint import lint_deck
from content_farm.production.channels import load_all, load_channel
from tests.unit.explainer_helpers import deck_dict, slide


def _ai(sid: str, prompt: str = "a squid in dark water", layout: str = "bullets", **media: Any) -> dict[str, Any]:
    return slide(sid, layout, media={"kind": "ai_image", "prompt": prompt, **media})


def _deck(slides: list[dict[str, Any]]) -> Deck:
    sections = [{"title": "甲", "slides": slides}, {"title": "乙", "slides": [_ai("x1", "quote", layout="quote")]},
                {"title": "丙", "slides": [_ai("y1", "tail", layout="quote", shot_size="close")]}]
    return Deck.model_validate(deck_dict(sections=sections))


def _codes(deck: Deck) -> list[str]:
    return [i.code for i in lint_deck(deck)]


def test_size_is_explicit_or_read_from_the_prompt_words() -> None:
    assert shot_language.shot_size_of(Media(kind="ai_image", prompt="x", shot_size="close")).value == "close"
    assert shot_language.shot_size_of(Media(kind="ai_image", prompt="A wide shot of a trench")).value == "wide"
    assert shot_language.shot_size_of(Media(kind="ai_image", prompt="macro detail of a tentacle")).value == "close"
    assert shot_language.shot_size_of(Media(kind="ai_image", prompt="a squid in dark water")) is None


def test_neighbouring_pictures_with_the_same_size_are_a_lint_error() -> None:
    same = _deck([_ai("a1", shot_size="wide"), _ai("a2", "other scene", shot_size="wide")])
    assert "shot-size-repeat" in _codes(same)
    varied = _deck([_ai("a1", shot_size="wide"), _ai("a2", "other scene", shot_size="close")])
    assert "shot-size-repeat" not in _codes(varied)
    unspecified = _deck([_ai("a1"), _ai("a2", "another squid")])
    assert "shot-size-repeat" not in _codes(unspecified)         # unknown sizes are never a repeat


def test_prompt_layers_are_composed_in_order_and_do_not_repeat_what_the_prompt_says() -> None:
    media = Media(kind="ai_image", prompt="a lantern fish", shot_size="close", lighting="cold rim light")
    assert shot_language.compose_prompt("STYLE.", media) == (
        "STYLE. close-up detail filling the frame, a lantern fish, lighting: cold rim light")
    named = Media(kind="ai_image", prompt="close-up of a lantern fish", shot_size="close")
    assert "close-up detail" not in shot_language.compose_prompt("STYLE.", named)


def test_camera_layer_becomes_the_motion_prompt_only_when_none_is_written() -> None:
    assert shot_language.motion_prompt_for(Media(kind="ai_image", prompt="x", camera="push")) == "slow push-in"
    both = Media(kind="ai_image", prompt="x", camera="push", motion_prompt="drift through snow")
    assert shot_language.motion_prompt_for(both) == "drift through snow"
    assert shot_language.motion_prompt_for(Media(kind="ai_image", prompt="x")) == ""


def test_shot_fields_are_refused_outside_ai_image() -> None:
    with pytest.raises(ValueError):
        Media(kind="slide", shot_size="close")


def test_requests_use_the_composed_prompt_and_a_banned_term_is_refused(tmp_path) -> None:
    deck = _deck([_ai("a1", shot_size="wide")])
    settings = Settings("flux2-klein-4b", "STYLE.", 1, 64, 64, ("seal",))
    assert requests_for(deck, settings)[0].prompt.startswith("STYLE. wide establishing shot")
    bad = _deck([_ai("a1", "a red seal on paper")])

    class Boom:
        name = "boom"

        def generate(self, request, out):
            raise AssertionError("must not load a model for a refused prompt")

    with pytest.raises(ValueError, match="banned by the channel style file"):
        illustrate(bad, tmp_path, settings, Boom())
    ok = _deck([_ai("a1", "a scroll, no seal")])
    with pytest.raises(AssertionError):                     # "no seal" is allowed, so it reaches the provider
        illustrate(ok, tmp_path, settings, Boom())


def test_style_file_parse_prefix_and_forbidden_detection() -> None:
    guide = style_file.parse("t", "# t\n## 畫風\n- ink wash\n## 色彩\n- grey\n## 構圖\n- empty paper\n## 禁用\n- text\n- seal\n")
    assert guide.prefix() == "ink wash, grey, empty paper, illustration, not a photograph, no text, no seal."
    assert guide.forbidden_in("a poster with text on it") == ["text"]
    assert guide.forbidden_in("a scroll, no text, without seal") == []
    with pytest.raises(style_file.StyleFileError):
        style_file.parse("t", "## 畫風\n- a\n")                       # colour section missing
    with pytest.raises(style_file.StyleFileError):
        style_file.parse("t", "## 其他\n- a\n")


def test_every_channel_with_ai_images_has_a_valid_style_file_and_it_is_used() -> None:
    for channel in load_all():
        code = channel.code
        if not channel.media.ai_image:
            continue
        guide = style_file.load(code)
        assert guide is not None, f"channels/styles/{code}.md missing"
        assert style_for(channel)[0] == guide.prefix() and "no text" in guide.prefix()


def test_a_channel_can_switch_the_style_file_off() -> None:
    channel = load_channel("yokai")
    off = channel.model_copy(update={"quality": channel.quality.model_copy(update={"style_file": False})})
    assert style_for(off) == (channel.ai_illustration.style_prefix, ())
