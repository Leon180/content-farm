"""Tests for assembly.drawtext — SRT parsing and drawtext filter generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from content_farm.assembly.drawtext import (
    build_drawtext_filter,
    build_drawtext_filter_from_entries,
    parse_srt,
)

_SAMPLE_SRT = """\
1
00:00:00,000 --> 00:00:02,500
第一句字幕

2
00:00:02,500 --> 00:00:05,000
第二句字幕
"""


def test_parse_srt_extracts_entries() -> None:
    entries = parse_srt(_SAMPLE_SRT)
    assert len(entries) == 2
    assert entries[0] == (0.0, 2.5, "第一句字幕")
    assert entries[1] == (2.5, 5.0, "第二句字幕")


def test_parse_srt_empty() -> None:
    assert parse_srt("") == []
    assert parse_srt("  \n\n  ") == []


def test_parse_srt_timestamp_precision() -> None:
    srt = "1\n01:02:03,456 --> 01:02:05,789\ntext\n\n"
    entries = parse_srt(srt)
    assert len(entries) == 1
    start, end, _ = entries[0]
    assert abs(start - 3723.456) < 0.001
    assert abs(end - 3725.789) < 0.001


def test_build_drawtext_filter_from_file(tmp_path: Path) -> None:
    srt_path = tmp_path / "test.srt"
    srt_path.write_text(_SAMPLE_SRT, encoding="utf-8")

    result = build_drawtext_filter(srt_path, fontfile=None)

    assert "drawtext=" in result
    assert "第一句字幕" in result
    assert "第二句字幕" in result
    assert "gte(t," in result and "lte(t," in result
    assert "0.000" in result and "2.500" in result
    assert "5.000" in result


def test_build_drawtext_filter_empty_srt(tmp_path: Path) -> None:
    srt_path = tmp_path / "empty.srt"
    srt_path.write_text("", encoding="utf-8")

    assert build_drawtext_filter(srt_path) == ""


def test_build_drawtext_filter_custom_style(tmp_path: Path) -> None:
    srt_path = tmp_path / "test.srt"
    srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n\n", encoding="utf-8")

    result = build_drawtext_filter(
        srt_path, fontsize=50, fontcolor="yellow", borderw=3,
    )

    assert "fontsize=50" in result
    assert "fontcolor=yellow" in result
    assert "borderw=3" in result


def test_build_drawtext_filter_with_fontfile(tmp_path: Path) -> None:
    srt_path = tmp_path / "test.srt"
    srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n\n", encoding="utf-8")

    result = build_drawtext_filter(srt_path, fontfile="/usr/share/fonts/test.ttf")
    assert "fontfile='/usr/share/fonts/test.ttf'" in result


def test_fontfile_with_spaces(tmp_path: Path) -> None:
    srt_path = tmp_path / "test.srt"
    srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n\n", encoding="utf-8")

    result = build_drawtext_filter(
        srt_path, fontfile="/System/Library/Fonts/STHeiti Medium.ttc",
    )
    # Space in path is inside single quotes
    assert "fontfile='/System/Library/Fonts/STHeiti Medium.ttc'" in result


def test_escape_single_quote_in_text(tmp_path: Path) -> None:
    srt_path = tmp_path / "test.srt"
    srt_path.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nit's a test\n\n", encoding="utf-8",
    )

    result = build_drawtext_filter(srt_path, fontfile=None)
    # Single quote replaced with right single quotation mark
    assert "it\u2019s a test" in result
    # No ASCII single quote inside the text value itself
    text_value = result.split("text='")[1].split("'")[0]
    assert "'" not in text_value


def test_escape_percent_in_text(tmp_path: Path) -> None:
    srt_path = tmp_path / "test.srt"
    srt_path.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n50% off\n\n", encoding="utf-8",
    )

    result = build_drawtext_filter(srt_path, fontfile=None)
    # % is replaced with full-width ％ (FFmpeg 8 drawtext treats %% as stray near CJK)
    assert "50\uff05 off" in result


def test_escape_colon_in_text(tmp_path: Path) -> None:
    srt_path = tmp_path / "test.srt"
    srt_path.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nhttps://example.com\n\n", encoding="utf-8",
    )

    result = build_drawtext_filter(srt_path, fontfile=None)
    # Colons in text must be escaped with \: even inside single quotes
    assert "https\\://example.com" in result


def test_build_from_entries() -> None:
    entries = [(0.0, 2.0, "Hello"), (2.0, 4.0, "World")]
    result = build_drawtext_filter_from_entries(entries, fontfile=None)

    assert result.count("drawtext=") == 2
    assert "Hello" in result
    assert "World" in result


def test_build_from_entries_empty() -> None:
    assert build_drawtext_filter_from_entries([]) == ""


def test_multiple_entries_comma_separated(tmp_path: Path) -> None:
    srt_path = tmp_path / "test.srt"
    srt_path.write_text(_SAMPLE_SRT, encoding="utf-8")

    result = build_drawtext_filter(srt_path, fontfile=None)
    # Two drawtext filters joined by comma
    parts = result.split(",drawtext=")
    assert len(parts) == 2
