"""Line-wrap utility for zh-TW subtitles.

Portrait 1080x1920 videos with ~78pt CJK font can fit ~13 Chinese
characters per line. Anything longer overflows the screen. This module
wraps subtitle text at punctuation boundaries so long chunks break
into multiple visual lines.

Used by both ``EstimationProvider`` and ``WhisperAlignmentProvider``
so subtitle output is consistently formatted regardless of timing
backend.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from content_farm.subtitle.atoms import is_safe_break, protected_spans

# Preferred break characters (zh + latin punctuation).
# Order matters: stronger separators first.
_STRONG_BREAK = re.compile(r"[。！？!?]")
_MEDIUM_BREAK = re.compile(r"[，、；：,;:]")
_WEAK_BREAK = re.compile(r"[　\s]")  # fullwidth or ascii space


def wrap_text(text: str, max_chars_per_line: int = 13) -> str:
    """Wrap ``text`` so no line exceeds ``max_chars_per_line`` characters.

    Existing line breaks (``\\n``) are preserved. Lines that are already
    short enough are left untouched.

    Break strategy per over-long line:
    1. Split at strong punctuation (。！？) within the window if present.
    2. Else split at medium punctuation (，、；：).
    3. Else split at whitespace.
    4. Else hard-break at the max boundary.

    The chosen break point keeps the punctuation on the PRECEDING line
    (natural reading flow).
    """
    if not text.strip():
        return text

    out_lines: list[str] = []
    for line in text.split("\n"):
        wrapped = _wrap_one_line(line, max_chars_per_line)
        out_lines.extend(wrapped)
    return "\n".join(out_lines)


def _wrap_one_line(line: str, max_chars: int) -> list[str]:
    line = line.rstrip()
    if len(line) <= max_chars:
        return [line]

    pieces: list[str] = []
    remaining = line

    while len(remaining) > max_chars:
        split_at = _find_break_point(remaining, max_chars)
        piece = remaining[:split_at].rstrip()
        if piece:
            pieces.append(piece)
        remaining = remaining[split_at:].lstrip()

    if remaining:
        pieces.append(remaining)
    return pieces


def _find_break_point(text: str, max_chars: int) -> int:
    """Return the index AFTER which we should break.

    Search strategy (priority order):
    1. Strong punctuation (。！？) within [max/2, max + 3]
    2. Medium punctuation (，、；：) within [max/2, max + 3]
    3. Whitespace within [max/2, max]
    4. Hard break at max

    Punctuation is allowed slightly past max (+3 chars) because:
    - Chinese punctuation marks are visually narrower than full chars
    - A natural break beats a hard cut, even if line is 14-15 chars
    - Avoids ugly mid-word/mid-clause breaks

    No candidate may split an atom (``subtitle.atoms``): a number and its
    unit, a percentage, or a Latin/number word such as ``CoWoS-L``.
    """
    window_start = max(1, max_chars // 2)
    # +4 tolerance: punctuation like 「，。」 are visually narrower than CJK
    # characters and the overall line still feels balanced.
    soft_window_end = min(max_chars + 4, len(text))
    hard_window_end = min(max_chars, len(text))
    spans = protected_spans(text)

    def safe(index: int) -> bool:
        return is_safe_break(text, index, spans)

    # 1. Strong punctuation (allow up to max + 3)
    for pos in range(soft_window_end - 1, window_start - 1, -1):
        if _STRONG_BREAK.match(text[pos]) and safe(pos + 1):
            return pos + 1  # include punctuation on preceding line

    # 2. Medium punctuation (allow up to max + 3) — never the comma in "1,000"
    for pos in range(soft_window_end - 1, window_start - 1, -1):
        if _MEDIUM_BREAK.match(text[pos]) and safe(pos + 1):
            return pos + 1

    # 3. Whitespace (only within hard limit) — never the space in "2026 年"
    for pos in range(hard_window_end - 1, window_start - 1, -1):
        if _WEAK_BREAK.match(text[pos]) and safe(pos + 1):
            return pos + 1

    # 4. Hard break at the max window, moved back to before any atom it would cut;
    #    an atom longer than the whole line stays whole (the line runs long).
    return _hard_break(text, hard_window_end, safe)


def _hard_break(text: str, limit: int, safe: Callable[[int], bool]) -> int:
    for index in range(limit, 0, -1):
        if safe(index):
            return index
    return next((i for i in range(limit + 1, len(text)) if safe(i)), len(text))
