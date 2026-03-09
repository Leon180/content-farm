"""Content pipeline orchestrator — wires all stages together."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from content_farm.assembly.assembler import VideoAssembler
from content_farm.assembly.factory import create_video_composer
from content_farm.assembly.schemas import AssemblyArtifact, AssemblyInput
from content_farm.config import Settings
from content_farm.llm.cache import FileCache, NullCache, ResponseCache
from content_farm.llm.client import LLMClient
from content_farm.script_gen.generator import ScriptGenerator
from content_farm.script_gen.schemas import Script, ScriptRequest
from content_farm.subtitle.factory import create_subtitle_provider
from content_farm.subtitle.generator import SubtitleGenerator
from content_farm.subtitle.schemas import SubtitleArtifact, SubtitleInput
from content_farm.telegram.approval import ApprovalGate
from content_farm.telegram.bot import TelegramBot
from content_farm.thumbnail.factory import create_thumbnail_provider
from content_farm.thumbnail.generator import ThumbnailGenerator
from content_farm.thumbnail.schemas import ThumbnailArtifact, ThumbnailInput
from content_farm.visual.factory import create_stock_provider
from content_farm.visual.generator import VisualGenerator
from content_farm.visual.schemas import VisualArtifact
from content_farm.voice.factory import create_tts_provider
from content_farm.voice.generator import VoiceGenerator
from content_farm.voice.schemas import VoiceArtifact
from content_farm.youtube.factory import create_youtube_uploader
from content_farm.youtube.generator import UploadGenerator
from content_farm.youtube.schemas import UploadArtifact, UploadInput

logger = logging.getLogger(__name__)


class PipelineResult(BaseModel):
    """Immutable result holding all pipeline artifacts."""

    model_config = {"frozen": True}

    script: Script
    voice: VoiceArtifact
    visual: VisualArtifact
    subtitle: SubtitleArtifact
    thumbnail: ThumbnailArtifact
    assembly: AssemblyArtifact
    upload: UploadArtifact | None = None
    output_dir: str


class ContentPipeline:
    """Orchestrates the full content creation pipeline.

    Flow:
        ScriptRequest → Script → [Telegram approval]
        → Voice + Visual (parallel) → [Telegram approval]
        → Subtitle + Thumbnail (parallel) → Assembly → Upload
    """

    def __init__(
        self,
        settings: Settings,
        *,
        output_dir: Path | None = None,
        use_cache: bool = True,
        skip_upload: bool = False,
    ) -> None:
        self._settings = settings
        self._base_output_dir = output_dir or Path("output")
        self._use_cache = use_cache
        self._skip_upload = skip_upload

    async def run(self, request: ScriptRequest) -> PipelineResult:
        """Execute the full content pipeline."""
        run_dir = self._create_run_dir(request.topic)
        logger.info("Pipeline started — output: %s", run_dir)

        gate = self._init_telegram()
        llm = LLMClient(api_key=self._settings.anthropic_api_key.get_secret_value())

        try:
            # --- Stage 1: Script Generation ---
            logger.info("[1/7] Generating script...")
            script = await self._generate_script(llm, request)
            logger.info("Script ready: %s (%d scenes)", script.video_title, len(script.scenes))

            # --- Telegram: check script ---
            await gate.check_script(script)

            # --- Stage 2+3: Voice + Visual (parallel) ---
            logger.info("[2/7] Generating voice + visual (parallel)...")
            voice, visual = await asyncio.gather(
                self._generate_voice(script, run_dir / "audio"),
                self._generate_visual(script, run_dir / "visual"),
            )
            logger.info("Voice: %d segments, Visual: %d assets", len(voice.segments), len(visual.assets))

            # --- Telegram: check visuals ---
            await gate.check_visuals(visual.assets)

            # --- Stage 4+5: Subtitle + Thumbnail (parallel) ---
            logger.info("[4/7] Generating subtitles + thumbnail (parallel)...")
            subtitle, thumbnail = await asyncio.gather(
                self._generate_subtitle(script, voice, run_dir / "subtitles"),
                self._generate_thumbnail(script, run_dir / "thumbnails"),
            )

            # --- Stage 6: Video Assembly ---
            logger.info("[6/7] Assembling video...")
            assembly = await self._assemble_video(
                script, voice, visual, subtitle, run_dir / "assembly",
            )
            logger.info("Video assembled: %s", assembly.file_path)

            # --- Stage 7: YouTube Upload ---
            upload: UploadArtifact | None = None
            if not self._skip_upload and self._has_youtube_credentials():
                logger.info("[7/7] Uploading to YouTube...")
                upload = await self._upload_video(script, assembly, thumbnail, subtitle)
                logger.info("Uploaded: %s", upload.url)
            else:
                logger.info("[7/7] YouTube upload skipped")

            result = PipelineResult(
                script=script,
                voice=voice,
                visual=visual,
                subtitle=subtitle,
                thumbnail=thumbnail,
                assembly=assembly,
                upload=upload,
                output_dir=str(run_dir),
            )
            logger.info("Pipeline complete — %s", run_dir)
            return result

        finally:
            await llm.close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_run_dir(self, topic: str) -> Path:
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_topic = re.sub(r"[^\w\u4e00-\u9fff]", "_", topic)[:30].strip("_")
        run_dir = self._base_output_dir / f"{timestamp}_{safe_topic}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _init_telegram(self) -> ApprovalGate:
        token = self._settings.telegram_bot_token.get_secret_value()
        chat_id = self._settings.telegram_chat_id
        if token and chat_id:
            bot = TelegramBot(token=token, chat_id=chat_id)
            return ApprovalGate(bot=bot)
        return ApprovalGate(bot=None)

    def _has_youtube_credentials(self) -> bool:
        return bool(
            self._settings.youtube_client_id.get_secret_value()
            and self._settings.youtube_client_secret.get_secret_value()
            and self._settings.youtube_refresh_token.get_secret_value()
        )

    async def _generate_script(
        self, llm: LLMClient, request: ScriptRequest,
    ) -> Script:
        cache: ResponseCache
        if self._use_cache:
            cache = FileCache(self._settings.cache_dir)
        else:
            cache = NullCache()
        gen = ScriptGenerator(llm=llm, cache=cache, settings=self._settings)
        return await gen.generate(request)

    async def _generate_voice(self, script: Script, output_dir: Path) -> VoiceArtifact:
        tts = create_tts_provider(self._settings)
        gen = VoiceGenerator(tts=tts, settings=self._settings, output_dir=output_dir)
        return await gen.generate(script)

    async def _generate_visual(self, script: Script, output_dir: Path) -> VisualArtifact:
        stock = create_stock_provider(self._settings)
        gen = VisualGenerator(stock=stock, settings=self._settings, output_dir=output_dir)
        return await gen.generate(script)

    async def _generate_subtitle(
        self, script: Script, voice: VoiceArtifact, output_dir: Path,
    ) -> SubtitleArtifact:
        provider = create_subtitle_provider(self._settings)
        gen = SubtitleGenerator(provider=provider, settings=self._settings, output_dir=output_dir)
        return await gen.generate(SubtitleInput(script=script, voice=voice))

    async def _generate_thumbnail(
        self, script: Script, output_dir: Path,
    ) -> ThumbnailArtifact:
        provider = create_thumbnail_provider(self._settings)
        gen = ThumbnailGenerator(provider=provider, settings=self._settings, output_dir=output_dir)
        return await gen.generate(ThumbnailInput(script=script))

    async def _assemble_video(
        self,
        script: Script,
        voice: VoiceArtifact,
        visual: VisualArtifact,
        subtitle: SubtitleArtifact,
        output_dir: Path,
    ) -> AssemblyArtifact:
        composer = create_video_composer(self._settings)
        assembler = VideoAssembler(
            composer=composer, settings=self._settings, output_dir=output_dir,
        )
        return await assembler.generate(AssemblyInput(
            script=script,
            voice=voice,
            visual=visual,
            subtitle_path=subtitle.file_path or None,
        ))

    async def _upload_video(
        self,
        script: Script,
        assembly: AssemblyArtifact,
        thumbnail: ThumbnailArtifact,
        subtitle: SubtitleArtifact,
    ) -> UploadArtifact:
        uploader = create_youtube_uploader(self._settings)
        gen = UploadGenerator(uploader=uploader, settings=self._settings)
        return await gen.generate(UploadInput(
            script=script,
            video_path=assembly.file_path,
            thumbnail_path=thumbnail.file_path or None,
            subtitle_path=subtitle.file_path or None,
            tags=script.tags,
        ))
