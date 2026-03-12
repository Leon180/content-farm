"""Pipeline stage implementations — stateless async functions.

Each stage takes ``(ctx, container, **kwargs)`` and writes its
artifact into the corresponding ``ctx`` slot.  The orchestrator
handles checkpoint save/load and progress notifications around
these functions.
"""

from __future__ import annotations

import json as _json
import logging
from pathlib import Path

from content_farm.pipeline.container import ServiceContainer
from content_farm.pipeline.context import PipelineContext
from content_farm.script_gen.schemas import ScriptRequest

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Script
# ------------------------------------------------------------------


async def run_script_stage(
    ctx: PipelineContext,
    container: ServiceContainer,
    *,
    request: ScriptRequest,
) -> None:
    """Generate script via LLM (two-phase: outline then expand)."""
    gen = container.create_script_generator()
    ctx.script = await gen.generate(request)


# ------------------------------------------------------------------
# Voice
# ------------------------------------------------------------------


async def run_voice_stage(
    ctx: PipelineContext,
    container: ServiceContainer,
) -> None:
    """Generate audio narration for all scenes."""
    assert ctx.script is not None
    gen = container.create_voice_generator(ctx.run_dir / "audio")
    ctx.voice = await gen.generate(ctx.script)

    # Sync script durations with actual voice measurements so downstream
    # stages (subtitle, storyboard, etc.) use real timings.
    ctx.script = sync_script_durations(ctx.script, ctx.voice)


# ------------------------------------------------------------------
# Visual (stock footage / AI images)
# ------------------------------------------------------------------


async def run_visual_stage(
    ctx: PipelineContext,
    container: ServiceContainer,
) -> None:
    """Source stock footage or AI images for all scenes."""
    assert ctx.script is not None
    gen = container.create_visual_generator(ctx.run_dir / "visual")
    ctx.visual = await gen.generate(ctx.script)


# ------------------------------------------------------------------
# Blank visual (materials mode)
# ------------------------------------------------------------------


async def run_blank_visual_stage(
    ctx: PipelineContext,
    container: ServiceContainer,
) -> None:
    """Generate black-screen video clips for template assembly."""
    from content_farm.visual.blank import generate_blank_visuals

    assert ctx.script is not None
    ctx.visual = await generate_blank_visuals(
        ctx.script,
        ctx.run_dir / "visual",
        ffmpeg_path=container.settings.ffmpeg_path,
    )


# ------------------------------------------------------------------
# Subtitle
# ------------------------------------------------------------------


async def run_subtitle_stage(
    ctx: PipelineContext,
    container: ServiceContainer,
) -> None:
    """Generate subtitles from script + voice timing."""
    from content_farm.subtitle.schemas import SubtitleInput

    assert ctx.script is not None and ctx.voice is not None
    gen = container.create_subtitle_generator(ctx.run_dir / "subtitles")
    ctx.subtitle = await gen.generate(
        SubtitleInput(script=ctx.script, voice=ctx.voice),
    )


# ------------------------------------------------------------------
# Thumbnail
# ------------------------------------------------------------------


async def run_thumbnail_stage(
    ctx: PipelineContext,
    container: ServiceContainer,
) -> None:
    """Generate video thumbnail from script + optional video keyframe."""
    from content_farm.thumbnail.schemas import ThumbnailInput

    assert ctx.script is not None

    video_path = _find_thumbnail_video(ctx)
    gen = container.create_thumbnail_generator(ctx.run_dir / "thumbnails")
    ctx.thumbnail = await gen.generate(
        ThumbnailInput(
            script=ctx.script,
            video_path=video_path,
        ),
    )


def _find_thumbnail_video(ctx: PipelineContext) -> str | None:
    """Find a video file for keyframe extraction.

    PillowProvider extracts a keyframe at ~25% of the video as
    thumbnail background.
    """
    if ctx.visual and ctx.visual.assets:
        first = ctx.visual.assets[0]
        if first.file_path and Path(first.file_path).exists():
            return first.file_path

    visual_dir = ctx.run_dir / "visual"
    if visual_dir.is_dir():
        mp4s = sorted(visual_dir.glob("scene_*.mp4"))
        if mp4s:
            return str(mp4s[0])

    return None


# ------------------------------------------------------------------
# Assembly
# ------------------------------------------------------------------


async def run_assembly_stage(
    ctx: PipelineContext,
    container: ServiceContainer,
) -> None:
    """Assemble final video from voice + visual + subtitles."""
    from content_farm.assembly.schemas import AssemblyInput

    assert ctx.script is not None
    assert ctx.voice is not None
    assert ctx.visual is not None

    assembler = container.create_video_assembler(ctx.run_dir / "assembly")
    ctx.assembly = await assembler.generate(AssemblyInput(
        script=ctx.script,
        voice=ctx.voice,
        visual=ctx.visual,
        subtitle_path=ctx.subtitle.file_path if ctx.subtitle else None,
    ))


# ------------------------------------------------------------------
# Template video (materials mode: blank bg + assembly + credits)
# ------------------------------------------------------------------


async def run_template_video_stage(
    ctx: PipelineContext,
    container: ServiceContainer,
) -> None:
    """Create template video with blank background + credits."""
    # First assemble the blank visuals with voice + subtitles
    await run_assembly_stage(ctx, container)

    assert ctx.assembly is not None
    video_path = Path(ctx.assembly.file_path)

    # Append source credits if the script has sources
    if ctx.script and ctx.script.sources:
        from content_farm.assembly.sources import append_sources_to_video

        video_path = await append_sources_to_video(
            video_path,
            ctx.script.sources,
            ctx.run_dir / "assembly",
            ffmpeg_path=container.settings.ffmpeg_path,
        )

    ctx.template_video_path = str(video_path)


