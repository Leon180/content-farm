"""Media-panel reworks of AI illustrations (orchestrator decision 2026-10-19, 九尾狐 s08b fake seal)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from content_farm.explainer.ai_images import AI_IMAGE_DIR
from content_farm.review.gate import _rework
from content_farm.review.prompt_rework import (attempts, contradictions, prompt_only_problems, reject_images,
                                               seed_for)
from content_farm.review.verdicts import media
from content_farm.review.config import load_review

STYLE = "Traditional East Asian ink wash painting, illustration, no text, no seal."
S08B = "a fox at a palace gate, a large red square seal impression floating in the sky like a stamp of approval"


def test_contradiction_catches_the_s08b_seal_and_nothing_harmless():
    assert contradictions(f"{STYLE} {S08B}") == ["seal"]
    assert contradictions(f"{STYLE} a white fox with nine tails on a hill at dusk") == []
    assert contradictions("no texts, a scroll with text") == ["text"]


def _deck() -> dict:
    slides = [{"id": "s08b", "narration": "旁白一。", "media": {"kind": "ai_image", "prompt": S08B, "motion": "parallax"}},
              {"id": "s09", "narration": "旁白二。", "media": {"kind": "ai_image", "prompt": "white fox"}},
              {"id": "s10", "narration": "旁白三。", "media": {"kind": "slide"}}]
    return {"title": "t", "sections": [{"title": "章", "slides": slides}]}


def test_prompt_only_accepts_a_clean_prompt_edit():
    before, after = _deck(), _deck()
    after["sections"][0]["slides"][0]["media"]["prompt"] = "a fox at a palace gate under a golden sky"
    assert prompt_only_problems(before, after, {"s08b"}, STYLE) == []


def test_prompt_only_refuses_narration_other_slides_other_fields_and_contradictions():
    before = _deck()
    narration = copy.deepcopy(before)
    narration["sections"][0]["slides"][0]["narration"] = "改了旁白。"
    other = copy.deepcopy(before)
    other["sections"][0]["slides"][1]["media"]["prompt"] = "black fox"
    motion = copy.deepcopy(before)
    motion["sections"][0]["slides"][0]["media"]["motion"] = "wan"
    assert any("旁白" in p for p in prompt_only_problems(before, narration, {"s08b"}, STYLE))
    assert any("s09 沒被點名" in p for p in prompt_only_problems(before, other, {"s08b"}, STYLE))
    assert any("prompt 以外" in p for p in prompt_only_problems(before, motion, {"s08b"}, STYLE))
    assert any("自相矛盾" in p for p in prompt_only_problems(before, copy.deepcopy(before), {"s08b"}, STYLE))


def test_rejected_images_move_aside_and_the_next_draw_gets_a_new_seed(tmp_path: Path):
    image_dir = tmp_path / AI_IMAGE_DIR
    image_dir.mkdir(parents=True)
    (image_dir / "s08b.png").write_bytes(b"png")
    (image_dir / "s08b.json").write_text("{}", encoding="utf-8")
    (image_dir / "s08.png").write_bytes(b"other slide")
    assert seed_for(tmp_path, "s08b", 42) == 42
    moved = reject_images(tmp_path, ["s08b"])
    assert len(moved) == 2 and not (image_dir / "s08b.png").exists() and (image_dir / "s08.png").exists()
    assert attempts(tmp_path, "s08b") == 1 and seed_for(tmp_path, "s08b", 42) == 43
    (image_dir / "s08b.png").write_bytes(b"png 2")
    reject_images(tmp_path, ["s08b"])
    assert seed_for(tmp_path, "s08b", 42) == 44


def test_the_media_panel_routes_ai_image_issues_to_a_prompt_only_deck_rework(tmp_path: Path):
    (tmp_path / "deck.json").write_text(json.dumps(_deck(), ensure_ascii=False), encoding="utf-8")
    (tmp_path / "review").mkdir()
    issues = [{"ref": {"target": "media", "item": "s08b"}, "category": "compliance", "severity": "high",
               "problem": "偽漢字紅印", "fix": "去掉印章", "evidence": "s08b", "who": "compliance-1",
               "caused_by": "illustrate"},
              {"ref": {"target": "media", "item": "credits.json"}, "category": "compliance", "severity": "low",
               "problem": "授權欄", "fix": "補", "evidence": "credits", "who": "compliance-1", "caused_by": "media"}]
    card = {"round": 1, "label": "round-1", "verdict": {"pass": False, "reasons": ["x"], "issues": issues}}
    plan = _rework(tmp_path, "media", "media", card, "illustrate")
    assert plan["prompt_only"] == ["s08b"] and plan["restart"] == "deck"
    assert "media" in plan["steps"]                      # the credits item still goes to the media step


def test_the_compliance_reason_carries_a_summary():
    stage = load_review().stages["media"]
    from content_farm.review.verdicts import Seat

    seat = Seat("compliance-1", "compliance", "compliance", False, True, {
        "assets": [], "issues": [{"ref": {"target": "media", "item": "s08b"}, "category": "compliance",
                                  "severity": "high", "problem": "天空浮著偽漢字紅色方印", "fix": "f",
                                  "evidence": "s08b"}]})
    verdict = media(stage, [seat], corpus="s08b")
    assert not verdict.passed and any("s08b：天空浮著偽漢字紅色方印" in r for r in verdict.reasons), verdict.reasons
