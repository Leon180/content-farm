"""Tests for subtitle line wrapping."""

from content_farm.subtitle.line_wrap import wrap_text


class TestWrapText:
    def test_short_line_unchanged(self) -> None:
        assert wrap_text("短文字", 13) == "短文字"

    def test_exactly_at_limit_unchanged(self) -> None:
        text = "一二三四五六七八九十一二三"  # 13 chars
        assert wrap_text(text, 13) == text

    def test_breaks_at_strong_punctuation(self) -> None:
        text = "心理學上這叫聲音對抗。最奇妙的是"
        result = wrap_text(text, 13)
        assert "\n" in result
        # The strong period should keep on the first line
        first, second = result.split("\n", 1)
        assert first.endswith("。")

    def test_breaks_at_medium_punctuation(self) -> None:
        text = "覺得錄音裡的自己很陌生，很奇怪不舒服"
        result = wrap_text(text, 13)
        assert "\n" in result
        first, second = result.split("\n", 1)
        assert first.endswith("，")

    def test_preserves_existing_breaks(self) -> None:
        text = "第一行\n第二行很長很長很長很長"
        result = wrap_text(text, 13)
        lines = result.split("\n")
        assert lines[0] == "第一行"
        # Second line should remain (≤13 chars after stripping) or wrap
        assert "第二行" in lines[1]

    def test_long_line_with_no_punctuation_hard_breaks(self) -> None:
        text = "一二三四五六七八九十一二三四五六七八九十"
        result = wrap_text(text, 13)
        lines = result.split("\n")
        assert all(len(line) <= 13 for line in lines)

    def test_empty_string(self) -> None:
        assert wrap_text("", 13) == ""

    def test_voice_perception_subtitle_14(self) -> None:
        """Real-world example: subtitle 14 from voice_perception."""
        text = "但錄音機只錄得到空氣傳播的那一條，濾鏡一拿掉，"
        result = wrap_text(text, 13)
        lines = result.split("\n")
        # Should split at the 「，」 around the middle
        assert len(lines) >= 2
        # Tolerate +4 (soft window for natural punctuation breaks)
        assert all(len(line) <= 17 for line in lines)

    def test_voice_perception_subtitle_1(self) -> None:
        text = "剛聽完自己的語音訊息，你的第一反應是不是："
        result = wrap_text(text, 13)
        lines = result.split("\n")
        assert lines[0].endswith("，")
        assert all(len(line) <= 17 for line in lines)
