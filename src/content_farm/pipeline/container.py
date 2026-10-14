"""Service container — lazy-initialized dependency factory."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING
import typing

from content_farm.config import Settings

if TYPE_CHECKING:
    from content_farm.llm.client import LLMClient
    from content_farm.llm.cache import ResponseCache
    from content_farm.script_gen.generator import ScriptGenerator
    from content_farm.voice.generator import VoiceGenerator
    from content_farm.visual.generator import VisualGenerator
    from content_farm.subtitle.generator import SubtitleGenerator
    from content_farm.thumbnail.generator import ThumbnailGenerator
    from content_farm.assembly.assembler import VideoAssembler
    from content_farm.youtube.generator import UploadGenerator
    from content_farm.drive.uploader import DriveUploader
    from content_farm.types import Orientation

logger = logging.getLogger(__name__)


class ServiceContainer:
    """Lazy-initialized service container.

    Accepts Settings. Generator construction is deferred to first access.
    Per-run generators that need ``output_dir`` use ``create_*`` methods
    (not properties) since they produce a new instance per call.
    Call ``close()`` when done to release resources.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        use_cache: bool = True,
    ) -> None:
        self._settings = settings
        self._use_cache = use_cache
        self._llm_client: typing.Any | None = None

    @property
    def settings(self) -> Settings:
        return self._settings

    # ------------------------------------------------------------------
    # Singletons (cached on first access)
    # ------------------------------------------------------------------

    @property
    def llm_client(self) -> "LLMClient":
        """Return (or create) the shared LLM client."""
        if self._llm_client is None:
            from content_farm.llm.client import LLMClient

            self._llm_client = LLMClient(
                api_key=self._settings.anthropic_api_key.get_secret_value(),
            )
        return self._llm_client

    @property
    def cache(self) -> "ResponseCache":
        """Return the configured response cache."""
        from content_farm.llm.cache import FileCache, NullCache

        if self._use_cache:
            return FileCache(self._settings.cache_dir)
        return NullCache()

    # ------------------------------------------------------------------
    # Per-run factories (new instance each call)
    # ------------------------------------------------------------------

    def create_script_generator(self) -> "ScriptGenerator":
        from content_farm.script_gen.generator import ScriptGenerator

        return ScriptGenerator(
            llm=self.llm_client,
            cache=self.cache,
            settings=self._settings,
        )

    def create_voice_generator(self, output_dir: Path) -> "VoiceGenerator":
        from content_farm.voice.factory import create_tts_provider
        from content_farm.voice.generator import VoiceGenerator

        tts = create_tts_provider(self._settings)
        return VoiceGenerator(
            tts=tts, settings=self._settings, output_dir=output_dir,
        )

    def create_visual_generator(self, output_dir: Path) -> "VisualGenerator":
        from content_farm.visual.factory import (
            create_image_provider,
            create_stock_provider,
        )
        from content_farm.visual.generator import VisualGenerator

        return VisualGenerator(
            stock=create_stock_provider(self._settings),
            settings=self._settings,
            output_dir=output_dir,
            image_provider=create_image_provider(self._settings),
        )

    def create_subtitle_generator(
        self, output_dir: Path, orientation: "Orientation | None" = None,
    ) -> "SubtitleGenerator":
        from content_farm.subtitle.factory import create_subtitle_provider
        from content_farm.subtitle.generator import SubtitleGenerator

        return SubtitleGenerator(
            provider=create_subtitle_provider(self._settings, orientation),
            settings=self._settings,
            output_dir=output_dir,
        )

    def create_thumbnail_generator(self, output_dir: Path) -> "ThumbnailGenerator":
        from content_farm.thumbnail.factory import create_thumbnail_provider
        from content_farm.thumbnail.generator import ThumbnailGenerator

        return ThumbnailGenerator(
            provider=create_thumbnail_provider(self._settings),
            settings=self._settings,
            output_dir=output_dir,
        )

    def create_video_assembler(self, output_dir: Path) -> "VideoAssembler":
        from content_farm.assembly.assembler import VideoAssembler
        from content_farm.assembly.factory import create_video_composer

        return VideoAssembler(
            composer=create_video_composer(self._settings),
            settings=self._settings,
            output_dir=output_dir,
        )

    def create_upload_generator(
        self,
        upload_settings: "UploadSettings | None" = None,
    ) -> "UploadGenerator":
        from content_farm.youtube.factory import create_youtube_uploader
        from content_farm.youtube.generator import UploadGenerator

        return UploadGenerator(
            uploader=create_youtube_uploader(self._settings),
            settings=self._settings,
            upload_settings=upload_settings,
        )

    def create_drive_uploader(self) -> "DriveUploader | None":
        from content_farm.drive.uploader import create_drive_uploader, DriveUploader

        return create_drive_uploader(
            credentials_path=self._settings.drive_credentials_path,
            folder_id=self._settings.drive_folder_id,
            project_root=str(self._settings.project_root),
        )

    # ------------------------------------------------------------------
    # Capability checks
    # ------------------------------------------------------------------

    def has_youtube_credentials(self) -> bool:
        s = self._settings
        return bool(
            s.youtube_client_id.get_secret_value()
            and s.youtube_client_secret.get_secret_value()
            and s.youtube_refresh_token.get_secret_value()
        )

    def has_drive_credentials(self) -> bool:
        return bool(
            self._settings.drive_credentials_path
            and self._settings.drive_folder_id
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Release resources held by cached services."""
        if self._llm_client is not None:
            close = getattr(self._llm_client, "close", None)
            if close is not None:
                await close()
            self._llm_client = None