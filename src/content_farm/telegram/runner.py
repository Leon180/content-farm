"""Pipeline lifecycle manager — runs pipeline as background task."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from content_farm.compose.staging import StagingManager
from content_farm.config import Settings
from content_farm.pipeline.orchestrator import ContentPipeline
from content_farm.pipeline.state import PipelineStateDB
from content_farm.script_gen.schemas import ScriptRequest
from content_farm.telegram.approval import ApprovalGate
from content_farm.telegram.bot import TelegramBot
from content_farm.telegram.dispatcher import UpdateDispatcher
from content_farm.telegram.media import download_telegram_document
from content_farm.types import Tone, VideoLength

logger = logging.getLogger(__name__)


class PipelineRunner:
    """Manages pipeline execution lifecycle for the daemon bot.

    Enforces single-run (no concurrent pipelines).
    """

    def __init__(
        self,
        settings: Settings,
        dispatcher: UpdateDispatcher,
        bot: TelegramBot,
    ) -> None:
        self._settings = settings
        self._dispatcher = dispatcher
        self._bot = bot
        self._current_task: asyncio.Task[None] | None = None
        self._current_topic: str | None = None
        self._current_run_id: str | None = None
        self._staging: StagingManager | None = None

    @property
    def is_running(self) -> bool:
        return self._current_task is not None and not self._current_task.done()

    @property
    def status_summary(self) -> str:
        if not self.is_running:
            return "目前沒有執行中的 Pipeline。"
        return f"正在執行: {self._current_topic}"

    @property
    def last_checkable_run_id(self) -> str | None:
        """Find the most recent run that can be checked for missing artifacts."""
        return self._find_run_by_status("completed", "failed", "in_progress")

    @property
    def last_failed_run_id(self) -> str | None:
        """Find the most recent failed run for /retry."""
        return self._find_run_by_status("failed")

    @property
    def last_resumable_run_id(self) -> str | None:
        """Find the most recent failed or in_progress run for /continue."""
        return self._find_run_by_status("failed", "in_progress")

    def _find_run_by_status(self, *statuses: str) -> str | None:
        """Find the most recent run matching any of the given statuses."""
        output_dir = Path(self._settings.output_dir)
        db = PipelineStateDB(output_dir / "pipeline_state.db")
        try:
            runs = db.list_runs(limit=5)
            for run in runs:
                if run.status in statuses:
                    return run.run_id
        finally:
            db.close()
        return None

    def get_run_summary(self, run_id: str) -> str:
        """Get a human-readable summary of a run's checkpoint state."""
        output_dir = Path(self._settings.output_dir)
        db = PipelineStateDB(output_dir / "pipeline_state.db")
        try:
            run = db.get_run(run_id)
            if run is None:
                return f"Run {run_id} not found"
            next_stage = db.get_next_stage(run_id)
        finally:
            db.close()

        stages_done = ", ".join(run.completed_stages) or "none"
        return (
            f"Run: {run_id}\n"
            f"  主題: {run.topic}\n"
            f"  已完成: {stages_done}\n"
            f"  下一步: {next_stage or 'all done'}"
        )

    async def start(self, topic: str) -> None:
        """Start a pipeline run in the background."""
        if self.is_running:
            await self._bot.send_message(
                f"Pipeline 正在執行中 ({self._current_topic})。\n"
                "請等待完成或使用 /cancel 取消。"
            )
            return

        self._current_topic = topic
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._dispatcher.set_approval_queue(queue)

        await self._bot.send_message(f"Pipeline 啟動: {topic}")

        self._current_task = asyncio.create_task(
            self._run_pipeline(topic, queue),
        )
        self._current_task.add_done_callback(self._on_done)

    async def resume(self, run_id: str) -> None:
        """Resume a failed pipeline run from last checkpoint."""
        if self.is_running:
            await self._bot.send_message(
                f"Pipeline 正在執行中 ({self._current_topic})。"
            )
            return

        self._current_topic = f"resume:{run_id}"
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._dispatcher.set_approval_queue(queue)

        summary = self.get_run_summary(run_id)
        await self._bot.send_message(f"Pipeline 從 checkpoint 繼續:\n{summary}")

        self._current_task = asyncio.create_task(
            self._resume_pipeline(run_id, queue),
        )
        self._current_task.add_done_callback(self._on_done)

    async def cancel(self) -> None:
        """Cancel the running pipeline."""
        if not self.is_running:
            await self._bot.send_message("目前沒有執行中的 Pipeline。")
            return

        if self._dispatcher.has_approval_queue:
            # Put cancel sentinel for the approval gate
            queue = self._dispatcher._approval_queue
            if queue is not None:
                await queue.put({"_cancel": True})
        elif self._current_task is not None:
            self._current_task.cancel()

        await self._bot.send_message("正在取消 Pipeline...")

    def _on_done(self, task: asyncio.Task[None]) -> None:
        """Cleanup after pipeline completes."""
        self._dispatcher.set_approval_queue(None)
        self._current_task = None
        self._current_topic = None
        self._current_run_id = None

        if task.cancelled():
            logger.info("Pipeline task was cancelled")
        elif task.exception():
            exc = task.exception()
            logger.error("Pipeline task failed: %s", exc)
        else:
            logger.info("Pipeline task completed")

    async def _run_pipeline(
        self, topic: str, queue: asyncio.Queue[dict[str, Any]],
    ) -> None:
        """Execute materials pipeline with external approval gate."""
        gate = ApprovalGate(bot=self._bot, update_queue=queue)
        pipeline = ContentPipeline(
            settings=self._settings,
            output_dir=Path(self._settings.output_dir),
        )

        request = ScriptRequest(
            topic=topic,
            video_length=VideoLength.SHORT,
            tone=Tone.EDUCATIONAL,
            language="zh-TW",
        )

        await pipeline.run_materials_with_gate(request, gate)

    async def _resume_pipeline(
        self, run_id: str, queue: asyncio.Queue[dict[str, Any]],
    ) -> None:
        """Resume a failed pipeline with external approval gate."""
        gate = ApprovalGate(bot=self._bot, update_queue=queue)
        pipeline = ContentPipeline(
            settings=self._settings,
            output_dir=Path(self._settings.output_dir),
        )

        await pipeline.resume_with_gate(run_id, gate)

    # ------------------------------------------------------------------
    # Compose (material staging + composition)
    # ------------------------------------------------------------------

    async def start_compose(self, run_id: str | None = None) -> None:
        """Enter material staging mode for a run."""
        if self.is_running:
            await self._bot.send_message(
                f"Pipeline 正在執行中 ({self._current_topic})。"
            )
            return

        if self._staging is not None:
            await self._bot.send_message(
                f"已在素材合成模式中 (run: {self._staging.run_id})。\n"
                "傳送素材檔案或使用 /done 開始合成。"
            )
            return

        if run_id is None:
            run_id = self._find_run_by_status("completed", "in_progress")
            if run_id is None:
                await self._bot.send_message(
                    "沒有找到可合成的 run。請指定 run_id: /compose <run_id>"
                )
                return

        output_dir = Path(self._settings.output_dir)
        db = PipelineStateDB(output_dir / "pipeline_state.db")
        try:
            run_info = db.get_run(run_id)
            if run_info is None:
                await self._bot.send_message(f"Run {run_id} 不存在。")
                return

            # Check voice checkpoint exists
            voice_data = db.get_checkpoint(run_id, "voice")
            if not voice_data:
                await self._bot.send_message(
                    f"Run {run_id} 沒有語音資料，無法合成。"
                )
                return

            script_data = db.get_checkpoint(run_id, "script")
        finally:
            db.close()

        run_dir = Path(run_info.output_dir)
        audio_dir = run_dir / "audio"

        # Collect voice files and compute total duration
        voice_paths = tuple(sorted(audio_dir.glob("*.mp3")))
        if not voice_paths:
            await self._bot.send_message("找不到語音檔案。")
            return

        # Get total voice duration from voice artifact
        from content_farm.voice.schemas import VoiceArtifact

        voice = VoiceArtifact.model_validate(voice_data)
        total_duration = voice.total_duration_seconds

        # Re-save storyboard/script with actual voice durations
        if script_data:
            from content_farm.pipeline.stages import (
                save_script_files,
                sync_script_durations,
            )
            from content_farm.script_gen.schemas import Script

            script = Script.model_validate(script_data)
            synced_script = sync_script_durations(script, voice)
            save_script_files(synced_script, run_dir)

        # Check for subtitle file
        sub_dir = run_dir / "subtitles"
        subtitle_path: Path | None = None
        if sub_dir.is_dir():
            srt_files = list(sub_dir.glob("*.srt"))
            if srt_files:
                subtitle_path = srt_files[0]

        staging_dir = run_dir / "compose"
        self._staging = StagingManager(
            staging_dir=staging_dir,
            run_id=run_id,
            voice_duration=total_duration,
            voice_paths=voice_paths,
            subtitle_path=subtitle_path,
        )

        # Register document handler
        self._dispatcher.set_document_handler(
            lambda update: self.handle_staged_document(update),
        )

        await self._bot.send_message(
            f"進入素材合成模式 (run: {run_id})\n"
            f"影片總長: {total_duration:.0f}s\n\n"
            "請傳送素材檔案（document 模式），檔名格式:\n"
            "  MM:SStoMM:SS.mp4（例如 00:00to00:03.mp4）\n\n"
            "完成後輸入 /done 開始合成。"
        )

        # Send storyboard + script for reference
        await self._send_reference_docs(run_dir, voice)

    async def _send_reference_docs(
        self, run_dir: Path, voice: Any,
    ) -> None:
        """Send storyboard and scene timing to help user find materials."""
        # Build scene timing summary from voice segments
        lines = ["--- 場景時間軸 ---"]
        cursor = 0.0
        for seg in voice.segments:
            end = cursor + seg.duration_seconds
            lines.append(
                f"場景 {seg.scene_number}: "
                f"{int(cursor // 60):02d}:{int(cursor % 60):02d}"
                f"-{int(end // 60):02d}:{int(end % 60):02d} "
                f"({seg.duration_seconds:.0f}s)"
            )
            cursor = end
        await self._bot.send_message("\n".join(lines))

        # Send storyboard if available
        storyboard = run_dir / "storyboard.txt"
        if storyboard.is_file():
            content = storyboard.read_text(encoding="utf-8").strip()
            await self._bot.send_message(f"--- 分鏡稿 ---\n\n{content}")

        # Send script.json as document if available
        script_file = run_dir / "script.json"
        if script_file.is_file():
            await self._bot.send_document(script_file, caption="完整腳本")

    async def handle_staged_document(self, update: dict[str, Any]) -> None:
        """Download a document and add it to staging."""
        if self._staging is None:
            return

        result = await download_telegram_document(
            self._bot, update, self._staging.staging_dir,
        )
        if result is None:
            return

        file_path, filename = result
        clip_or_err = self._staging.add_clip(file_path, filename)

        if isinstance(clip_or_err, str):
            await self._bot.send_message(clip_or_err)
            return

        clip = clip_or_err
        await self._bot.send_message(
            f"收到: {clip.original_filename}\n"
            f"  {clip.start_seconds:.0f}-{clip.end_seconds:.0f}s "
            f"({clip.media_type})\n\n"
            f"{self._staging.format_summary()}"
        )

    async def finish_compose(self) -> None:
        """Trigger final composition from staged materials."""
        if self._staging is None:
            await self._bot.send_message(
                "尚未進入素材合成模式。請先使用 /compose [run_id]。"
            )
            return

        if self._staging.clip_count == 0:
            await self._bot.send_message(
                "尚未收到任何素材。請先傳送檔案再使用 /done。"
            )
            return

        staging = self._staging
        self._staging = None
        self._dispatcher.set_document_handler(None)

        self._current_topic = f"compose:{staging.run_id}"
        self._current_run_id = staging.run_id
        self._current_task = asyncio.create_task(
            self._compose_pipeline(staging),
        )
        self._current_task.add_done_callback(self._on_done)

    async def _compose_pipeline(self, staging: StagingManager) -> None:
        """Execute the compose workflow."""
        from content_farm.compose.timeline import build_timeline, compose_timeline

        try:
            await self._bot.send_message("開始合成...")

            clips = staging.get_clips()
            work_dir = staging.staging_dir

            await self._bot.send_message("正在建構時間軸...")
            segments = await build_timeline(
                clips,
                staging.voice_duration,
                work_dir,
                ffmpeg_path=self._settings.ffmpeg_path,
            )

            output_path = work_dir / "final_composed.mp4"
            await self._bot.send_message("正在合成影片...")
            result = await compose_timeline(
                segments,
                staging.voice_paths,
                output_path,
                subtitle_path=staging.subtitle_path,
                ffmpeg_path=self._settings.ffmpeg_path,
            )

            # Upload to Drive if configured
            drive_link = await self._upload_compose_result(
                staging.run_id, work_dir,
            )

            summary = (
                f"合成完成！\n"
                f"  素材: {result.clip_count} 段\n"
                f"  空白填充: {result.gap_count} 段\n"
                f"  總長: {result.duration_seconds:.0f}s"
            )
            if drive_link:
                summary += f"\n  Drive: {drive_link}"

            await self._bot.send_message(summary)

            # Send the video preview
            await self._bot.send_video(output_path, caption="合成結果預覽")

        except Exception as exc:
            logger.error("Compose failed: %s", exc)
            await self._bot.send_message(f"合成失敗: {exc}")

    async def _upload_compose_result(
        self, run_id: str, compose_dir: Path,
    ) -> str:
        """Upload compose output to the run's Drive folder."""
        from content_farm.drive.uploader import extract_folder_id
        from content_farm.pipeline.container import ServiceContainer

        container = ServiceContainer(self._settings)
        try:
            if not container.has_drive_credentials():
                return ""

            output_dir = Path(self._settings.output_dir)
            db = PipelineStateDB(output_dir / "pipeline_state.db")
            try:
                drive_link = db.get_checkpoint(run_id, "drive") or ""
            finally:
                db.close()

            if not isinstance(drive_link, str) or not drive_link:
                return ""

            folder_id = extract_folder_id(drive_link)
            if not folder_id:
                return ""

            uploader = container.create_drive_uploader()
            if uploader is None:
                return ""

            compose_folder_id = uploader.find_subfolder(folder_id, "compose")
            if not compose_folder_id:
                compose_folder_id = uploader.create_subfolder(
                    folder_id, "compose",
                )

            files = sorted(compose_dir.glob("final_composed.*"))
            if files:
                await uploader.upload_files(files, compose_folder_id)

            return drive_link
        except Exception:
            logger.warning("Drive upload for compose failed", exc_info=True)
            return ""
        finally:
            await container.close()

    async def fetch(self, run_id: str | None = None) -> None:
        """Check and re-fetch missing artifacts for a run."""
        if self.is_running:
            await self._bot.send_message(
                f"Pipeline 正在執行中 ({self._current_topic})。"
            )
            return

        if run_id is None:
            run_id = self.last_checkable_run_id
            if run_id is None:
                await self._bot.send_message(
                    "沒有找到可檢查的 run。請指定 run_id: /check <run_id>",
                )
                return

        self._current_topic = f"fetch:{run_id}"
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._dispatcher.set_approval_queue(queue)

        summary = self.get_run_summary(run_id)
        await self._bot.send_message(f"正在檢查 run 的素材...\n{summary}")

        self._current_task = asyncio.create_task(
            self._fetch_pipeline(run_id, queue),
        )
        self._current_task.add_done_callback(self._on_done)

    async def _fetch_pipeline(
        self, run_id: str, queue: asyncio.Queue[dict[str, Any]],
    ) -> None:
        """Execute the fetch workflow."""
        from content_farm.pipeline.container import ServiceContainer
        from content_farm.pipeline.fetch import fetch_missing_artifacts

        gate = ApprovalGate(bot=self._bot, update_queue=queue)
        container = ServiceContainer(self._settings)
        output_dir = Path(self._settings.output_dir)
        db = PipelineStateDB(output_dir / "pipeline_state.db")

        try:
            await fetch_missing_artifacts(
                run_id=run_id,
                settings=self._settings,
                container=container,
                gate=gate,
                db=db,
            )
        except Exception as exc:
            logger.error("Check failed for run %s: %s", run_id, exc)
            await self._bot.send_message(f"Check 失敗: {exc}")
        finally:
            await container.close()
            db.close()
