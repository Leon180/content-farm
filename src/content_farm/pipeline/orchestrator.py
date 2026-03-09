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
from content_farm.pipeline.state import PipelineStateDB, RunStatus
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
from content_farm.visual.factory import create_image_provider, create_stock_provider
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
    drive_link: str = ""
    output_dir: str


class MaterialsResult(BaseModel):
    """Immutable result for materials-only mode."""

    model_config = {"frozen": True}

    script: Script
    voice: VoiceArtifact
    subtitle: SubtitleArtifact
    template_video_path: str
    drive_link: str
    output_dir: str


class ContentPipeline:
    """Orchestrates the full content creation pipeline.

    Supports two modes:
    - **materials**: Script → Voice → Subtitle → Template video → Drive upload
    - **full**: Script → Voice + Visual → Subtitle + Thumbnail → Assembly → Upload

    Supports checkpoint/resume: each stage saves its result to SQLite.
    On failure, `resume(run_id)` restarts from the last incomplete stage.
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
        self._db = PipelineStateDB(self._base_output_dir / "pipeline_state.db")

    # ------------------------------------------------------------------
    # Materials-only mode
    # ------------------------------------------------------------------

    async def run_materials(self, request: ScriptRequest) -> MaterialsResult:
        """Generate script + voice + subtitles + template video, deliver via Drive."""
        run_dir = self._create_run_dir(request.topic)
        run_id = self._db.create_run(request.topic, str(run_dir))
        logger.info("Materials pipeline started — run=%s output=%s", run_id, run_dir)

        gate, bot = self._init_telegram()
        llm = LLMClient(api_key=self._settings.anthropic_api_key.get_secret_value())

        try:
            # --- Stage 1: Script Generation ---
            logger.info("[1/5] Generating script...")
            script = await self._generate_script(llm, request)
            logger.info("Script ready: %s (%d scenes)", script.video_title, len(script.scenes))

            self._db.save_script(run_id, script.model_dump_json())
            self._db.save_checkpoint(run_id, "script")

            # --- Telegram: check script (with editing) ---
            approval = await gate.check_script(script)
            if approval.edited_script is not None:
                script = approval.edited_script
                self._db.save_script(run_id, script.model_dump_json())
                logger.info("Script updated by user edits")

            # --- Stage 2: Voice Generation ---
            logger.info("[2/5] Generating voice...")
            voice = await self._generate_voice(script, run_dir / "audio")
            self._db.save_checkpoint(run_id, "voice", voice.model_dump_json())

            # --- Stage 3: Subtitle Generation ---
            logger.info("[3/5] Generating subtitles...")
            subtitle = await self._generate_subtitle(script, voice, run_dir / "subtitles")
            self._db.save_checkpoint(run_id, "subtitle", subtitle.model_dump_json())

            # --- Stage 4: Template Video (blank bg + voice + subtitles) ---
            logger.info("[4/5] Creating template video...")
            template_path = await self._create_template_video(
                script, voice, subtitle, run_dir,
            )

            # --- Stage 5: Upload to Google Drive ---
            logger.info("[5/5] Uploading to Google Drive...")
            drive_link = await self._upload_to_drive(run_dir)

            # --- Telegram: deliver materials ---
            await gate.deliver_materials(script, drive_link)

            self._db.set_run_status(run_id, RunStatus.COMPLETED)

            result = MaterialsResult(
                script=script,
                voice=voice,
                subtitle=subtitle,
                template_video_path=str(template_path),
                drive_link=drive_link,
                output_dir=str(run_dir),
            )
            logger.info("Materials pipeline complete — run=%s", run_id)
            return result

        except Exception as exc:
            self._db.set_run_status(run_id, RunStatus.FAILED)
            await self._notify_error(gate, exc, run_id)
            raise
        finally:
            await llm.close()
            if bot is not None:
                await bot.close()

    # ------------------------------------------------------------------
    # Full pipeline mode
    # ------------------------------------------------------------------

    async def run(self, request: ScriptRequest) -> PipelineResult:
        """Execute the full content pipeline."""
        run_dir = self._create_run_dir(request.topic)
        run_id = self._db.create_run(request.topic, str(run_dir))
        logger.info("Pipeline started — run=%s output=%s", run_id, run_dir)

        gate, bot = self._init_telegram()
        llm = LLMClient(api_key=self._settings.anthropic_api_key.get_secret_value())

        try:
            logger.info("[1/7] Generating script...")
            script = await self._generate_script(llm, request)
            logger.info("Script ready: %s (%d scenes)", script.video_title, len(script.scenes))

            self._db.save_script(run_id, script.model_dump_json())
            self._db.save_checkpoint(run_id, "script")

            approval = await gate.check_script(script)
            if approval.edited_script is not None:
                script = approval.edited_script
                self._db.save_script(run_id, script.model_dump_json())

            result = await self._run_production(script, run_dir, gate, run_id)
            await self._notify_success(gate, result)
            return result

        except Exception as exc:
            self._db.set_run_status(run_id, RunStatus.FAILED)
            await self._notify_error(gate, exc, run_id)
            raise
        finally:
            await llm.close()
            if bot is not None:
                await bot.close()

    async def run_from_script(self, script: Script) -> PipelineResult:
        """Run production stages from a pre-approved script (skip generation + approval)."""
        topic = script.video_title or "untitled"
        run_dir = self._create_run_dir(topic)
        run_id = self._db.create_run(topic, str(run_dir))
        logger.info("Pipeline started from script — run=%s output=%s", run_id, run_dir)

        self._db.save_script(run_id, script.model_dump_json())
        self._db.save_checkpoint(run_id, "script")

        gate, bot = self._init_telegram()
        try:
            result = await self._run_production(script, run_dir, gate, run_id)
            await self._notify_success(gate, result)
            return result
        except Exception as exc:
            self._db.set_run_status(run_id, RunStatus.FAILED)
            await self._notify_error(gate, exc, run_id)
            raise
        finally:
            if bot is not None:
                await bot.close()

    async def resume(self, run_id: str) -> PipelineResult:
        """Resume a failed or interrupted pipeline run from its last checkpoint."""
        run_info = self._db.get_run(run_id)
        if run_info is None:
            raise ValueError(f"Run not found: {run_id}")

        run_dir = Path(run_info.output_dir)
        next_stage = self._db.get_next_stage(run_id)

        if next_stage is None:
            raise ValueError(f"Run {run_id} is already complete")

        script_json = self._db.get_script_json(run_id)
        if script_json is None:
            raise ValueError(f"Run {run_id} has no saved script — cannot resume")

        script = Script.model_validate_json(script_json)
        logger.info(
            "Resuming run %s from stage '%s' (completed: %s)",
            run_id, next_stage, ", ".join(run_info.completed_stages),
        )

        self._db.set_run_status(run_id, RunStatus.IN_PROGRESS)
        gate, bot = self._init_telegram()

        try:
            result = await self._run_production(script, run_dir, gate, run_id)
            await self._notify_success(gate, result)
            return result
        except Exception as exc:
            self._db.set_run_status(run_id, RunStatus.FAILED)
            await self._notify_error(gate, exc, run_id)
            raise
        finally:
            if bot is not None:
                await bot.close()

    async def _run_production(
        self,
        script: Script,
        run_dir: Path,
        gate: ApprovalGate,
        run_id: str,
    ) -> PipelineResult:
        """Run voice, visual, subtitle, thumbnail, assembly, and upload stages."""
        completed = set((self._db.get_run(run_id) or _empty_run()).completed_stages)

        voice: VoiceArtifact
        visual: VisualArtifact

        if "voice" in completed and "visual" in completed:
            logger.info("[2-3/7] Restoring voice + visual from checkpoint...")
            voice = VoiceArtifact.model_validate(self._db.get_checkpoint(run_id, "voice"))
            visual = VisualArtifact.model_validate(self._db.get_checkpoint(run_id, "visual"))
        else:
            logger.info("[2-3/7] Generating voice + visual (parallel)...")
            voice, visual = await asyncio.gather(
                self._generate_voice(script, run_dir / "audio"),
                self._generate_visual(script, run_dir / "visual"),
            )
            self._db.save_checkpoint(run_id, "voice", voice.model_dump_json())
            self._db.save_checkpoint(run_id, "visual", visual.model_dump_json())

        logger.info("Voice: %d segments, Visual: %d assets", len(voice.segments), len(visual.assets))

        # Skip visual approval if already past this stage (resuming)
        if "subtitle" not in completed:
            await gate.check_visuals(visual.assets)

        subtitle: SubtitleArtifact
        thumbnail: ThumbnailArtifact

        if "subtitle" in completed and "thumbnail" in completed:
            logger.info("[4-5/7] Restoring subtitle + thumbnail from checkpoint...")
            subtitle = SubtitleArtifact.model_validate(self._db.get_checkpoint(run_id, "subtitle"))
            thumbnail = ThumbnailArtifact.model_validate(self._db.get_checkpoint(run_id, "thumbnail"))
        else:
            logger.info("[4-5/7] Generating subtitles + thumbnail (parallel)...")
            subtitle, thumbnail = await asyncio.gather(
                self._generate_subtitle(script, voice, run_dir / "subtitles"),
                self._generate_thumbnail(script, run_dir / "thumbnails"),
            )
            self._db.save_checkpoint(run_id, "subtitle", subtitle.model_dump_json())
            self._db.save_checkpoint(run_id, "thumbnail", thumbnail.model_dump_json())

        assembly: AssemblyArtifact

        if "assembly" in completed:
            logger.info("[6/7] Restoring assembly from checkpoint...")
            assembly = AssemblyArtifact.model_validate(self._db.get_checkpoint(run_id, "assembly"))
        else:
            logger.info("[6/7] Assembling video...")
            assembly = await self._assemble_video(
                script, voice, visual, subtitle, run_dir / "assembly",
            )
            self._db.save_checkpoint(run_id, "assembly", assembly.model_dump_json())

        logger.info("Video assembled: %s", assembly.file_path)

        upload: UploadArtifact | None = None
        if "upload" in completed:
            upload_data = self._db.get_checkpoint(run_id, "upload")
            if upload_data:
                upload = UploadArtifact.model_validate(upload_data)
        elif not self._skip_upload and self._has_youtube_credentials():
            logger.info("[7/7] Uploading to YouTube...")
            upload = await self._upload_video(script, assembly, thumbnail, subtitle)
            self._db.save_checkpoint(run_id, "upload", upload.model_dump_json())
            logger.info("Uploaded: %s", upload.url)
        else:
            logger.info("[7/7] YouTube upload skipped")

        # --- Google Drive upload ---
        drive_link = ""
        if "drive" in completed:
            drive_link = self._db.get_checkpoint(run_id, "drive") or ""
        elif self._settings.drive_credentials_path and self._settings.drive_folder_id:
            logger.info("[8/8] Uploading to Google Drive...")
            drive_link = await self._upload_to_drive(run_dir)
            self._db.save_checkpoint(run_id, "drive", drive_link)
            logger.info("Drive link: %s", drive_link)
        else:
            logger.info("[8/8] Google Drive upload skipped")

        self._db.set_run_status(run_id, RunStatus.COMPLETED)

        # Clean up local files after successful Drive upload
        if drive_link and drive_link.startswith("http"):
            self._cleanup_local(run_dir)

        result = PipelineResult(
            script=script,
            voice=voice,
            visual=visual,
            subtitle=subtitle,
            thumbnail=thumbnail,
            assembly=assembly,
            upload=upload,
            drive_link=drive_link,
            output_dir=str(run_dir),
        )
        logger.info("Pipeline complete — run=%s dir=%s", run_id, run_dir)
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_run_dir(self, topic: str) -> Path:
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_topic = re.sub(r"[^\w\u4e00-\u9fff]", "_", topic)[:30].strip("_")
        run_dir = self._base_output_dir / f"{timestamp}_{safe_topic}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _init_telegram(self) -> tuple[ApprovalGate, TelegramBot | None]:
        token = self._settings.telegram_bot_token.get_secret_value()
        chat_id = self._settings.telegram_chat_id
        if token and chat_id:
            bot = TelegramBot(token=token, chat_id=chat_id)
            return ApprovalGate(bot=bot), bot
        return ApprovalGate(bot=None), None

    def _cleanup_local(self, run_dir: Path) -> None:
        """Remove large media files after successful Drive upload."""
        import shutil

        for subdir in ("assembly", "audio", "visual"):
            target = run_dir / subdir
            if target.is_dir():
                shutil.rmtree(target)
                logger.info("Cleaned up local: %s", target)

    async def _notify_success(self, gate: ApprovalGate, result: PipelineResult) -> None:
        try:
            await gate.notify_completion(
                video_path=result.assembly.file_path,
                output_dir=result.output_dir,
                upload_url=result.upload.url if result.upload else None,
                drive_link=result.drive_link or None,
            )
        except Exception:
            logger.warning("Failed to send completion notification", exc_info=True)

    async def _notify_error(
        self, gate: ApprovalGate, exc: Exception, run_id: str,
    ) -> None:
        try:
            await gate.notify_failure(error=str(exc), run_id=run_id)
        except Exception:
            logger.warning("Failed to send failure notification", exc_info=True)

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
        image_provider = create_image_provider(self._settings)
        gen = VisualGenerator(
            stock=stock, settings=self._settings, output_dir=output_dir,
            image_provider=image_provider,
        )
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

    async def _create_template_video(
        self,
        script: Script,
        voice: VoiceArtifact,
        subtitle: SubtitleArtifact,
        run_dir: Path,
    ) -> Path:
        """Create a template video: black background + voice + subtitles.

        If the script has sources, appends a subtitle-only credits section
        at the end (no voiceover).
        """
        from content_farm.visual.blank import generate_blank_visuals

        visual = await generate_blank_visuals(
            script, run_dir / "visual",
            ffmpeg_path=self._settings.ffmpeg_path,
        )
        assembly = await self._assemble_video(
            script, voice, visual, subtitle, run_dir / "assembly",
        )
        video_path = Path(assembly.file_path)

        if script.sources:
            from content_farm.assembly.sources import append_sources_to_video

            video_path = await append_sources_to_video(
                video_path,
                script.sources,
                run_dir / "assembly",
                ffmpeg_path=self._settings.ffmpeg_path,
            )

        return video_path

    async def _upload_to_drive(self, run_dir: Path) -> str:
        """Upload run directory to Google Drive, return shareable link."""
        from content_farm.drive.uploader import create_drive_uploader

        uploader = create_drive_uploader(
            credentials_path=self._settings.drive_credentials_path,
            folder_id=self._settings.drive_folder_id,
        )
        if uploader is None:
            logger.info("Google Drive not configured — skipping upload")
            return f"file://{run_dir}"

        folder_name = run_dir.name
        return await uploader.upload_folder(run_dir, folder_name)

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


def _empty_run() -> PipelineStateDB:
    """Placeholder for when get_run returns None mid-operation."""
    from content_farm.pipeline.state import RunInfo
    return RunInfo(
        run_id="", topic="", status="", output_dir="",
        completed_stages=(), created_at="", updated_at="",
    )
