"""Channel brands: registry, palettes that pass WCAG, the brand= override, and
that decks without a brand render exactly as before."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content_farm.explainer.brands import (
    BRAND_ASSET_DIR,
    BRAND_CSS_DIR,
    brand_codes,
    brand_contrast_report,
    brand_css_path,
    brand_palette,
    get_brand,
)
from content_farm.explainer.cards import overlay_html
from content_farm.explainer.deck import Deck
from content_farm.explainer.pages import build_pages, theme_css
from content_farm.explainer.styles import PALETTE_KEYS, palette_from_css, style_codes
from tests.unit.explainer_helpers import deck_dict

DEMO_DECKS = Path(__file__).resolve().parents[2] / "docs" / "examples" / "brands"


def _deck(**overrides: object) -> Deck:
    return Deck.model_validate(deck_dict(**overrides))


class TestRegistry:
    def test_seven_brands_each_with_stylesheet_assets_and_silhouette(self) -> None:
        codes = brand_codes()
        assert len(codes) == 7 and len(set(codes)) == 7
        assert sorted(p.stem for p in BRAND_CSS_DIR.glob("*.css")) == sorted(codes)
        for code in codes:
            assert brand_css_path(code).is_file()
            assert (BRAND_ASSET_DIR / code / "assets.html.j2").is_file()
            assert (BRAND_ASSET_DIR / "silhouettes" / f"{code}.svg").is_file()

    def test_brands_cite_real_styles(self) -> None:
        for code in brand_codes():
            spec = get_brand(code)
            assert spec.derived_from and set(spec.derived_from) <= set(style_codes())

    def test_unknown_brand_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown brand"):
            brand_css_path("nope")


class TestPalettes:
    @pytest.mark.parametrize("code", brand_codes())
    def test_every_role_present_and_contrast_passes(self, code: str) -> None:
        assert set(brand_palette(code)) == set(PALETTE_KEYS)
        failing = [row for row in brand_contrast_report(code) if not row["ok"]]
        assert failing == []

    def test_brands_do_not_share_a_background_or_accent(self) -> None:
        palettes = [brand_palette(code) for code in brand_codes()]
        assert len({p["bg"] for p in palettes}) == 7
        assert len({p["accent"] for p in palettes}) == 7

    def test_palette_from_css_reports_missing_roles(self) -> None:
        with pytest.raises(ValueError, match="missing palette roles"):
            palette_from_css(":root { --bg: #000000; }", "x")
        with pytest.raises(ValueError, match="no :root"):
            palette_from_css("body {}", "x")


class TestOverride:
    def test_no_brand_keeps_category_theme(self) -> None:
        deck = _deck()
        assert theme_css(deck) == theme_css(deck, None, None)
        assert "brand:" not in build_pages(deck)[0].html

    @pytest.mark.parametrize("code", brand_codes())
    def test_brand_stylesheet_is_embedded(self, code: str) -> None:
        deck = _deck()
        marker = f"brand: {code}"
        assert marker in build_pages(deck, brand=code)[0].html
        section, slide = deck.sections[0], deck.slides[0]
        assert marker in overlay_html(deck, section, slide, 1, brand=code)

    def test_brand_wins_over_style(self) -> None:
        deck = _deck()
        assert theme_css(deck, style="swiss", brand="yokai") == brand_css_path("yokai").read_text(encoding="utf-8")


@pytest.mark.parametrize("code", brand_codes())
def test_demo_decks_validate(code: str) -> None:
    data = json.loads((DEMO_DECKS / f"{code}.json").read_text(encoding="utf-8"))
    deck = Deck.model_validate(data)
    assert len(deck.slides) == 3
