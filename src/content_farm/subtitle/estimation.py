"""Estimation-based subtitle provider for zh-TW content.

Splits narration text into subtitle segments proportionally
based on character count and audio duration.  Inserts brief
gaps after sentence-ending punctuation for dramatic pacing.
"""

from __future__ import annotations

import re

from content_farm.subtitle.schemas import SubtitleSegment

_MIN_CHARS = 10
_MAX_CHARS = 22
_TARGET_CHARS = 17

# Punctuation where we prefer to break (zh + latin).
_BREAK_PUNCT = re.compile(r"[，。！？；：、\n,.!?;:]")

# Sentence-ending punctuation that triggers a dramatic gap.
_SENTENCE_END = re.compile(r"[。！？!?]$")

# Default gap inserted after sentence-ending punctuation (seconds).
_DEFAULT_GAP = 0.35


class EstimationProvider:
    """Generates subtitle segments by distributing timestamps proportionally.

    Sentence-ending marks (。！？) automatically insert a brief gap
    (default 0.35 s) after the subtitle disappears.  Use ``……`` in
    the narration for an extra-long pause (~0.7 s double gap).
    """

    def __init__(
        self,
        *,
        target_chars: int = _TARGET_CHARS,
        min_chars: int = _MIN_CHARS,
        max_chars: int = _MAX_CHARS,
        sentence_gap: float = _DEFAULT_GAP,
    ) -> None:
        self._target_chars = target_chars
        self._min_chars = min_chars
        self._max_chars = max_chars
        self._sentence_gap = sentence_gap

    async def generate_segments(
        self,
        text: str,
        *,
        duration_seconds: float,
        offset_seconds: float = 0.0,
    ) -> tuple[SubtitleSegment, ...]:
        """Split *text* into timed subtitle segments with dramatic gaps."""
        if not text.strip():
            return ()

        chunks = self._split_text(text)
        if not chunks:
            return ()

        total_chars = sum(len(c) for c in chunks)
        if total_chars == 0:
            return ()

        # Count how many gaps we'll insert (every chunk that ends with 。！？
        # EXCEPT the very last chunk — no gap needed after final subtitle).
        gap_count = sum(
            1 for c in chunks[:-1] if _SENTENCE_END.search(c)
        )
        # Extra-long pause for ……
        ellipsis_count = sum(
            1 for c in chunks[:-1] if c.rstrip("。！？!?").endswith("……")
        )
        total_gap = gap_count * self._sentence_gap + ellipsis_count * self._sentence_gap
        speech_duration = max(duration_seconds - total_gap, duration_seconds * 0.5)

        segments: list[SubtitleSegment] = []
        current_time = offset_seconds

        for i, chunk in enumerate(chunks):
            proportion = len(chunk) / total_chars
            chunk_duration = proportion * speech_duration
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

            # Insert gap after sentence-ending punctuation (not last chunk)
            if i < len(chunks) - 1 and _SENTENCE_END.search(chunk):
                gap = self._sentence_gap
                if chunk.rstrip("。！？!?").endswith("……"):
                    gap += self._sentence_gap  # double gap for ellipsis
                current_time += gap

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
