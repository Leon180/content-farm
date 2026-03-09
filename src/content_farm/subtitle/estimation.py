"""Estimation-based subtitle provider for zh-TW content.

Splits narration text into subtitle segments proportionally
based on character count and audio duration. No ASR needed.
"""

from __future__ import annotations

import re

from content_farm.subtitle.schemas import SubtitleSegment

_MIN_CHARS = 10
_MAX_CHARS = 22
_TARGET_CHARS = 17

# Punctuation where we prefer to break (zh + latin).
_BREAK_PUNCT = re.compile(r"[，。！？；：、\n,.!?;:]")


class EstimationProvider:
    """Generates subtitle segments by distributing timestamps proportionally."""

    def __init__(
        self,
        *,
        target_chars: int = _TARGET_CHARS,
        min_chars: int = _MIN_CHARS,
        max_chars: int = _MAX_CHARS,
    ) -> None:
        self._target_chars = target_chars
        self._min_chars = min_chars
        self._max_chars = max_chars

    async def generate_segments(
        self,
        text: str,
        *,
        duration_seconds: float,
        offset_seconds: float = 0.0,
    ) -> tuple[SubtitleSegment, ...]:
        """Split *text* into timed subtitle segments."""
        if not text.strip():
            return ()

        chunks = self._split_text(text)
        if not chunks:
            return ()

        total_chars = sum(len(c) for c in chunks)
        if total_chars == 0:
            return ()

        segments: list[SubtitleSegment] = []
        current_time = offset_seconds

        for i, chunk in enumerate(chunks):
            proportion = len(chunk) / total_chars
            chunk_duration = proportion * duration_seconds
            end_time = current_time + chunk_duration

            segments.append(
                SubtitleSegment(
                    index=i + 1,
                    start_seconds=round(current_time, 3),
                    end_seconds=round(end_time, 3),
                    text=chunk.strip(),
                    scene_number=0,  # Set by generator
                )
            )
            current_time = end_time

        return tuple(segments)

    def _split_text(self, text: str) -> list[str]:
        """Split *text* into chunks, preferring punctuation break points."""
        text = text.strip()
        if len(text) <= self._max_chars:
            return [text]

        chunks: list[str] = []
        remaining = text

        while remaining:
            if len(remaining) <= self._max_chars:
                if remaining.strip():
                    chunks.append(remaining.strip())
                break

            # Search backward from max_chars for a punctuation break.
            best_break = self._target_chars
            window_end = min(self._max_chars, len(remaining))

            found_punct = False
            for pos in range(window_end, self._min_chars - 1, -1):
                if pos < len(remaining) and _BREAK_PUNCT.match(remaining[pos]):
                    best_break = pos + 1  # Include the punctuation char
                    found_punct = True
                    break

            if not found_punct:
                best_break = min(self._target_chars, len(remaining))

            chunk = remaining[:best_break]
            remaining = remaining[best_break:].lstrip()
            stripped = chunk.strip()
            if stripped:
                chunks.append(stripped)

        return chunks
