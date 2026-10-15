"""Text normalization for TTS — converts numerals to speakable Chinese."""

from __future__ import annotations

import re

_DIGIT_MAP = {
    "0": "零",
    "1": "一",
    "2": "二",
    "3": "三",
    "4": "四",
    "5": "五",
    "6": "六",
    "7": "七",
    "8": "八",
    "9": "九",
}

# Matches 4-digit years followed by a year-related suffix (年, 年代, 年間, etc.)
# or preceded by common context like 西元, 公元, 民國 is typically 3-digit so excluded.
# A single space before 年 is allowed: decks space Latin/digits from CJK ("2016 年").
_YEAR_PATTERN = re.compile(r"(?<!\d)(\d{4}) ?(年)")


def _digits_to_chinese(match: re.Match) -> str:
    """Convert a 4-digit year to digit-by-digit Chinese reading."""
    digits = match.group(1)
    suffix = match.group(2)
    chinese = "".join(_DIGIT_MAP[d] for d in digits)
    return chinese + suffix


def apply_pronunciation_map(
    text: str,
    pronunciation_map: dict[str, str],
) -> str:
    """Apply pronunciation substitutions for TTS only.

    Each key (display text) is replaced with its value (TTS text).
    Applied in iteration order so later entries can build on earlier ones.
    """
    for display, tts in pronunciation_map.items():
        text = text.replace(display, tts)
    return text


def normalize_for_tts(
    text: str,
    pronunciation_map: dict[str, str] | None = None,
) -> str:
    """Normalize text for Chinese TTS.

    Handles:
    - Pronunciation substitutions (鮪魚 → 偉魚 for TTS only)
    - 4-digit years: 1974年 → 一九七四年
    """
    if pronunciation_map:
        text = apply_pronunciation_map(text, pronunciation_map)
    return _YEAR_PATTERN.sub(_digits_to_chinese, text)
