"""YouTube uploader protocol — abstraction for upload backends."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from content_farm.youtube.schemas import UploadSettings


@runtime_checkable
class YouTubeUploader(Protocol):
    """Interface that all YouTube upload providers must implement."""

    async def upload_video(
        self,
        *,
        video_path: Path,
        title: str,
        description: str,
        tags: tuple[str, ...] = (),
        settings: UploadSettings | None = None,
    ) -> str:
        """Upload a video to YouTube.

        Returns the video ID.
        """
        ...

    async def set_thumbnail(
        self,
        *,
        video_id: str,
        thumbnail_path: Path,
    ) -> None:
        """Set a custom thumbnail for an uploaded video."""
        ...

    async def set_captions(
        self,
        *,
        video_id: str,
        caption_path: Path,
        language: str = "zh-TW",
    ) -> None:
        """Upload captions/subtitles for an uploaded video."""
        ...
