"""Thumbnail generation pipeline stage."""

from __future__ import annotations

import logging
from pathlib import Path

from content_farm.config import Settings
from content_farm.thumbnail.protocol import ThumbnailProvider
from content_farm.thumbnail.schemas import (
    ThumbnailArtifact,
    ThumbnailInput,
    ThumbnailSettings,
)

logger = logging.getLogger(__name__)


class ThumbnailGenerator:
    """Generates a YouTube thumbnail for a video script."""

    def __init__(
        self,
        provider: ThumbnailProvider,
        settings: Settings,
        thumbnail_settings: ThumbnailSettings | None = None,
        output_dir: Path | None = None,
    ) -> None:
        self._provider = provider
        self._settings = settings
        self._thumb_settings = thumbnail_settings or ThumbnailSettings()
        self._output_dir = output_dir or Path("output/thumbnails")

    async def generate(self, thumb_input: ThumbnailInput) -> ThumbnailArtifact:
        """Generate a single thumbnail JPEG."""
        self._output_dir.mkdir(parents=True, exist_ok=True)

        output_path = self._output_dir / "thumbnail.jpg"
        video_path = Path(thumb_input.video_path) if thumb_input.video_path else None
        bg_path = (
            Path(thumb_input.background_image_path)
            if thumb_input.background_image_path
            else None
        )

        file_size = await self._provider.render(
            title=thumb_input.script.video_title,
            output_path=output_path,
            video_path=video_path,
            background_image_path=bg_path,
            settings=self._thumb_settings,
        )

        used_keyframe = video_path is not None and video_path.exists()

        logger.info(
            "Generated thumbnail: %s (%d bytes, keyframe=%s)",
            output_path, file_size, used_keyframe,
        )

        return ThumbnailArtifact(
            file_path=str(output_path),
            width=self._thumb_settings.width,
            height=self._thumb_settings.height,
            file_size_bytes=file_size,
            used_keyframe=used_keyframe,
            output_dir=str(self._output_dir),
        )


class ThumbnailStage:
    """PipelineStage adapter for ThumbnailGenerator."""

    def __init__(self, generator: ThumbnailGenerator) -> None:
        self._generator = generator

    @property
    def name(self) -> str:
        return "thumbnail_generation"

    async def validate_input(self, input_data: ThumbnailInput) -> None:
        if not isinstance(input_data, ThumbnailInput):
            msg = f"Expected ThumbnailInput, got {type(input_data)}"
            raise TypeError(msg)
        if not input_data.script.video_title.strip():
            raise ValueError("Script has no video_title for thumbnail text")

    async def execute(self, input_data: ThumbnailInput) -> ThumbnailArtifact:
        return await self._generator.generate(input_data)
