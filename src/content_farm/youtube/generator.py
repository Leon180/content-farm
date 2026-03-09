"""YouTube upload pipeline stage."""

from __future__ import annotations

import logging
from pathlib import Path

from content_farm.config import Settings
from content_farm.youtube.protocol import YouTubeUploader
from content_farm.youtube.schemas import UploadArtifact, UploadInput, UploadSettings

logger = logging.getLogger(__name__)


class UploadGenerator:
    """Orchestrates video upload, thumbnail, and captions."""

    def __init__(
        self,
        uploader: YouTubeUploader,
        settings: Settings,
        upload_settings: UploadSettings | None = None,
    ) -> None:
        self._uploader = uploader
        self._settings = settings
        self._upload_settings = upload_settings or UploadSettings()

    async def generate(self, upload_input: UploadInput) -> UploadArtifact:
        """Upload video and optionally set thumbnail + captions."""
        video_path = Path(upload_input.video_path)

        video_id = await self._uploader.upload_video(
            video_path=video_path,
            title=upload_input.script.video_title,
            description=upload_input.script.description,
            tags=upload_input.tags,
            settings=self._upload_settings,
        )

        thumbnail_set = False
        if upload_input.thumbnail_path:
            await self._uploader.set_thumbnail(
                video_id=video_id,
                thumbnail_path=Path(upload_input.thumbnail_path),
            )
            thumbnail_set = True

        captions_set = False
        if upload_input.subtitle_path:
            await self._uploader.set_captions(
                video_id=video_id,
                caption_path=Path(upload_input.subtitle_path),
                language=upload_input.script.language,
            )
            captions_set = True

        url = f"https://youtu.be/{video_id}"
        logger.info(
            "Upload complete: %s (thumbnail=%s, captions=%s)",
            url, thumbnail_set, captions_set,
        )

        return UploadArtifact(
            video_id=video_id,
            url=url,
            privacy_status=self._upload_settings.privacy_status,
            thumbnail_set=thumbnail_set,
            captions_set=captions_set,
        )


class UploadStage:
    """PipelineStage adapter for UploadGenerator."""

    def __init__(self, generator: UploadGenerator) -> None:
        self._generator = generator

    @property
    def name(self) -> str:
        return "youtube_upload"

    async def validate_input(self, input_data: UploadInput) -> None:
        if not isinstance(input_data, UploadInput):
            msg = f"Expected UploadInput, got {type(input_data)}"
            raise TypeError(msg)
        if not input_data.script.video_title.strip():
            raise ValueError("Script has no video_title for upload")
        video_path = Path(input_data.video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

    async def execute(self, input_data: UploadInput) -> UploadArtifact:
        return await self._generator.generate(input_data)
