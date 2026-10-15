"""deck.json v2 ``media`` field: per-kind validation, lint rules, script hand-off."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from content_farm.explainer.deck import Animation, Deck, MediaKind
from content_farm.explainer.lint import lint_deck
from content_farm.explainer.to_script import deck_to_script
from tests.unit.explainer_helpers import deck_dict, slide


def _with_media(media: dict[str, Any] | None, layout: str = "bullets", **extra: Any) -> Deck:
    data = deck_dict()
    overrides: dict[str, Any] = dict(extra)
    if media is not None:
        overrides["media"] = media
    data["sections"][1]["slides"].append(slide("m1", layout, **overrides))
    return Deck.model_validate(data)


def _m1(deck: Deck):  # noqa: ANN202 - test helper
    return next(s for s in deck.slides if s.id == "m1")


def _codes(deck: Deck) -> list[str]:
    return [issue.code for issue in lint_deck(deck)]


class TestMediaValidation:
    def test_absent_media_defaults_to_slide(self) -> None:
        deck = _with_media(None)
        assert _m1(deck).media_kind == MediaKind.SLIDE

    @pytest.mark.parametrize(("kind", "field"), [
        ("title_card", "source_id"),
        ("stock", "query"),
        ("ai_image", "prompt"),
        ("animated", "animation"),
    ])
    def test_kind_requires_its_field(self, kind: str, field: str) -> None:
        with pytest.raises(ValidationError, match=f"requires '{field}'"):
            _with_media({"kind": kind})

    def test_valid_kinds(self) -> None:
        assert _m1(_with_media({"kind": "stock", "query": "wafer"})).media_kind == "stock"
        assert _m1(_with_media({"kind": "ai_image", "prompt": "a cat"})).media.prompt
        deck = _with_media({"kind": "title_card", "source_id": "s1"})
        assert _m1(deck).media.source_id == "s1"

    def test_stock_keywords_are_lowercase_words(self) -> None:
        media = _m1(_with_media({"kind": "stock", "query": "wafer", "keywords": ["wafer", "clean-room"]})).media
        assert media.keywords == ("wafer", "clean-room")
        with pytest.raises(ValidationError):
            _with_media({"kind": "stock", "query": "wafer", "keywords": ["Wafer Fab"]})

    def test_title_card_source_must_exist(self) -> None:
        with pytest.raises(ValidationError, match="media.source_id 'nope'"):
            _with_media({"kind": "title_card", "source_id": "nope"})

    def test_unknown_kind_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _with_media({"kind": "screenshot"})

    def test_extra_media_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _with_media({"kind": "stock", "query": "x", "url": "https://example.com"})

    @pytest.mark.parametrize(("animation", "layout"), [
        ("count_up", "big_number"),
        ("grow_bars", "compare"),
        ("grow_bars", "bullets"),
        ("reveal_list", "timeline"),
        ("draw_line", "timeline"),
        ("fade_in", "quote"),
    ])
    def test_animation_fits_layout(self, animation: str, layout: str) -> None:
        deck = _with_media({"kind": "animated", "animation": animation}, layout)
        assert _m1(deck).animation == Animation(animation)

    @pytest.mark.parametrize(("animation", "layout"), [
        ("count_up", "bullets"),
        ("draw_line", "compare"),
        ("reveal_list", "quote"),
    ])
    def test_animation_layout_mismatch(self, animation: str, layout: str) -> None:
        with pytest.raises(ValidationError, match="does not fit layout"):
            _with_media({"kind": "animated", "animation": animation}, layout)

    def test_default_animation_per_layout(self) -> None:
        deck = _with_media({"kind": "stock", "query": "fab"}, "timeline")
        assert _m1(deck).animation == Animation.DRAW_LINE

    def test_source_published_format(self) -> None:
        data = deck_dict()
        data["sources"][0]["published"] = "2026/10/01"
        with pytest.raises(ValidationError):
            Deck.model_validate(data)
        data["sources"][0]["published"] = "2026-10-01"
        assert Deck.model_validate(data).sources[0].published == "2026-10-01"


class TestMediaLint:
    def test_three_plain_slides_in_a_row_warns(self) -> None:
        # helper deck: a1, b1, b2 are plain → third one triggers
        codes = _codes(Deck.model_validate(deck_dict()))
        assert "plain-slide-run" in codes

    def test_plain_run_broken_by_media(self) -> None:
        data = deck_dict()
        data["sections"][1]["slides"][0]["media"] = {"kind": "stock", "query": "chip"}
        data["sections"][2]["slides"][0]["media"] = {"kind": "ai_image", "prompt": "cat"}
        codes = _codes(Deck.model_validate(data))
        assert "plain-slide-run" not in codes

    def test_footage_share_below_20_percent_warns(self) -> None:
        data = deck_dict()
        data["sections"][1]["slides"][0]["media"] = {"kind": "animated", "animation": "count_up"}
        assert "footage-share" in _codes(Deck.model_validate(data))

    def test_footage_share_met(self) -> None:
        data = deck_dict()  # 4 slides → 1 stock = 25%
        data["sections"][1]["slides"][1]["media"] = {"kind": "stock", "query": "chip"}
        assert "footage-share" not in _codes(Deck.model_validate(data))

    def test_title_card_without_publisher_warns(self) -> None:
        deck = _with_media({"kind": "title_card", "source_id": "s1"})
        assert "title-card-meta" in _codes(deck)

    def test_title_card_with_publisher_ok(self) -> None:
        data = deck_dict()
        data["sources"][0].update(publisher="經濟日報", published="2026-10-01")
        data["sections"][1]["slides"].append(
            slide("m1", media={"kind": "title_card", "source_id": "s1"}))
        assert "title-card-meta" not in _codes(Deck.model_validate(data))


class TestScriptHandOff:
    def test_media_lands_in_visual_hint(self) -> None:
        data = deck_dict()
        data["sections"][1]["slides"][0]["media"] = {"kind": "stock", "query": "wafer fab"}
        data["sections"][1]["slides"][1]["media"] = {"kind": "ai_image", "prompt": "a cat"}
        data["sections"][2]["slides"][0]["media"] = {"kind": "title_card", "source_id": "s1"}
        script = deck_to_script(Deck.model_validate(data))
        hints = [s.visual_hint for s in script.scenes]
        assert hints[0].style == "slide" and hints[0].description == "title:a1"
        assert hints[1].style == "stock" and hints[1].keywords == ("wafer fab",)
        assert hints[1].source_preference == "stock"
        assert hints[2].style == "ai_image" and hints[2].description == "compare:b2|a cat"
        assert hints[2].source_preference == "ai"
        assert hints[3].style == "title_card" and hints[3].description.endswith("|source:s1")

    def test_animated_hint_names_animation(self) -> None:
        deck = _with_media({"kind": "animated", "animation": "reveal_list"})
        hint = deck_to_script(deck).scenes[3].visual_hint
        assert hint.style == "animated" and hint.description.endswith("|reveal_list")
