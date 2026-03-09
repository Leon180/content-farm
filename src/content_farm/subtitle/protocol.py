"""Subtitle provider protocol — abstraction for subtitle generation backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from content_farm.subtitle.schemas import SubtitleSegment


@runtime_checkable
class SubtitleProvider(Protocol):
    """Interface that all subtitle providers must implement."""

    async def generate_segments(
        self,
        text: str,
        *,
        duration_seconds: float,
        offset_seconds: float = 0.0,
    ) -> tuple[SubtitleSegment, ...]:
        """Split narration text into timed subtitle segments.

        Args:
            text: The narration text to split.
            duration_seconds: Total audio duration for this text.
            offset_seconds: Time offset for placing this scene
                within the full video timeline.

        Returns:
            Tuple of SubtitleSegment entries with absolute timestamps.
        """
        ...
