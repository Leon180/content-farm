"""``media`` slide hint: schema only (rendering belongs to the visual worker)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from content_farm.explainer.deck import Deck
from content_farm.explainer.media import Media
from tests.unit.explainer_helpers import deck_dict


def _with_media(media: dict[str, Any]) -> dict[str, Any]:
    data = deck_dict()
    data["sections"][1]["slides"][0]["media"] = media
    return data


class TestAccepts:
    def test_media_is_optional(self) -> None:
        assert all(s.media is None for s in Deck.model_validate(deck_dict()).slides)

    def test_kind_defaults_to_slide(self) -> None:
        assert Media().kind == "slide"

    @pytest.mark.parametrize("media", [
        {"kind": "slide"},
        {"kind": "stock", "query": "semiconductor cleanroom wafer"},
        {"kind": "ai_image", "prompt": "a cat inspecting a silicon wafer"},
        {"kind": "animated", "animation": "count_up"},
        {"kind": "title_card", "headline": "台積電擴產", "source_id": "s1"},
    ])
    def test_each_kind_with_its_required_field(self, media: dict[str, Any]) -> None:
        deck = Deck.model_validate(_with_media(media))
        assert deck.slides[1].media is not None
        assert deck.slides[1].media.kind == media["kind"]


class TestRejects:
    @pytest.mark.parametrize(("media", "field"), [
        ({"kind": "stock"}, "query"),
        ({"kind": "ai_image", "prompt": "  "}, "prompt"),
        ({"kind": "animated"}, "animation"),
        ({"kind": "title_card", "source_id": "s1"}, "headline"),
        ({"kind": "title_card", "headline": "標題"}, "source_id"),
    ])
    def test_missing_required_field(self, media: dict[str, Any], field: str) -> None:
        with pytest.raises(ValidationError, match=field):
            Deck.model_validate(_with_media(media))

    def test_unknown_kind(self) -> None:
        with pytest.raises(ValidationError):
            Deck.model_validate(_with_media({"kind": "hologram"}))

    def test_extra_field(self) -> None:
        with pytest.raises(ValidationError):
            Deck.model_validate(_with_media({"kind": "slide", "colour": "red"}))

    def test_title_card_source_must_exist(self) -> None:
        media = {"kind": "title_card", "headline": "標題", "source_id": "nope"}
        with pytest.raises(ValidationError, match="media cites unknown source_id"):
            Deck.model_validate(_with_media(media))

    def test_animation_name_is_an_identifier(self) -> None:
        with pytest.raises(ValidationError):
            Deck.model_validate(_with_media({"kind": "animated", "animation": "../x"}))