# ------------------------------------------------------------------
# YouTube upload
# ------------------------------------------------------------------


async def run_upload_stage(
    ctx: PipelineContext,
    container: ServiceContainer,
) -> None:
    """Upload to YouTube (skipped if no credentials)."""
    from content_farm.youtube.schemas import UploadInput

    if not container.has_youtube_credentials():
        logger.info("YouTube upload skipped — no credentials")
        return

    assert ctx.script is not None and ctx.assembly is not None

    gen = container.create_upload_generator()
    ctx.upload = await gen.generate(UploadInput(
        script=ctx.script,
        video_path=ctx.assembly.file_path,
        thumbnail_path=ctx.thumbnail.file_path if ctx.thumbnail else None,
        subtitle_path=ctx.subtitle.file_path if ctx.subtitle else None,
        tags=ctx.script.tags,
    ))


# ------------------------------------------------------------------
# Google Drive upload
# ------------------------------------------------------------------


async def run_drive_stage(
    ctx: PipelineContext,
    container: ServiceContainer,
) -> None:
    """Upload run directory to Google Drive."""
    if not container.has_drive_credentials():
        logger.info("Google Drive upload skipped — not configured")
        ctx.drive_link = f"file://{ctx.run_dir}"
        return

    # Save script files for human editors before uploading
    save_script_files(ctx.script, ctx.run_dir)

    uploader = container.create_drive_uploader()
    if uploader is None:
        ctx.drive_link = f"file://{ctx.run_dir}"
        return

    ctx.drive_link = await uploader.upload_folder(
        ctx.run_dir, ctx.run_dir.name,
    )


# ------------------------------------------------------------------
# Artifact audit (used by /fetch)
# ------------------------------------------------------------------


def audit_artifacts(ctx: PipelineContext) -> list[str]:
    """Return stage names whose output files are missing on disk.

    Useful for ``/fetch`` to detect which stages need re-running.
    """
    missing: list[str] = []

    if ctx.voice and ctx.voice.segments:
        if not Path(ctx.voice.segments[0].file_path).exists():
            missing.append("voice")

    if ctx.visual:
        if any(
            not Path(a.file_path).exists()
            for a in ctx.visual.assets
            if a.file_path
        ):
            missing.append("visual")

    if ctx.subtitle and ctx.subtitle.file_path:
        if not Path(ctx.subtitle.file_path).exists():
            missing.append("subtitle")

    if ctx.thumbnail and ctx.thumbnail.file_path:
        if not Path(ctx.thumbnail.file_path).exists():
            missing.append("thumbnail")

    if ctx.assembly and ctx.assembly.file_path:
        if not Path(ctx.assembly.file_path).exists():
            missing.append("assembly")

    if ctx.template_video_path:
        if not Path(ctx.template_video_path).exists():
            missing.append("template_video")

    return missing


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def sync_script_durations(script, voice):  # noqa: ANN001, ANN201
    """Return a new Script with scene durations from actual voice measurements.

    After voice generation, actual audio lengths differ from the LLM's
    original estimates.  This syncs the script so that storyboard / JSON
    written later reflect reality.
    """
    duration_map = {
        seg.scene_number: seg.duration_seconds for seg in voice.segments
    }

    new_scenes = []
    for scene in script.scenes:
        actual = duration_map.get(scene.scene_number)
        if actual is not None:
            new_scenes.append(
                scene.model_copy(update={"duration_seconds": round(actual)})
            )
        else:
            new_scenes.append(scene)

    total = sum(s.duration_seconds for s in new_scenes)
    return script.model_copy(
        update={"scenes": tuple(new_scenes), "total_duration_seconds": total},
    )


def save_script_files(script, run_dir: Path) -> None:  # noqa: ANN001
    """Save script JSON and human-readable storyboard to run_dir."""
    if script is None:
        return

    script_path = run_dir / "script.json"
    script_path.write_text(
        _json.dumps(
            script.model_dump(mode="json"), ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    lines = [f"# {script.video_title}", f"{script.description}", ""]
    cursor = 0.0
    for scene in script.scenes:
        start_mm = int(cursor // 60)
        start_ss = int(cursor % 60)
        end_val = cursor + scene.duration_seconds
        end_mm = int(end_val // 60)
        end_ss = int(end_val % 60)
        time_range = f"{start_mm:02d}:{start_ss:02d}-{end_mm:02d}:{end_ss:02d}"
        lines.append(f"## 場景 {scene.scene_number}: {scene.title}")
        lines.append(
            f"時長: {scene.duration_seconds}s ({time_range}) | "
            f"轉場: {scene.transition}",
        )
        cursor = end_val
        lines.append("")
        lines.append("### 旁白")
        lines.append(scene.narration)
        lines.append("")
        lines.append("### 畫面提示")
        hint = scene.visual_hint
        lines.append(f"描述: {hint.description}")
        if hint.keywords:
            lines.append(f"關鍵字: {', '.join(hint.keywords)}")
        lines.append(f"風格: {hint.style} | 來源: {hint.source_preference}")
        lines.append("")
    if script.sources:
        lines.append("## 參考來源")
        for src in script.sources:
            lines.append(f"- {src}")
        lines.append("")

    storyboard_path = run_dir / "storyboard.txt"
    storyboard_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Saved script.json + storyboard.txt to %s", run_dir)