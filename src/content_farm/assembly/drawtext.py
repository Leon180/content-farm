"""Build FFmpeg drawtext filter chains from SRT files.

Uses the drawtext filter (built into all FFmpeg builds) to burn subtitles
directly into the video frames.  No libass / subtitles filter required.
"""

from __future__ import annotations

import re
from pathlib import Path

# SRT block: index, start --> end, one or more text lines, blank line
_SRT_BLOCK = re.compile(
    r"(\d+)\s*\n"
    r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\n"
    r"((?:(?!\n\n|\Z).+(?:\n|$))+)",
)

# Known CJK font paths (checked in order)
_CJK_FONT_CANDIDATES = (
    "/System/Library/Fonts/STHeiti Medium.ttc",      # macOS
    "/System/Library/Fonts/PingFang.ttc",             # macOS newer
    "/System/Library/Fonts/Hiragino Sans GB.ttc",     # macOS
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Linux
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
)


def find_cjk_font() -> str | None:
    """Return the first available CJK font path, or None."""
    for candidate in _CJK_FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def _parse_timestamp(ts: str) -> float:
    """``00:01:23,456`` → seconds as float."""
    h, m, rest = ts.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_srt(content: str) -> list[tuple[float, float, str]]:
    """Parse SRT content into ``(start, end, text)`` tuples."""
    entries: list[tuple[float, float, str]] = []
    for match in _SRT_BLOCK.finditer(content):
        start = _parse_timestamp(match.group(2))
        end = _parse_timestamp(match.group(3))
        text = match.group(4).strip()
        entries.append((start, end, text))
    return entries


def _escape_text(text: str) -> str:
    """Escape text for FFmpeg drawtext ``text='...'`` (single-quoted value).

    The value is wrapped in single quotes by the caller, which protects
    commas and semicolons.  Colons still need ``\\:`` even inside quotes.
    Backslash and single-quote must also be escaped.
    """
    text = text.replace("\\", "\\\\")     # \ → \\  (must be first)
    text = text.replace("'", "\u2019")    # ' → RIGHT SINGLE QUOTATION MARK
    text = text.replace(":", "\\:")       # : → \:  (option separator)
    text = text.replace("%", "%%")        # % → %%  (drawtext format sequence)
    text = text.replace("\n", " ")
    return text


def build_drawtext_filter(
    srt_path: Path,
    *,
    fontsize: int = 58,
    fontcolor: str = "white",
    borderw: int = 3,
    bordercolor: str = "black",
    margin_bottom: int = 120,
    fontfile: str | None = None,
) -> str:
    """Build a drawtext filter chain from an SRT file.

    Returns a filter string like ``drawtext=...,drawtext=...`` that can
    be used as ``-vf`` value or embedded in ``-filter_complex``.
    """
    content = srt_path.read_text(encoding="utf-8")
    entries = parse_srt(content)

    if not entries:
        return ""

    if fontfile is None:
        fontfile = find_cjk_font()

    parts: list[str] = []
    for start, end, text in entries:
        escaped = _escape_text(text)

        tokens = [
            f"text='{escaped}'",
            f"fontsize={fontsize}",
            f"fontcolor={fontcolor}",
            f"borderw={borderw}",
            f"bordercolor={bordercolor}",
            "x=(w-text_w)/2",
            f"y=h-text_h-{margin_bottom}",
            f"enable='gte(t,{start:.3f})*lte(t,{end:.3f})'",
        ]
        if fontfile:
            tokens.insert(1, f"fontfile='{fontfile}'")

        parts.append("drawtext=" + ":".join(tokens))

    return ",".join(parts)


def build_drawtext_filter_from_entries(
    entries: list[tuple[float, float, str]],
    *,
    fontsize: int = 34,
    fontcolor: str = "white",
    borderw: int = 3,
    bordercolor: str = "black",
    margin_bottom: int = 120,
    fontfile: str | None = None,
) -> str:
    """Build a drawtext filter chain from pre-parsed entries.

    Same as ``build_drawtext_filter`` but takes entries directly
    (useful for source credits where SRT is generated in-memory).
    """
    if not entries:
        return ""

    if fontfile is None:
        fontfile = find_cjk_font()

    parts: list[str] = []
    for start, end, text in entries:
        escaped = _escape_text(text)

        tokens = [
            f"text='{escaped}'",
            f"fontsize={fontsize}",
            f"fontcolor={fontcolor}",
            f"borderw={borderw}",
            f"bordercolor={bordercolor}",
            "x=(w-text_w)/2",
            f"y=h-text_h-{margin_bottom}",
            f"enable='gte(t,{start:.3f})*lte(t,{end:.3f})'",
        ]
        if fontfile:
            tokens.insert(1, f"fontfile='{fontfile}'")

        parts.append("drawtext=" + ":".join(tokens))

    return ",".join(parts)
