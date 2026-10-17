"""Pinyin comparison: homophones are not misreads; tone-only differences are listed apart."""

from __future__ import annotations

from content_farm.voice import checked_synthesis
from content_farm.voice.pinyin_check import compare


def test_homophone_is_not_an_error() -> None:
    result = compare("扣窩斯", "扣窩絲", ["kou4", "wo1", "si1"], ["kou4", "wo1", "si1"])
    assert result == {"pinyin_cer": 0.0, "tone_errors": []}


def test_tone_difference_is_listed_but_not_counted() -> None:
    result = compare("買", "賣", ["mai3"], ["mai4"])
    assert result["pinyin_cer"] == 0.0
    assert result["tone_errors"] == ["買(mai3)→賣(mai4)"]


def test_wrong_syllable_counts() -> None:
    assert compare("九尾狐", "九尾虎", ["jiu3", "wei3", "hu2"], ["jiu3", "wei3", "hu3"])["pinyin_cer"] == 0.0
    assert compare("扣破斯", "可破斯", ["kou4", "po4", "si1"], ["ke3", "po4", "si1"])["pinyin_cer"] == 0.333


def test_record_check_without_tts_python_keeps_record(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("CF_LOCAL_TTS_PYTHON", raising=False)
    checked_synthesis.record_check(tmp_path, "scene_001.mp3", {"cer": 0.1, "hypothesis": "abc"})
    assert checked_synthesis.load_checks(tmp_path) == {"scene_001.mp3": {"cer": 0.1, "hypothesis": "abc"}}
