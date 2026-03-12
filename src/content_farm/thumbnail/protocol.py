"""Thumbnail provider protocol — abstraction for thumbnail rendering backends."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from content_farm.thumbnail.schemas import ThumbnailSettings


@runtime_checkable
class ThumbnailProvider(Protocol):
    """Interface that all thumbnail providers must implement."""

    async def render(
        self,
        *,
        title: str,
        output_path: Path,
        video_path: Path | None = None,
        background_image_path: Path | None = None,
        settings: ThumbnailSettings | None = None,
    ) -> int:
        """Render a YouTube thumbnail image.

        Args:
            title: Text to overlay on the thumbnail.
            output_path: Where to save the JPEG.
            video_path: Optional MP4 for keyframe extraction.
            background_image_path: Optional stock photo for background.
            settings: Render parameters (uses defaults if None).

        Returns:
            File size in bytes.
        """
        ...
