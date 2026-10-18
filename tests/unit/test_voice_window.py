"""Sentence windows to re-voice (voice.window)."""

from __future__ import annotations

from content_farm.voice.window import Window, plan

OLD = ["一。", "二。", "三。", "四。", "五。", "六。", "七。", "八。"]


def _with(index: int, text: str) -> list[str]:
    return [*OLD[:index], text, *OLD[index + 1:]]


def test_unchanged_scene_needs_nothing():
    assert plan(OLD, OLD, 1) == []


def test_one_rewrite_with_radius():
    assert plan(OLD, _with(3, "改。"), 0) == [Window(3, 3, 3, 3)]
    assert plan(OLD, _with(3, "改。"), 1) == [Window(2, 4, 2, 4)]
    assert plan(OLD, _with(0, "改。"), 1) == [Window(0, 1, 0, 1)]   # clamped at the scene edge


def test_close_edits_merge_into_one_window():
    old = [*OLD, "九。", "十。"]
    new = list(old)
    new[2], new[4] = "甲。", "乙。"
    assert plan(old, new, 1) == [Window(1, 5, 1, 5)]


def test_insertion_replaces_a_neighbour_even_at_radius_zero():
    new = [*OLD[:4], "新。", *OLD[4:]]
    assert plan(OLD, new, 0) == [Window(3, 4, 3, 5)]


def test_large_edits_fall_back_to_a_full_take():
    new = ["甲。", "乙。", "丙。", "丁。", "戊。", "己。", "七。", "八。"]
    assert plan(OLD, new, 1) is None
    assert plan([], OLD, 1) is None and plan(OLD, OLD, -1) is None
