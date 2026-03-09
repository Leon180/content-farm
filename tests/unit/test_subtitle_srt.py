"""Tests for SRT format helpers."""

from __future__ import annotations

from content_farm.subtitle.schemas import SubtitleSegment
from content_farm.subtitle.srt import format_timestamp, render_srt


class TestFormatTimestamp:
    def test_zero(self) -> None:
        assert format_timestamp(0.0) == "00:00:00,000"

    def test_seconds_only(self) -> None:
        assert format_timestamp(5.0) == "00:00:05,000"

    def test_minutes_and_seconds(self) -> None:
        assert format_timestamp(65.0) == "00:01:05,000"

    def test_hours_minutes_seconds(self) -> None:
        assert format_timestamp(3661.5) == "01:01:01,500"

    def test_milliseconds(self) -> None:
        assert format_timestamp(1.123) == "00:00:01,123"

    def test_large_value(self) -> None:
        assert format_timestamp(7200.0) == "02:00:00,000"


class TestRenderSrt:
    def test_single_segment(self) -> None:
        seg = SubtitleSegment(
            index=1,
            start_seconds=0.0,
            end_seconds=2.5,
            text="Hello",
            scene_number=1,
        )
        result = render_srt((seg,))
        assert "1\n" in result
        assert "00:00:00,000 --> 00:00:02,500" in result
        assert "Hello" in result

    def test_multiple_segments(self) -> None:
        segs = (
            SubtitleSegment(
                index=1, start_seconds=0.0, end_seconds=2.0,
                text="第一段", scene_number=1,
            ),
            SubtitleSegment(
                index=2, start_seconds=2.0, end_seconds=4.0,
                text="第二段", scene_number=1,
            ),
        )
        result = render_srt(segs)
        assert result.count("-->") == 2
        assert "1\n" in result
        assert "2\n" in result

    def test_empty_segments(self) -> None:
        result = render_srt(())
        assert result == ""

    def test_cjk_text(self) -> None:
        seg = SubtitleSegment(
            index=1,
            start_seconds=0.0,
            end_seconds=3.0,
            text="歡迎來到我們的頻道",
            scene_number=1,
        )
        result = render_srt((seg,))
        assert "歡迎來到我們的頻道" in result
