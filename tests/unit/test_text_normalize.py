"""Tests for voice text normalization."""

from content_farm.voice.text_normalize import normalize_for_tts


class TestNormalizeForTTS:
    """Year normalization for Chinese TTS."""

    def test_four_digit_year(self):
        assert normalize_for_tts("1974年") == "一九七四年"

    def test_multiple_years(self):
        text = "從1953年到1974年之間"
        assert normalize_for_tts(text) == "從一九五三年到一九七四年之間"

    def test_year_with_decade_suffix(self):
        # 年代 starts with 年 so the pattern matches the 年 part
        assert normalize_for_tts("1950年代") == "一九五零年代"

    def test_no_year_suffix_untouched(self):
        # 4 digits without 年 should NOT be converted
        assert normalize_for_tts("有1974個人") == "有1974個人"

    def test_three_digit_number_untouched(self):
        assert normalize_for_tts("300年") == "300年"

    def test_five_digit_number_untouched(self):
        assert normalize_for_tts("10000年") == "10000年"

    def test_no_numbers(self):
        text = "飛機窗戶為什麼是圓的"
        assert normalize_for_tts(text) == text

    def test_mixed_content(self):
        text = "在1954年，有超過300萬人搭飛機"
        assert normalize_for_tts(text) == "在一九五四年，有超過300萬人搭飛機"

    def test_year_2000s(self):
        assert normalize_for_tts("2024年") == "二零二四年"

    def test_year_with_zero(self):
        assert normalize_for_tts("2000年") == "二零零零年"
