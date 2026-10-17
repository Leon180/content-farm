"""Retention tooling: beat lint, picture metrics on synthetic frames, dead zones, descriptions."""

from __future__ import annotations

import json

import numpy as np

from content_farm.retention.audio_report import describe
from content_farm.retention.beats import classify, lint
from content_farm.retention.report import dead_zones
from content_farm.retention.screen_text import sync_findings
from content_farm.retention.timing import Scene, Sentence, sentence_timeline, split_sentences
from content_farm.retention.video_probe import FPS, analyse_frames


def test_classify_hook_kinds() -> None:
    assert classify("為什麼還是不夠？") == "question"
    assert classify("接下來，我們一張一張證明它。") == "tease"
    assert classify("晶圓翻倍，能出貨的晶片卻不一定跟著翻倍。") == "reversal"
    assert classify("我上一次等這麼久，是在等罐罐打折。") == "joke"
    assert classify("黃仁勳自己說：那是百分之百 NVIDIA 的錯。") == "quote"
    assert classify("中介層就像一張高架路網。") == "analogy"
    assert classify("報導說 2026 年約 13 萬片。") is None


def test_split_sentences_keeps_punctuation() -> None:
    assert split_sentences("第一句。第二句？第三句") == ["第一句。", "第二句？", "第三句"]


def _scene(index: int, start: float, end: float, chapter: int = 1) -> Scene:
    return Scene(index, f"s{index:02d}", chapter, start, end, "")


def test_lint_flags_long_gap_and_missing_chapter_tease() -> None:
    scenes = [_scene(1, 0, 30, 1), _scene(2, 30, 60, 2)]
    sentences = [Sentence(1, "s01", "為什麼？", 2, 3), Sentence(1, "s01", "平鋪直敘。", 3, 29),
                 Sentence(2, "s02", "報導說。", 31, 40), Sentence(2, "s02", "接下來看答案。", 45, 50)]
    report = lint(scenes, sentences, {})
    assert report.first_hook == 2
    assert report.max_gap == 43.0              # 2 → 45 s with nothing in between
    assert any(g["start"] == 2 for g in report.gaps)
    assert report.chapter_teases == [{"chapter": 1, "at": 30.0, "slide_id": "s01"}]


def test_lint_passes_dense_hooks() -> None:
    scenes = [_scene(1, 0, 20)]
    sentences = [Sentence(1, "s01", "為什麼？", t, t + 1) for t in (1, 9, 17)]
    report = lint(scenes, sentences, {})
    assert report.gaps == [] and report.max_gap <= 10


def test_sentence_timeline_uses_srt_when_text_matches(tmp_path) -> None:
    (tmp_path / "subtitles").mkdir()
    (tmp_path / "script.json").write_text(json.dumps({"scenes": [
        {"scene_number": 1, "narration": "甲乙。丙丁？", "duration_seconds": 10, "chapter_number": 1}]}),
        encoding="utf-8")
    (tmp_path / "subtitles" / "subtitles.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\n甲乙。\n\n2\n00:00:06,000 --> 00:00:08,000\n丙丁？\n", encoding="utf-8")
    sentences = sentence_timeline(tmp_path)
    assert [round(s.start) for s in sentences] == [1, 6]


def test_dead_zones_need_all_three_silent() -> None:
    zones = dead_zones(60.0, [5.0, 30.0], [38.0], [12.0, 20.0])
    assert zones == [{"start": 38.0, "end": 60.0, "seconds": 22.0}]
    assert dead_zones(20.0, [9.0], [], [15.0]) == []


def test_analyse_frames_finds_long_still_and_blank() -> None:
    rng = np.random.default_rng(0)
    busy = rng.integers(0, 255, size=(83, 156), dtype=np.uint8)
    other = rng.integers(0, 255, size=(83, 156), dtype=np.uint8)
    flat = np.full((83, 156), 128, dtype=np.uint8)
    frames = np.stack([busy] * (12 * FPS) + [flat] * (2 * FPS) + [other] * (3 * FPS))
    report = analyse_frames(frames)
    assert report.longest_still >= 11.5
    assert len(report.long_stills) == 1
    assert len(report.blanks) == 1 and report.blanks[0].seconds >= 1.5
    assert len(report.events) >= 2


def test_held_blend_is_detected() -> None:
    rng = np.random.default_rng(1)
    a = rng.integers(0, 255, size=(83, 156)).astype(np.float32)
    b = rng.integers(0, 255, size=(83, 156)).astype(np.float32)
    mid = ((a + b) / 2).astype(np.uint8)
    frames = np.stack([a.astype(np.uint8)] * 12 + [mid] * (3 * FPS) + [b.astype(np.uint8)] * 12)
    assert len(analyse_frames(frames).held_blends) == 1


def test_sync_flags_numbers_not_spoken() -> None:
    scenes = [_scene(1, 0, 30)]
    sentences = [Sentence(1, "s01", "中介層上限 858 平方毫米。", 1, 5), Sentence(1, "s01", "到了 2027 年。", 20, 25)]
    issues = sync_findings(scenes, sentences, {"s01": "858 mm² 9 倍 2027"})
    kinds = {i["number"]: i["issue"] for i in issues}
    assert "858" not in kinds
    assert kinds["9"] == "畫面有、旁白沒講"
    assert "後才講" in kinds["2027"]


def test_describe_reads_like_a_person() -> None:
    line = describe({"rate": 6.1, "pitch_spread_st": 1.0, "bgm_under_voice_db": 15, "cues": []})
    assert line == "語速 6.1 字/秒偏快、語調平、BGM 低、無音效"
    assert describe({"rate": None, "cues": ["叮聲"]}).startswith("沒有旁白")
