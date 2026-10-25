"""Slideshow risk score (quality v5 item 1): per-page points, the deck limit, and the one automatic fix."""

from __future__ import annotations

import json
from typing import Any

from content_farm.explainer.deck import Deck
from content_farm.explainer.slideshow_risk import RISK_THRESHOLD, fix_requests, producer_note, score_deck
from content_farm.production import slideshow_fix
from tests.unit.explainer_helpers import NARRATION, deck_dict, slide

AI = {"kind": "ai_image", "prompt": "a lone squid drifting through marine snow, side view, soft cold light"}


def _deck(slides: list[dict[str, Any]]) -> Deck:
    thirds = [slides[0::3], slides[1::3], slides[2::3]]
    sections = [{"title": f"章{i}", "slides": group or [slide(f"x{i}", "quote", media=AI)]} for i, group in enumerate(thirds)]
    return Deck.model_validate(deck_dict(sections=sections))


def test_plain_repeated_text_pages_are_risky_and_a_varied_picture_deck_is_not() -> None:
    boring = _deck([slide(f"p{i}", "bullets") for i in range(9)])
    varied = _deck([slide("a", "title", media=AI), slide("b", "big_number", media={**AI, "frame": "panel_left"}),
                    slide("c", "quote", media={**AI, "motion_prompt": "slow push-in"})])
    boring_risk, varied_risk = score_deck(boring), score_deck(varied)
    assert boring_risk.over_limit and boring_risk.mean_score > varied_risk.mean_score
    assert not varied_risk.over_limit and not varied_risk.risky


def test_factors_are_named_per_page() -> None:
    deck = _deck([slide("a", "bullets"), slide("b", "bullets")])
    by_id = {r.slide_id: r for r in score_deck(deck).slides}
    assert "plain" in by_id["a"].factors
    assert {"plain", "repeat"} <= set(by_id["b"].factors)      # same form as the page before
    assert by_id["b"].score >= RISK_THRESHOLD


def test_a_wall_of_text_and_a_long_hold_add_points() -> None:
    long_text = {"items": ["一二三四五六七八九十一二三四五六", "一二三四五六七八九十一二三四五六", "一二三四五六七八九十一二三四五六",
                           "一二三四五六七八九十一二三四五六", "一二三四五六七八九十一二三四五六"]}
    deck = _deck([slide("a", "bullets", body=long_text, narration=NARRATION * 4)])
    factors = score_deck(deck).slides[0].factors
    assert "text" in factors and "long_hold" in factors


def test_measured_seconds_override_the_estimate_and_moving_media_is_not_held() -> None:
    held = _deck([slide("a", "quote", media=AI)])
    assert "long_hold" in score_deck(held, {"a": 40.0}).slides[0].factors
    assert "long_hold" not in score_deck(held, {"a": 5.0}).slides[0].factors


def test_fix_requests_only_when_over_the_limit_and_worst_first() -> None:
    boring = score_deck(_deck([slide(f"p{i}", "bullets") for i in range(9)]))
    lines = fix_requests(boring)
    assert lines and lines[0].startswith("p")
    assert "換版型" in producer_note(boring) or "加一張圖" in producer_note(boring)
    fine = score_deck(_deck([slide("a", "title", media=AI), slide("b", "quote", media={**AI, "frame": "panel_left"}),
                             slide("c", "big_number", media={**AI, "motion_prompt": "pan right"})]))
    assert fix_requests(fine) == [] and producer_note(fine) == ""


def _write_deck(run_dir, slides) -> None:
    (run_dir / "deck.json").write_text(_deck(slides).model_dump_json(), encoding="utf-8")


def test_maybe_redo_asks_once_keeps_a_better_deck_and_never_asks_again(tmp_path) -> None:
    bad = [slide(f"p{i}", "bullets") for i in range(9)]
    good = [slide("a", "title", media=AI), slide("b", "quote", media={**AI, "frame": "panel_left"}),
            slide("c", "big_number", media={**AI, "motion_prompt": "pan right"})]
    _write_deck(tmp_path, bad)
    notes: list[str] = []

    def produce(note: str) -> None:
        notes.append(note)
        _write_deck(tmp_path, good)

    slideshow_fix.maybe_redo(tmp_path, enabled=True, produce=produce, violations=lambda: [], log=lambda _m: None)
    report = json.loads(slideshow_fix.report_path(tmp_path).read_text(encoding="utf-8"))
    assert len(notes) == 1 and report["requested"] and report["outcome"] == "fixed"
    assert report["after"]["mean_score"] < report["before"]["mean_score"]
    _write_deck(tmp_path, bad)          # a later rework brings the bad deck back: still no second request
    slideshow_fix.maybe_redo(tmp_path, enabled=True, produce=produce, violations=lambda: [], log=lambda _m: None)
    assert len(notes) == 1


def test_a_failed_or_rule_breaking_redo_restores_the_first_deck(tmp_path) -> None:
    bad = [slide(f"p{i}", "bullets") for i in range(9)]
    _write_deck(tmp_path, bad)
    original = (tmp_path / "deck.json").read_text(encoding="utf-8")

    def produce(_note: str) -> None:
        (tmp_path / "deck.json").write_text("{}", encoding="utf-8")

    slideshow_fix.maybe_redo(tmp_path, enabled=True, produce=produce, violations=lambda: ["opening missing"],
                             log=lambda _m: None)
    assert (tmp_path / "deck.json").read_text(encoding="utf-8") == original
    assert json.loads(slideshow_fix.report_path(tmp_path).read_text(encoding="utf-8"))["outcome"] == "restored"


def test_disabled_channel_does_nothing(tmp_path) -> None:
    _write_deck(tmp_path, [slide(f"p{i}", "bullets") for i in range(9)])
    slideshow_fix.maybe_redo(tmp_path, enabled=False, produce=lambda _n: 1 / 0, violations=lambda: [], log=lambda _m: None)
    assert not slideshow_fix.report_path(tmp_path).exists()
