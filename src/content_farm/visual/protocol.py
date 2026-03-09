"""Visual provider protocol — abstraction for stock footage and AI generation."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from content_farm.visual.schemas import VideoResult


@runtime_checkable
class StockProvider(Protocol):
    """Interface for visual content providers (stock footage, AI generation)."""

    async def search_videos(
        self,
        query: str,
        *,
        min_duration: int = 5,
        max_duration: int = 30,
        orientation: str = "landscape",
        per_page: int = 5,
    ) -> tuple[VideoResult, ...]:
        """Search for videos matching the query.

        Returns a tuple of VideoResult objects sorted by relevance.
        """
        ...

    async def download_video(
        self,
        video: VideoResult,
        *,
        output_path: Path,
        quality: str = "hd",
    ) -> int:
        """Download a video to the specified path.

        Returns the number of bytes written.
        """
        ...
