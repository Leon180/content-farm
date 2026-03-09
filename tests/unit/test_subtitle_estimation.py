"""Tests for the estimation-based subtitle provider."""

from __future__ import annotations

import pytest

from content_farm.subtitle.estimation import EstimationProvider


@pytest.mark.asyncio
async def test_short_text_single_segment() -> None:
    provider = EstimationProvider()
    segments = await provider.generate_segments("短文本", duration_seconds=3.0)
    assert len(segments) == 1
    assert segments[0].start_seconds == 0.0
    assert segments[0].end_seconds == pytest.approx(3.0, abs=0.01)
    assert segments[0].text == "短文本"


@pytest.mark.asyncio
async def test_long_text_splits_into_chunks() -> None:
    provider = EstimationProvider(target_chars=10, max_chars=15)
    text = "這是一段比較長的中文敘述文字需要被分割成多個字幕段落以便觀看"
    segments = await provider.generate_segments(text, duration_seconds=6.0)
    assert len(segments) > 1
    for seg in segments:
        assert len(seg.text) <= 20


@pytest.mark.asyncio
async def test_offset_applied() -> None:
    provider = EstimationProvider()
    segments = await provider.generate_segments(
        "測試", duration_seconds=2.0, offset_seconds=10.0,
    )
    assert segments[0].start_seconds == pytest.approx(10.0)
    assert segments[0].end_seconds == pytest.approx(12.0)


@pytest.mark.asyncio
async def test_empty_text_returns_empty() -> None:
    provider = EstimationProvider()
    segments = await provider.generate_segments("", duration_seconds=5.0)
    assert segments == ()


@pytest.mark.asyncio
async def test_whitespace_only_returns_empty() -> None:
    provider = EstimationProvider()
    segments = await provider.generate_segments("   \n  ", duration_seconds=5.0)
    assert segments == ()


@pytest.mark.asyncio
async def test_prefers_punctuation_breaks() -> None:
    provider = EstimationProvider(target_chars=10, min_chars=5, max_chars=20)
    text = "前面的文字文字文字，後面的文字然後繼續寫下去"
    segments = await provider.generate_segments(text, duration_seconds=4.0)
    assert len(segments) >= 2
    # First chunk should end at or include the comma
    assert "，" in segments[0].text


@pytest.mark.asyncio
async def test_timestamps_are_continuous() -> None:
    provider = EstimationProvider(target_chars=10, max_chars=15)
    text = "第一段字幕內容第二段字幕內容第三段字幕內容。"
    segments = await provider.generate_segments(text, duration_seconds=9.0)
    assert len(segments) > 1
    for i in range(1, len(segments)):
        assert segments[i].start_seconds == pytest.approx(
            segments[i - 1].end_seconds, abs=0.01,
        )


@pytest.mark.asyncio
async def test_total_duration_matches() -> None:
    provider = EstimationProvider(target_chars=10, max_chars=15)
    text = "這段文字會被分割成多個段落用來測試總時長是否正確"
    duration = 8.0
    segments = await provider.generate_segments(text, duration_seconds=duration)
    assert len(segments) > 0
    assert segments[-1].end_seconds == pytest.approx(duration, abs=0.01)


@pytest.mark.asyncio
async def test_indices_are_sequential() -> None:
    provider = EstimationProvider(target_chars=10, max_chars=15)
    text = "第一段字幕內容第二段字幕內容第三段字幕內容。"
    segments = await provider.generate_segments(text, duration_seconds=6.0)
    indices = [s.index for s in segments]
    assert indices == list(range(1, len(segments) + 1))
