"""Content pipeline orchestrator — wires stages, checkpoints, and notifications."""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from pydantic import BaseModel

from content_farm.assembly.schemas import AssemblyArtifact
from content_farm.config import Settings
from content_farm.pipeline import stages
from content_farm.pipeline.container import ServiceContainer
from content_farm.pipeline.context import PipelineContext, create_run_dir
from content_farm.pipeline.state import PipelineStateDB, RunStatus
from content_farm.script_gen.schemas import Script, ScriptRequest
from content_farm.subtitle.schemas import SubtitleArtifact
from content_farm.telegram.approval import ApprovalGate
from content_farm.telegram.bot import TelegramBot
from content_farm.thumbnail.schemas import ThumbnailArtifact
from content_farm.visual.schemas import VisualArtifact
from content_farm.voice.schemas import VoiceArtifact
from content_farm.youtube.schemas import UploadArtifact

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

    Two modes:
    - **materials**: Script -> Voice -> Subtitle -> Template video -> Drive
    - **full**: Script -> Voice+Visual -> Subtitle+Thumbnail -> Assembly -> Upload

    Supports checkpoint/resume: each stage saves its result to SQLite.
    On failure, ``resume(run_id)`` restarts from the last incomplete stage.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        output_dir: Path | None = None,
        use_cache: bool = True,
        skip_upload: bool = False,
        container: ServiceContainer | None = None,
    ) -> None:
        self._settings = settings
        self._base_output_dir = output_dir or Path("output")
        self._skip_upload = skip_upload
        self._container = container or ServiceContainer(
            settings, use_cache=use_cache,
        )
        self._db = PipelineStateDB(self._base_output_dir / "pipeline_state.db")

    # ------------------------------------------------------------------
    # Materials-only mode
    # ------------------------------------------------------------------

    async def run_materials(self, request: ScriptRequest) -> MaterialsResult:
        """Generate script + voice + subtitles + template video, deliver via Drive."""
        gate, bot = self._init_telegram()
        try:
            return await self.run_materials_with_gate(request, gate)
        finally:
            if bot is not None:
                await bot.close()

    async def run_materials_with_gate(
        self, request: ScriptRequest, gate: ApprovalGate,
    ) -> MaterialsResult:
        """Run materials pipeline with an externally-managed ApprovalGate."""
        run_dir = create_run_dir(self._base_output_dir, request.topic)
        run_id = self._db.create_run(request.topic, str(run_dir))
        ctx = PipelineContext(
            settings=self._settings, run_id=run_id,
            run_dir=run_dir, gate=gate, mode="materials",
        )
        logger.info("Materials pipeline started — run=%s output=%s", run_id, run_dir)

        try:
            await self._run_materials_flow(ctx, request)
            return MaterialsResult(
                script=ctx.script,
                voice=ctx.voice,
                subtitle=ctx.subtitle,
                template_video_path=ctx.template_video_path,
                drive_link=ctx.drive_link,
                output_dir=str(run_dir),
            )
        except Exception as exc:
            self._db.set_run_status(run_id, RunStatus.FAILED)
            await self._notify_error(gate, exc, run_id)
            raise
        finally:
            await self._container.close()

    async def resume_with_gate(
        self, run_id: str, gate: ApprovalGate,
    ) -> MaterialsResult:
        """Resume a failed run from the last completed checkpoint."""
        ctx = self._load_context(run_id, gate, mode="materials")
        logger.info(
            "Resuming run %s — completed: %s",
            run_id, ctx.completed_stages,
        )

        try:
            await self._run_materials_flow(ctx)
            return MaterialsResult(
                script=ctx.script,
                voice=ctx.voice,
                subtitle=ctx.subtitle,
                template_video_path=ctx.template_video_path,
                drive_link=ctx.drive_link,
                output_dir=str(ctx.run_dir),
            )
        except Exception as exc:
            self._db.set_run_status(run_id, RunStatus.FAILED)
            await self._notify_error(gate, exc, run_id)
            raise
        finally:
            await self._container.close()

    async def _run_materials_flow(
        self,
        ctx: PipelineContext,
        request: ScriptRequest | None = None,
    ) -> None:
        """Shared materials pipeline logic (used by both run and resume)."""
        # 1. Script
        if request is not None:
            await self._run_stage(
                ctx, "script", 1, 5, "正在生成腳本...",
                stages.run_script_stage, request=request,
            )
        else:
            self._restore_artifact(ctx, "script")
        await self._check_script_approval(ctx)

        # 2. Voice
        await self._run_stage(
            ctx, "voice", 2, 5, "正在生成語音...",
            stages.run_voice_stage,
        )

        # 3. Subtitle
        await self._run_stage(
            ctx, "subtitle", 3, 5, "正在生成字幕...",
            stages.run_subtitle_stage,
        )

        # 4. Template video (blank bg + assembly + credits)
        if not ctx.is_completed("assembly"):
            await ctx.gate.notify_progress(4, 5, "正在建立模板影片...")
            await stages.run_blank_visual_stage(ctx, self._container)
            await stages.run_template_video_stage(ctx, self._container)
            self._save_checkpoint(ctx, "assembly")

        # 5. Drive upload
        await self._run_stage(
            ctx, "drive", 5, 5, "正在上傳至 Google Drive...",
            stages.run_drive_stage,
        )

        await ctx.gate.deliver_materials(ctx.script, ctx.drive_link)
        self._db.set_run_status(ctx.run_id, RunStatus.COMPLETED)
        logger.info("Materials pipeline complete — run=%s", ctx.run_id)

    # ------------------------------------------------------------------
    # Full pipeline mode
    # ------------------------------------------------------------------

    async def run(self, request: ScriptRequest) -> PipelineResult:
        """Execute the full content pipeline."""
        run_dir = create_run_dir(self._base_output_dir, request.topic)
        run_id = self._db.create_run(request.topic, str(run_dir))
        gate, bot = self._init_telegram()
        ctx = PipelineContext(
            settings=self._settings, run_id=run_id,
            run_dir=run_dir, gate=gate, mode="full",
        )
        logger.info("Pipeline started — run=%s output=%s", run_id, run_dir)

        try:
            # 1. Script
            await self._run_stage(
                ctx, "script", 1, 5, "正在生成腳本...",
                stages.run_script_stage, request=request,
            )
            await self._check_script_approval(ctx)

            result = await self._run_production(ctx)
            await self._notify_success(gate, result)
            return result

        except Exception as exc:
            self._db.set_run_status(run_id, RunStatus.FAILED)
            await self._notify_error(gate, exc, run_id)
            raise
        finally:
            await self._container.close()
            if bot is not None:
                await bot.close()

    async def run_from_script(self, script: Script) -> PipelineResult:
        """Run production stages from a pre-approved script."""
        topic = script.video_title or "untitled"
        run_dir = create_run_dir(self._base_output_dir, topic)
        run_id = self._db.create_run(topic, str(run_dir))
        gate, bot = self._init_telegram()
        ctx = PipelineContext(
            settings=self._settings, run_id=run_id,
            run_dir=run_dir, gate=gate, mode="full",
        )
        ctx.script = script

        self._db.save_script(run_id, script.model_dump_json())
        self._db.save_checkpoint(run_id, "script")
        ctx.mark_completed("script")

        try:
            result = await self._run_production(ctx, step_offset=0, total_steps=4)
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
        """Resume a failed or interrupted full pipeline run."""
        run_info = self._db.get_run(run_id)
        if run_info is None:
            raise ValueError(f"Run not found: {run_id}")

        next_stage = self._db.get_next_stage(run_id)
        if next_stage is None:
            raise ValueError(f"Run {run_id} is already complete")

        gate, bot = self._init_telegram()
        ctx = self._load_context(run_id, gate, mode="full")

        try:
            result = await self._run_production(ctx, step_offset=0, total_steps=4)
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
        ctx: PipelineContext,
        *,
        step_offset: int = 1,
        total_steps: int = 5,
    ) -> PipelineResult:
        """Run voice → visual → subtitle → thumbnail → assembly → upload → drive."""
        step = step_offset

        # Voice + Visual (parallel)
        step += 1
        await self._run_parallel_stages(
            ctx, step, total_steps, "正在生成語音 + 搜尋素材...",
            ("voice", stages.run_voice_stage),
            ("visual", stages.run_visual_stage),
        )
        # Visual approval (skip if resuming past this point)
        if "subtitle" not in ctx.completed_stages and ctx.visual:
            await ctx.gate.check_visuals(ctx.visual.assets)

        # Subtitle + Thumbnail (parallel)
        step += 1
        await self._run_parallel_stages(
            ctx, step, total_steps, "正在生成字幕 + 縮圖...",
            ("subtitle", stages.run_subtitle_stage),
            ("thumbnail", stages.run_thumbnail_stage),
        )

        # Assembly
        step += 1
        await self._run_stage(
            ctx, "assembly", step, total_steps, "正在合成影片...",
            stages.run_assembly_stage,
        )

        # YouTube upload
        step += 1
        if not self._skip_upload:
            await self._run_stage(
                ctx, "upload", step, total_steps, "正在上傳...",
                stages.run_upload_stage,
            )

        # Drive upload
        await self._run_stage(
            ctx, "drive", step, total_steps, None,
            stages.run_drive_stage,
        )

        self._db.set_run_status(ctx.run_id, RunStatus.COMPLETED)

        # Clean up local files after successful Drive upload
        if ctx.drive_link and ctx.drive_link.startswith("http"):
            self._cleanup_local(ctx.run_dir)

        result = PipelineResult(
            script=ctx.script,
            voice=ctx.voice,
            visual=ctx.visual,
            subtitle=ctx.subtitle,
            thumbnail=ctx.thumbnail,
            assembly=ctx.assembly,
            upload=ctx.upload,
            drive_link=ctx.drive_link,
            output_dir=str(ctx.run_dir),
        )
        logger.info("Pipeline complete — run=%s dir=%s", ctx.run_id, ctx.run_dir)
        return result

    # ------------------------------------------------------------------
    # Stage execution helpers
    # ------------------------------------------------------------------

    async def _run_stage(
        self,
        ctx: PipelineContext,
        stage_name: str,
        step: int,
        total: int,
        progress_msg: str | None,
        stage_fn,
        **kwargs,
    ) -> None:
        """Run a single stage with checkpoint load/skip/save logic."""
        if ctx.is_completed(stage_name):
            self._restore_artifact(ctx, stage_name)
            return

        if progress_msg:
            await ctx.gate.notify_progress(step, total, progress_msg)

        logger.info("[%d/%d] Running stage: %s", step, total, stage_name)
        await stage_fn(ctx, self._container, **kwargs)
        self._save_checkpoint(ctx, stage_name)

    async def _run_parallel_stages(
        self,
        ctx: PipelineContext,
        step: int,
        total: int,
        progress_msg: str,
        *stage_defs: tuple[str, ...],
    ) -> None:
        """Run multiple stages in parallel, skipping completed ones."""
        all_completed = all(ctx.is_completed(name) for name, _ in stage_defs)
        if all_completed:
            for name, _ in stage_defs:
                self._restore_artifact(ctx, name)
            return

        await ctx.gate.notify_progress(step, total, progress_msg)
        logger.info("[%d/%d] Running parallel: %s", step, total,
                    " + ".join(name for name, _ in stage_defs))

        await asyncio.gather(*(
            fn(ctx, self._container) for _, fn in stage_defs
        ))
        for name, _ in stage_defs:
            self._save_checkpoint(ctx, name)

    # ------------------------------------------------------------------
    # Checkpoint helpers
    # ------------------------------------------------------------------

    _ARTIFACT_MAP: dict[str, tuple[type, str]] = {
        "voice": (VoiceArtifact, "voice"),
        "visual": (VisualArtifact, "visual"),
        "subtitle": (SubtitleArtifact, "subtitle"),
        "thumbnail": (ThumbnailArtifact, "thumbnail"),
        "assembly": (AssemblyArtifact, "assembly"),
        "upload": (UploadArtifact, "upload"),
    }

    def _save_checkpoint(self, ctx: PipelineContext, stage: str) -> None:
        """Save artifact to DB after stage completion."""
        if stage == "script" and ctx.script is not None:
            self._db.save_script(ctx.run_id, ctx.script.model_dump_json())
            self._db.save_checkpoint(ctx.run_id, "script")
        elif stage == "drive":
            self._db.save_checkpoint(ctx.run_id, "drive", ctx.drive_link)
        elif stage in self._ARTIFACT_MAP:
            _, attr = self._ARTIFACT_MAP[stage]
            artifact = getattr(ctx, attr, None)
            artifact_json = artifact.model_dump_json() if artifact else None
            self._db.save_checkpoint(ctx.run_id, stage, artifact_json)
        else:
            self._db.save_checkpoint(ctx.run_id, stage)
        ctx.mark_completed(stage)

    def _restore_artifact(self, ctx: PipelineContext, stage: str) -> None:
        """Load artifact from DB checkpoint into context."""
        if stage == "script":
            json_str = self._db.get_script_json(ctx.run_id)
            if json_str:
                ctx.script = Script.model_validate_json(json_str)
            return

        if stage == "drive":
            ctx.drive_link = self._db.get_checkpoint(ctx.run_id, "drive") or ""
            return

        if stage in self._ARTIFACT_MAP:
            data = self._db.get_checkpoint(ctx.run_id, stage)
            if data is not None:
                model_cls, attr = self._ARTIFACT_MAP[stage]
                setattr(ctx, attr, model_cls.model_validate(data))

    def _load_context(
        self, run_id: str, gate: ApprovalGate, *, mode: str = "materials",
    ) -> PipelineContext:
        """Build PipelineContext from saved checkpoint data."""
        run_info = self._db.get_run(run_id)
        if run_info is None:
            raise ValueError(f"Run not found: {run_id}")

        ctx = PipelineContext(
            settings=self._settings,
            run_id=run_id,
            run_dir=Path(run_info.output_dir),
            gate=gate,
            mode=mode,
            completed_stages=set(run_info.completed_stages),
        )

        for stage_name in run_info.completed_stages:
            self._restore_artifact(ctx, stage_name)

        self._db.set_run_status(run_id, RunStatus.IN_PROGRESS)
        return ctx

    # ------------------------------------------------------------------
    # Approval / notification helpers
    # ------------------------------------------------------------------

    async def _check_script_approval(self, ctx: PipelineContext) -> None:
        """Send script for human review; apply edits if any."""
        if ctx.script is None:
            return
        approval = await ctx.gate.check_script(ctx.script)
        if approval.edited_script is not None:
            ctx.script = approval.edited_script
            self._db.save_script(ctx.run_id, ctx.script.model_dump_json())
            logger.info("Script updated by user edits")

    def _init_telegram(self) -> tuple[ApprovalGate, TelegramBot | None]:
        token = self._settings.telegram_bot_token.get_secret_value()
        chat_id = self._settings.telegram_chat_id
        if token and chat_id:
            bot = TelegramBot(token=token, chat_id=chat_id)
            return ApprovalGate(bot=bot), bot
        return ApprovalGate(bot=None), None

    async def _notify_success(
        self, gate: ApprovalGate, result: PipelineResult,
    ) -> None:
        try:
            await gate.notify_completion(
                video_path=result.assembly.file_path,
                output_dir=result.output_dir,
                script=result.script,
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

    @staticmethod
    def _cleanup_local(run_dir: Path) -> None:
        """Remove large media files after successful Drive upload."""
        for subdir in ("assembly", "audio", "visual"):
            target = run_dir / subdir
            if target.is_dir():
                shutil.rmtree(target)
                logger.info("Cleaned up local: %s", target)