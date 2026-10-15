"""Opt-in slide styles: registry, palette parsing, WCAG maths, and that the
category themes are untouched when no style is passed."""

from __future__ import annotations

import pytest

from content_farm.explainer.cards import overlay_html
from content_farm.explainer.deck import Deck
from content_farm.explainer.pages import build_pages
from content_farm.explainer.styles import (
    PALETTE_KEYS,
    STYLES_DIR,
    contrast_ratio,
    contrast_report,
    get_style,
    palette,
    relative_luminance,
    style_codes,
    style_css_path,
)
from tests.unit.explainer_helpers import deck_dict


def _deck(**overrides: object) -> Deck:
    return Deck.model_validate(deck_dict(**overrides))


class TestRegistry:
    def test_ten_styles_each_with_a_stylesheet(self) -> None:
        codes = style_codes()
        assert len(codes) == 10 and len(set(codes)) == 10
        for code in codes:
            assert style_css_path(code).is_file()
        assert sorted(p.stem for p in STYLES_DIR.glob("*.css")) == sorted(codes)

    def test_categories_and_score_are_valid(self) -> None:
        for code in style_codes():
            spec = get_style(code)
            assert spec.categories and set(spec.categories) <= {"ai", "tech", "knowledge"}
            assert 1 <= spec.ai_distance <= 5

    def test_unknown_style_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown style"):
            style_css_path("../tech")


class TestPalette:
    @pytest.mark.parametrize("code", style_codes())
    def test_every_role_defined(self, code: str) -> None:
        colours = palette(code)
        assert tuple(colours) == PALETTE_KEYS
        assert all(v.startswith("#") and len(v) == 7 for v in colours.values())

    @pytest.mark.parametrize("code", style_codes())
    def test_body_text_meets_wcag_aa(self, code: str) -> None:
        report = {row["pair"]: row for row in contrast_report(code)}
        body = next(row for label, row in report.items() if label.startswith("內文"))
        assert body["ratio"] >= 4.5


class TestContrastMaths:
    def test_black_on_white_is_21(self) -> None:
        assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)
        assert contrast_ratio("#ffffff", "#000000") == pytest.approx(21.0)

    def test_known_value(self) -> None:
        # WebAIM: #777777 on white = 4.48:1
        assert contrast_ratio("#777777", "#ffffff") == pytest.approx(4.48, abs=0.01)

    def test_bad_hex(self) -> None:
        with pytest.raises(ValueError):
            relative_luminance("#fff")


class TestThemeSelection:
    def test_default_is_category_theme_unchanged(self) -> None:
        deck = _deck()
        assert build_pages(deck)[0].html == build_pages(deck, style=None)[0].html
        assert "#ff8a1f" in build_pages(deck)[0].html

    def test_style_replaces_theme_but_keeps_template(self) -> None:
        html = build_pages(_deck(), style="newspaper")[0].html
        assert "#ebe2cf" in html and "#ff8a1f" not in html
        assert 'class="topbar"' in html and "theme-tech" in html

    def test_overlay_uses_style(self) -> None:
        deck = _deck()
        section = deck.sections[0]
        plain = overlay_html(deck, section, section.slides[0], 1)
        styled = overlay_html(deck, section, section.slides[0], 1, style="swiss")
        assert "#ff8a1f" in plain and "#d6201a" in styled
