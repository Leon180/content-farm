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


# --- Dramatic gap tests ---


@pytest.mark.asyncio
async def test_gap_after_sentence_ending_punctuation() -> None:
    """Chunks ending with 。！？ should have a gap before the next chunk starts."""
    provider = EstimationProvider(target_chars=10, min_chars=5, max_chars=14, sentence_gap=0.5)
    # 。 at position 9 falls within the split search window → chunk ends with 。
    text = "第一句話說完了結束。第二句話繼續開始寫下去吧"
    segments = await provider.generate_segments(text, duration_seconds=8.0)
    assert len(segments) >= 2
    # Find the first chunk that ends with 。
    gap_found = False
    for i in range(len(segments) - 1):
        if segments[i].text.endswith("。"):
            gap = segments[i + 1].start_seconds - segments[i].end_seconds
            assert gap >= 0.4  # close to 0.5
            gap_found = True
            break
    assert gap_found, "No chunk ended with 。"


@pytest.mark.asyncio
async def test_no_gap_after_comma() -> None:
    """Commas (，) should NOT trigger a gap — only 。！？ do."""
    provider = EstimationProvider(target_chars=10, min_chars=5, max_chars=14, sentence_gap=0.5)
    text = "前面一段話寫很長，後面又繼續寫一段話下去"
    segments = await provider.generate_segments(text, duration_seconds=6.0)
    assert len(segments) >= 2
    # No sentence-ending punct → no gap, timestamps continuous
    for i in range(1, len(segments)):
        gap = segments[i].start_seconds - segments[i - 1].end_seconds
        assert gap < 0.01


@pytest.mark.asyncio
async def test_no_gap_after_last_chunk() -> None:
    """The final chunk should NOT have a trailing gap."""
    provider = EstimationProvider(target_chars=8, max_chars=12, sentence_gap=0.5)
    text = "最後一句話結束。"
    segments = await provider.generate_segments(text, duration_seconds=3.0)
    assert len(segments) == 1
    # Single segment should consume the full duration
    assert segments[0].end_seconds == pytest.approx(3.0, abs=0.01)


@pytest.mark.asyncio
async def test_ellipsis_double_gap() -> None:
    """……。 pattern triggers double gap for extra dramatic pause."""
    provider = EstimationProvider(target_chars=10, min_chars=5, max_chars=14, sentence_gap=0.4)
    text = "懸念慢慢揭曉了……。答案就是這個你猜到了嗎"
    segments = await provider.generate_segments(text, duration_seconds=8.0)
    assert len(segments) >= 2
    gap_found = False
    for i in range(len(segments) - 1):
        if "……" in segments[i].text and segments[i].text.endswith("。"):
            gap = segments[i + 1].start_seconds - segments[i].end_seconds
            assert gap >= 0.7  # double gap
            gap_found = True
            break
    assert gap_found, "No chunk ended with ……。"


@pytest.mark.asyncio
async def test_custom_sentence_gap() -> None:
    """sentence_gap parameter controls gap duration."""
    provider = EstimationProvider(target_chars=10, min_chars=5, max_chars=14, sentence_gap=1.0)
    text = "第一句話說完了結束。第二句話繼續開始寫下去吧"
    segments = await provider.generate_segments(text, duration_seconds=10.0)
    assert len(segments) >= 2
    gap_found = False
    for i in range(len(segments) - 1):
        if segments[i].text.endswith("。"):
            gap = segments[i + 1].start_seconds - segments[i].end_seconds
            assert gap >= 0.9
            gap_found = True
            break
    assert gap_found, "No chunk ended with 。"


@pytest.mark.asyncio
async def test_zero_gap_disables_feature() -> None:
    """sentence_gap=0 reverts to continuous timestamps."""
    provider = EstimationProvider(target_chars=10, min_chars=5, max_chars=14, sentence_gap=0.0)
    text = "第一句話說完了結束。第二句話繼續開始寫下去吧"
    segments = await provider.generate_segments(text, duration_seconds=6.0)
    assert len(segments) >= 2
    for i in range(1, len(segments)):
        gap = segments[i].start_seconds - segments[i - 1].end_seconds
        assert gap < 0.01
