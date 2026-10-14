"""deck.json schema, lint rules and the deck → script.json conversion."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pydantic import ValidationError

from content_farm.explainer.deck import (
    BigNumberBody,
    Category,
    Deck,
    Layout,
    estimate_seconds,
    visible_len,
)
from content_farm.explainer.lint import lint_deck
from content_farm.explainer.to_script import deck_to_script
from content_farm.script_gen.schemas import Script
from content_farm.types import GenreTemplate, Orientation, VideoLength
from tests.unit.explainer_helpers import NARRATION, deck_dict, slide

ROOT = Path(__file__).resolve().parents[2]


def _codes(deck: Deck) -> set[str]:
    return {i.code for i in lint_deck(deck)}


class TestSchemaAccepts:
    def test_minimal_deck(self) -> None:
        deck = Deck.model_validate(deck_dict())
        assert deck.category == Category.TECH
        assert [s.id for s in deck.slides] == ["a1", "b1", "b2", "c1"]
        assert isinstance(deck.slides[1].body, BigNumberBody)

    def test_category_defaults_to_tech(self) -> None:
        data = deck_dict()
        del data["category"]
        assert Deck.model_validate(data).category == Category.TECH

    def test_knowledge_does_not_need_as_of(self) -> None:
        Deck.model_validate(deck_dict(category="knowledge", as_of=None))

    def test_mascot_pose_optional(self) -> None:
        data = deck_dict()
        data["sections"][0]["slides"][0]["mascot"] = {"pose": "point"}
        assert Deck.model_validate(data).slides[0].mascot.pose == "point"  # type: ignore[union-attr]

    def test_every_layout_has_a_body_model(self) -> None:
        for layout in Layout:
            data = deck_dict()
            data["sections"][0]["slides"] = [slide("x", layout.value)]
            assert Deck.model_validate(data).slides[0].layout == layout


class TestSchemaRejects:
    @pytest.mark.parametrize("category", ["ai", "tech"])
    def test_ai_and_tech_require_as_of(self, category: str) -> None:
        with pytest.raises(ValidationError, match="requires as_of"):
            Deck.model_validate(deck_dict(category=category, as_of=None))

    def test_bad_as_of_format(self) -> None:
        with pytest.raises(ValidationError):
            Deck.model_validate(deck_dict(as_of="2026/10"))

    def test_fewer_than_three_sections(self) -> None:
        data = deck_dict()
        data["sections"] = data["sections"][:2]
        with pytest.raises(ValidationError):
            Deck.model_validate(data)

    def test_unknown_source_id(self) -> None:
        data = deck_dict()
        data["sections"][1]["slides"][0]["source_ids"] = ["nope"]
        with pytest.raises(ValidationError, match="unknown source_ids"):
            Deck.model_validate(data)

    def test_duplicate_slide_id(self) -> None:
        data = deck_dict()
        data["sections"][2]["slides"][0]["id"] = "a1"
        with pytest.raises(ValidationError, match="duplicate slide id"):
            Deck.model_validate(data)

    @pytest.mark.parametrize("narration", ["太短了", "長" * 221])
    def test_narration_length(self, narration: str) -> None:
        data = deck_dict()
        data["sections"][0]["slides"][0]["narration"] = narration
        with pytest.raises(ValidationError, match="narration has"):
            Deck.model_validate(data)

    def test_heading_too_long(self) -> None:
        data = deck_dict()
        data["sections"][0]["slides"][0]["heading"] = "字" * 25
        with pytest.raises(ValidationError):
            Deck.model_validate(data)

    def test_body_must_match_layout(self) -> None:
        data = deck_dict()
        data["sections"][0]["slides"][0] = slide("x", "bullets", body={"value": "1"})
        with pytest.raises(ValidationError):
            Deck.model_validate(data)

    def test_bullet_count_and_length(self) -> None:
        data = deck_dict()
        data["sections"][0]["slides"][0] = slide("x", "bullets", body={"items": ["a", "b"]})
        with pytest.raises(ValidationError):
            Deck.model_validate(data)
        data["sections"][0]["slides"][0] = slide("x", "bullets", body={"items": ["字" * 19] * 3})
        with pytest.raises(ValidationError):
            Deck.model_validate(data)

    def test_unsupported_layout(self) -> None:
        data = deck_dict()
        data["sections"][0]["slides"][0]["layout"] = "custom_html"
        with pytest.raises(ValidationError):
            Deck.model_validate(data)

    def test_gossip_needs_sources(self) -> None:
        data = deck_dict()
        data["sections"][0]["slides"][0]["beat"] = "gossip"
        with pytest.raises(ValidationError, match="gossip beat must cite"):
            Deck.model_validate(data)

    def test_bad_mascot_pose(self) -> None:
        data = deck_dict()
        data["sections"][0]["slides"][0]["mascot"] = {"pose": "../../etc"}
        with pytest.raises(ValidationError):
            Deck.model_validate(data)

    def test_extra_fields_forbidden(self) -> None:
        data = deck_dict()
        data["sections"][0]["slides"][0]["colour"] = "red"
        with pytest.raises(ValidationError):
            Deck.model_validate(data)


class TestLint:
    def test_short_sample_deck_warns_but_validates(self) -> None:
        codes = _codes(Deck.model_validate(deck_dict()))
        assert {"slide-count", "duration"} <= codes

    def test_draft_data_flagged(self) -> None:
        assert "draft-data" in _codes(Deck.model_validate(deck_dict(draft_data=True)))

    def test_beat_gap_and_repeat(self) -> None:
        data = deck_dict()
        data["sections"][1]["slides"] = [slide(f"g{i}") for i in range(5)]
        assert "beat-gap" in _codes(Deck.model_validate(data))
        data["sections"][1]["slides"][0]["beat"] = "joke"
        data["sections"][1]["slides"][1]["beat"] = "joke"
        assert "beat-repeat" in _codes(Deck.model_validate(data))

    def test_bullets_heavy_and_variety(self) -> None:
        data = deck_dict()
        for section in data["sections"]:
            section["slides"] = [slide(f"{section['title']}{i}") for i in range(2)]
        codes = _codes(Deck.model_validate(data))
        assert {"bullets-heavy", "layout-variety"} <= codes

    def test_unsourced_number(self) -> None:
        data = deck_dict()
        data["sections"][2]["slides"][0]["narration"] = NARRATION + "毛利率大約 59%。"
        assert "unsourced-number" in _codes(Deck.model_validate(data))

    def test_investment_advice(self) -> None:
        data = deck_dict()
        data["sections"][2]["slides"][0]["narration"] = NARRATION + "所以現在該買進嗎？"
        assert "investment-advice" in _codes(Deck.model_validate(data))


class TestDeckToScript:
    def test_one_scene_per_slide_and_one_chapter_per_section(self) -> None:
        deck = Deck.model_validate(deck_dict())
        script = deck_to_script(deck)
        assert [s.scene_number for s in script.scenes] == [1, 2, 3, 4]
        assert [s.chapter_number for s in script.scenes] == [1, 2, 2, 3]
        assert [c.title for c in script.chapters] == ["開場", "本體", "結尾"]
        assert script.chapters[0].start_timestamp == 0.0
        assert script.scenes[1].visual_hint.style == "slide"
        assert script.scenes[1].visual_hint.description == "big_number:b1"

    def test_landscape_knowledge_medium(self) -> None:
        script = deck_to_script(Deck.model_validate(deck_dict()))
        assert script.orientation == Orientation.LANDSCAPE
        assert script.genre == GenreTemplate.KNOWLEDGE
        assert script.target_length == VideoLength.MEDIUM
        assert script.pronunciation_map == {"TSMC": "T S M C"}
        assert script.sources == ("年報 — https://example.com/ar",)

    def test_durations_are_estimates_and_chapters_contiguous(self) -> None:
        script = deck_to_script(Deck.model_validate(deck_dict()))
        per_scene = estimate_seconds(NARRATION)
        assert all(s.duration_seconds == per_scene for s in script.scenes)
        assert script.total_duration_seconds == pytest.approx(per_scene * 4)
        for prev, nxt in zip(script.chapters, script.chapters[1:]):
            assert nxt.start_timestamp == pytest.approx(
                prev.start_timestamp + prev.duration_seconds, abs=0.01,
            )

    def test_round_trips_through_script_schema(self) -> None:
        script = deck_to_script(Deck.model_validate(deck_dict()))
        restored = Script.model_validate(json.loads(json.dumps(script.model_dump(mode="json"))))
        assert restored.scenes == script.scenes

    def test_visible_len_ignores_whitespace(self) -> None:
        assert visible_len("a b\n c　") == 3


def _load_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("deck_to_script", ROOT / "scripts/deck_to_script.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestCli:
    def _write(self, tmp_path: Path, data: dict[str, Any]) -> Path:
        (tmp_path / "deck.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return tmp_path

    def test_writes_script_json(self, tmp_path: Path) -> None:
        run_dir = self._write(tmp_path, deck_dict())
        assert _load_cli().main(["--run-dir", str(run_dir)]) == 0
        script = Script.model_validate_json((run_dir / "script.json").read_text(encoding="utf-8"))
        assert len(script.scenes) == 4

    def test_strict_fails_on_lint(self, tmp_path: Path) -> None:
        run_dir = self._write(tmp_path, deck_dict())
        assert _load_cli().main(["--run-dir", str(run_dir), "--strict"]) == 2
        assert not (run_dir / "script.json").exists()

    def test_invalid_deck_exit_1(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        run_dir = self._write(tmp_path, deck_dict(as_of=None))
        assert _load_cli().main(["--run-dir", str(run_dir)]) == 1
        assert "requires as_of" in capsys.readouterr().err
