"""Slide HTML building (pure) and headless rendering (needs playwright + chromium)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image

from content_farm.explainer.deck import BulletsBody, Deck, Layout, Slide
from content_farm.explainer.pages import build_pages, mascot_uri
from tests.unit.explainer_helpers import NARRATION, deck_dict, slide

ROOT = Path(__file__).resolve().parents[2]


def _deck(**overrides: object) -> Deck:
    return Deck.model_validate(deck_dict(**overrides))


class TestBuildPages:
    def test_one_page_per_slide_in_order(self) -> None:
        pages = build_pages(_deck())
        assert [p.stem for p in pages] == ["slide_001", "slide_002", "slide_003", "slide_004"]
        assert [p.slide.id for p in pages] == ["a1", "b1", "b2", "c1"]

    def test_theme_follows_category(self) -> None:
        tech = build_pages(_deck())[0].html
        knowledge = build_pages(_deck(category="knowledge", as_of=None))[0].html
        assert "#ff8a1f" in tech and "theme-tech" in tech
        assert "Songti TC" in knowledge and "theme-knowledge" in knowledge

    def test_footer_as_of_sources_and_disclaimer(self) -> None:
        html = build_pages(_deck())[1].html  # b1 cites s1
        assert '<span class="asof">資料截至 2026-10</span>' in html
        assert '<span class="sources">來源：年報</span>' in html
        assert '<span class="disclaimer">非投資建議</span>' in html
        knowledge = build_pages(_deck(category="knowledge", as_of=None))[1].html
        assert 'class="asof"' not in knowledge and 'class="disclaimer"' not in knowledge

    def test_draft_badge_only_when_draft(self) -> None:
        assert "示意數字・待查證" not in build_pages(_deck())[0].html
        assert "示意數字・待查證" in build_pages(_deck(draft_data=True))[0].html

    def test_text_is_escaped(self) -> None:
        data = deck_dict()
        data["sections"][0]["slides"][0]["heading"] = "<script>x</script>"
        html = build_pages(Deck.model_validate(data))[0].html
        assert "<script>x</script>" not in html
        assert "&lt;script&gt;" in html

    def test_mascot_slot_empty_without_asset(self, tmp_path: Path) -> None:
        data = deck_dict()
        data["sections"][0]["slides"][0]["mascot"] = {"pose": "smug"}
        deck = Deck.model_validate(data)
        assert 'class="mascot"' not in build_pages(deck, mascot_dir=tmp_path)[0].html
        assert 'class="mascot"' not in build_pages(deck, mascot_dir=None)[0].html

    def test_mascot_slot_filled_with_asset(self, tmp_path: Path) -> None:
        Image.new("RGBA", (10, 10)).save(tmp_path / "point.png")
        data = deck_dict()
        data["sections"][0]["slides"][0]["mascot"] = {"pose": "point"}
        html = build_pages(Deck.model_validate(data), mascot_dir=tmp_path)[0].html
        assert 'class="mascot"' in html
        assert (tmp_path / "point.png").resolve().as_uri() in html

    def test_mascot_uri_none_for_slide_without_mascot(self, tmp_path: Path) -> None:
        assert mascot_uri(tmp_path, _deck().slides[0]) is None

    def test_every_layout_renders(self) -> None:
        for layout in Layout:
            data = deck_dict()
            data["sections"][0]["slides"] = [slide("x", layout.value)]
            html = build_pages(Deck.model_validate(data))[0].html
            assert f"layout-{layout.value}" in html


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as pw:
            pw.chromium.launch().close()
    except Exception:  # noqa: BLE001 — any launch failure means "skip", not "fail"
        return False
    return True


needs_browser = pytest.mark.skipif(
    not _chromium_available(), reason="playwright chromium not installed (pip install -e .[browser])",
)


@needs_browser
class TestRenderInBrowser:
    def test_renders_png_and_contact_sheet(self, tmp_path: Path) -> None:
        from content_farm.explainer.render import make_contact_sheet, render_pages

        rendered = render_pages(build_pages(_deck(draft_data=True)), tmp_path)
        assert [r.png_path.name for r in rendered] == [
            "slide_001.png", "slide_002.png", "slide_003.png", "slide_004.png",
        ]
        for r in rendered:
            with Image.open(r.png_path) as img:
                assert img.size == (1920, 1080)
            assert r.problems == ()
        sheet = make_contact_sheet(rendered, tmp_path / "contact_sheet.png")
        with Image.open(sheet) as img:
            assert img.width > 1000 and img.height > 600

    def test_overflow_fails_and_names_the_slide(self, tmp_path: Path) -> None:
        from content_farm.explainer.render import SlideOverflowError, render_pages

        deck = _deck()
        # Bypass schema limits to force a too-tall bullets slide in position 3.
        crowded = Slide.model_construct(
            id="crowded", layout=Layout.BULLETS, heading="塞爆的一頁",
            body=BulletsBody.model_construct(items=tuple(f"第 {i} 點很長很長很長" for i in range(12))),
            narration=NARRATION, source_ids=(), beat=None, mascot=None, notes="",
        )
        sections = list(deck.sections)
        sections[1] = sections[1].model_copy(update={"slides": (sections[1].slides[0], crowded)})
        deck = deck.model_copy(update={"sections": tuple(sections)})

        with pytest.raises(SlideOverflowError) as info:
            render_pages(build_pages(deck), tmp_path)
        failed = info.value.failed
        assert [(r.index, r.slide_id) for r in failed] == [(3, "crowded")]
        assert "slide 03 (crowded, bullets)" in str(info.value)
        assert (tmp_path / "slide_003.png").is_file()  # still written for inspection


def _load_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("render_slides", ROOT / "scripts/render_slides.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCli:
    def test_invalid_deck_exit_1(self, tmp_path: Path) -> None:
        (tmp_path / "deck.json").write_text(json.dumps(deck_dict(as_of=None)), encoding="utf-8")
        assert _load_cli().main(["--run-dir", str(tmp_path)]) == 1

    @needs_browser
    def test_run_dir_end_to_end(self, tmp_path: Path) -> None:
        (tmp_path / "deck.json").write_text(
            json.dumps(deck_dict(), ensure_ascii=False), encoding="utf-8",
        )
        assert _load_cli().main(["--run-dir", str(tmp_path)]) == 0
        assert (tmp_path / "slides" / "contact_sheet.png").is_file()
        assert len(list((tmp_path / "slides").glob("slide_*.png"))) == 4
