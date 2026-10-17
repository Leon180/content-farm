"""Subtitle lines vs the cat's column (explainer.mascot.clearance)."""

from __future__ import annotations

from pathlib import Path

import pytest

from content_farm.assembly.drawtext import find_cjk_font
from content_farm.assembly.timeline_assembly import LANDSCAPE_PRESET
from content_farm.explainer.mascot.clearance import SUBTITLE_FONT_SIZE, srt_lines, wide_lines
from content_farm.subtitle.line_wrap import wrap_text

FONT = find_cjk_font()
needs_font = pytest.mark.skipif(not FONT, reason="no CJK font on this machine")

# 28 chars with a comma at the end: wrap_text(…, 24) keeps it on one line (max + 4).
LONG = "我先把結論放在這裡。CoWoS 不是什麼沒人會的黑科技，"
SHORT = "卡住的是時間差。"


def _srt(tmp_path: Path, *texts: str) -> Path:
    blocks = [f"{i}\n00:00:0{i},000 --> 00:00:0{i},900\n{t}\n" for i, t in enumerate(texts, 1)]
    path = tmp_path / "subtitles.srt"
    path.write_text("\n".join(blocks), encoding="utf-8")
    return path


def test_font_size_matches_the_landscape_preset() -> None:
    assert SUBTITLE_FONT_SIZE == LANDSCAPE_PRESET.subtitle_font_size


def test_srt_lines_keeps_multi_line_cues() -> None:
    srt = "1\n00:00:01,000 --> 00:00:02,000\n第一行\n第二行\n\n2\n00:00:03,000 --> 00:00:04,000\n第三行\n"
    assert srt_lines(srt) == ["第一行", "第二行", "第三行"]


@needs_font
def test_long_line_is_flagged_short_is_not(tmp_path: Path) -> None:
    hits = wide_lines(_srt(tmp_path, LONG, SHORT), FONT)
    assert [h.text for h in hits] == [LONG]
    assert hits[0].right_edge > 1600


@needs_font
def test_default_landscape_wrap_can_overshoot_but_explainer_setting_cannot(tmp_path: Path) -> None:
    # comma at position 28: the 24-char wrap takes it (+4 tolerance) → a 28-char line; at 64 px
    # (v3) the explainer's 14-char setting (≤ 18 chars with tolerance) stays clear of the mascot
    from content_farm.production.steps import EXPLAINER_SUBTITLE_MAX

    text = "長期由矽品這些封測廠在台積電授權下承接後段製程而且越做，越多" * 3
    at_24 = wrap_text(text, 24).split("\n")
    at_explainer = wrap_text(text, int(EXPLAINER_SUBTITLE_MAX)).split("\n")
    assert wide_lines(_srt(tmp_path, *at_24), FONT)  # control: the detector fires
    assert wide_lines(_srt(tmp_path, *at_explainer), FONT) == ()
