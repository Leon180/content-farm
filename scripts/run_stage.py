"""CLI entry point for running individual pipeline stages.

Used by Claude Code skills to invoke Python stages one at a time.
State flows through files on disk (script.json, audio/*.mp3, etc.).

Usage:
    # Explicit path
    python scripts/run_stage.py --stage voice --run-dir output/20260312_topic/

    # Just a run name (output/ is prefixed)
    python scripts/run_stage.py --stage voice --run-dir 20260312_topic

    # Latest run with a script.json (no --run-dir at all)
    python scripts/run_stage.py --stage voice
    python scripts/run_stage.py --stage voice --run-dir latest
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from content_farm.config import Settings
from content_farm.pipeline.container import ServiceContainer
from content_farm.pipeline.context import PipelineContext
from content_farm.script_gen.schemas import Script
from content_farm.telegram.approval import ApprovalGate

logger = logging.getLogger(__name__)

STAGES = (
    "voice", "visual", "visual_timeline", "blank_visual", "subtitle",
    "thumbnail", "assembly", "assembly_timeline", "template", "drive",
    "prepareupload", "youtube",
)

OUTPUT_ROOT = Path("output")


def resolve_run_dir(run_dir_arg: str | Path | None) -> Path:
    """Turn the ``--run-dir`` argument into an absolute Path.

    Accepts:
      * ``None`` or ``"latest"`` → newest directory under ``output/`` that
        contains a ``script.json``
      * ``"20260312_topic"`` (no slash) → ``output/20260312_topic``
      * full or relative path → used as-is

    Raises ``FileNotFoundError`` if no candidate exists.
    """
    if (
        run_dir_arg is None
        or str(run_dir_arg).strip() == ""
        or str(run_dir_arg).lower() == "latest"
    ):
        latest = _find_latest_run_dir()
        if latest is None:
            raise FileNotFoundError(
                "No run directory found under output/ (need a script.json)"
            )
        logger.info("Using latest run: %s", latest)
        return latest

    p = Path(run_dir_arg)
    # Bare name like "20260312_topic" → look under output/
    if not p.is_absolute() and len(p.parts) == 1 and not p.exists():
        candidate = OUTPUT_ROOT / p
        if candidate.exists():
            return candidate
        raise FileNotFoundError(
            f"Run directory not found: {p} (also checked {candidate})"
        )

    if not p.exists():
        raise FileNotFoundError(f"Run directory not found: {p}")
    return p


def _find_latest_run_dir() -> Path | None:
    if not OUTPUT_ROOT.is_dir():
        return None
    candidates = [
        d for d in OUTPUT_ROOT.iterdir()
        if d.is_dir() and (d / "script.json").is_file()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda d: d.stat().st_mtime)


# ------------------------------------------------------------------
# Artifact reconstruction from disk
# ------------------------------------------------------------------


async def _rebuild_voice_artifact(run_dir: Path) -> "VoiceArtifact | None":
    """Reconstruct VoiceArtifact by scanning audio/*.mp3 files."""
    from content_farm.voice.schemas import AudioSegment, VoiceArtifact

    audio_dir = run_dir / "audio"
    if not audio_dir.is_dir():
        return None

    mp3s = sorted(audio_dir.glob("scene_*.mp3"))
    if not mp3s:
        return None

    # Try loading saved artifact first
    artifact_file = run_dir / "voice_artifact.json"
    if artifact_file.is_file():
        data = json.loads(artifact_file.read_text(encoding="utf-8"))
        return VoiceArtifact.model_validate(data)

    # Fallback: reconstruct from files using ffprobe
    segments = []
    for mp3 in mp3s:
        scene_num = int(mp3.stem.split("_")[1])
        duration = await _get_audio_duration(mp3)
        segments.append(AudioSegment(
            scene_number=scene_num,
            file_path=str(mp3),
            duration_seconds=round(duration, 2),
            character_count=0,
        ))

    total = sum(s.duration_seconds for s in segments)
    full_mp3 = audio_dir / "full.mp3"
    return VoiceArtifact(
        segments=tuple(segments),
        total_duration_seconds=total,
        output_dir=str(audio_dir),
        full_audio_path=str(full_mp3) if full_mp3.is_file() else "",
    )


async def _get_audio_duration(file_path: Path) -> float:
    """Get audio duration via ffprobe, with byte-size fallback."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", str(file_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            data = json.loads(stdout)
            return float(data["format"]["duration"])
    except (FileNotFoundError, KeyError, json.JSONDecodeError, ValueError):
        pass

    try:
        return round((file_path.stat().st_size * 8) / 128000, 2)
    except FileNotFoundError:
        return 0.0


def _rebuild_visual_artifact(run_dir: Path) -> "VisualArtifact | None":
    """Reconstruct VisualArtifact from visual/*.mp4 files or saved artifact."""
    from content_farm.visual.schemas import VisualArtifact, VisualAsset

    # Try saved artifact first
    artifact_file = run_dir / "visual_artifact.json"
    if artifact_file.is_file():
        data = json.loads(artifact_file.read_text(encoding="utf-8"))
        return VisualArtifact.model_validate(data)

    visual_dir = run_dir / "visual"
    if not visual_dir.is_dir():
        return None

    mp4s = sorted(visual_dir.glob("scene_[0-9][0-9][0-9].mp4"))
    if not mp4s:
        return None

    assets = []
    for mp4 in mp4s:
        scene_num = int(mp4.stem.split("_")[1])
        assets.append(VisualAsset(
            scene_number=scene_num,
            file_path=str(mp4),
            source="disk",
            duration_seconds=0.0,
            query_used="",
        ))

    return VisualArtifact(
        assets=tuple(assets),
        output_dir=str(visual_dir),
    )


def _rebuild_subtitle_artifact(run_dir: Path) -> "SubtitleArtifact | None":
    """Find existing subtitle file."""
    from content_farm.subtitle.schemas import SubtitleArtifact

    artifact_file = run_dir / "subtitle_artifact.json"
    if artifact_file.is_file():
        data = json.loads(artifact_file.read_text(encoding="utf-8"))
        return SubtitleArtifact.model_validate(data)

    sub_dir = run_dir / "subtitles"
    if not sub_dir.is_dir():
        return None

    srt_files = sorted(sub_dir.glob("*.srt")) + sorted(sub_dir.glob("*.vtt"))
    if not srt_files:
        return None

    return SubtitleArtifact(file_path=str(srt_files[0]))


def _rebuild_assembly_artifact(run_dir: Path) -> "AssemblyArtifact | None":
    """Find existing assembly output."""
    from content_farm.assembly.schemas import AssemblyArtifact

    artifact_file = run_dir / "assembly_artifact.json"
    if artifact_file.is_file():
        data = json.loads(artifact_file.read_text(encoding="utf-8"))
        return AssemblyArtifact.model_validate(data)

    assembly_dir = run_dir / "assembly"
    if not assembly_dir.is_dir():
        return None

    videos = sorted(assembly_dir.glob("*.mp4"))
    if not videos:
        return None

    return AssemblyArtifact(file_path=str(videos[0]))


def _save_artifact(run_dir: Path, stage: str, artifact: object) -> None:
    """Save artifact JSON for downstream stages."""
    if artifact is None or not hasattr(artifact, "model_dump"):
        return
    path = run_dir / f"{stage}_artifact.json"
    path.write_text(
        json.dumps(artifact.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Saved %s", path)


# ------------------------------------------------------------------
# Stage execution
# ------------------------------------------------------------------


async def run_stage(stage: str, run_dir: Path) -> None:
    """Load context from disk, run one stage, save artifact."""
    from content_farm.pipeline import stages

    settings = Settings()  # type: ignore[call-arg]
    container = ServiceContainer(settings)

    # Load script.json (required for all stages)
    script_path = run_dir / "script.json"
    if not script_path.is_file():
        print(f"Error: {script_path} not found", file=sys.stderr)
        sys.exit(1)

    script_data = json.loads(script_path.read_text(encoding="utf-8"))
    script = Script.model_validate(script_data)

    # Build context with no-op gate (skills are human-in-the-loop)
    gate = ApprovalGate(bot=None)
    ctx = PipelineContext(
        settings=settings,
        run_id=run_dir.name,
        run_dir=run_dir,
        gate=gate,
    )
    ctx.script = script

    # Reconstruct existing artifacts for stages that need them
    ctx.voice = await _rebuild_voice_artifact(run_dir)
    ctx.visual = _rebuild_visual_artifact(run_dir)
    ctx.subtitle = _rebuild_subtitle_artifact(run_dir)
    ctx.assembly = _rebuild_assembly_artifact(run_dir)

    try:
        if stage == "voice":
            await stages.run_voice_stage(ctx, container)
            _save_artifact(run_dir, "voice", ctx.voice)
            # Voice now also produces subtitles
            if ctx.subtitle is not None:
                _save_artifact(run_dir, "subtitle", ctx.subtitle)
            # Sync script durations with actual audio lengths
            if ctx.voice is not None:
                ctx.script = stages.sync_script_durations(ctx.script, ctx.voice)
                script_path.write_text(
                    json.dumps(
                        ctx.script.model_dump(mode="json"),
                        ensure_ascii=False, indent=2,
                    ),
                    encoding="utf-8",
                )
                logger.info("Updated script.json with actual audio durations")

        elif stage == "visual":
            await stages.run_visual_stage(ctx, container)
            _save_artifact(run_dir, "visual", ctx.visual)

        elif stage == "visual_timeline":
            await stages.run_visual_timeline_stage(ctx, container)
            _save_artifact(run_dir, "visual", ctx.visual)

        elif stage == "concatscene":
            await stages.run_concat_scene_stage(ctx, container)
            _save_artifact(run_dir, "visual", ctx.visual)

        elif stage == "blank_visual":
            await stages.run_blank_visual_stage(ctx, container)
            _save_artifact(run_dir, "visual", ctx.visual)

        elif stage == "subtitle":
            if ctx.voice is None:
                print("Error: voice artifacts required for subtitle", file=sys.stderr)
                sys.exit(1)
            await stages.run_subtitle_stage(ctx, container)
            _save_artifact(run_dir, "subtitle", ctx.subtitle)

        elif stage == "thumbnail":
            await stages.run_thumbnail_stage(ctx, container)
            _save_artifact(run_dir, "thumbnail", ctx.thumbnail)

        elif stage == "assembly":
            if ctx.voice is None or ctx.visual is None:
                print(
                    "Error: voice + visual artifacts required for assembly",
                    file=sys.stderr,
                )
                sys.exit(1)
            await stages.run_assembly_stage(ctx, container)
            _save_artifact(run_dir, "assembly", ctx.assembly)

        elif stage == "assembly_timeline":
            if ctx.voice is None:
                print(
                    "Error: voice artifacts required for timeline assembly",
                    file=sys.stderr,
                )
                sys.exit(1)
            await stages.run_timeline_assembly_stage(ctx, container)
            _save_artifact(run_dir, "assembly", ctx.assembly)

        elif stage == "template":
            if ctx.voice is None or ctx.visual is None:
                print(
                    "Error: voice + visual artifacts required for template",
                    file=sys.stderr,
                )
                sys.exit(1)
            await stages.run_template_video_stage(ctx, container)
            print(f"Template video: {ctx.template_video_path}")

        elif stage == "drive":
            # Sync script durations before saving
            if ctx.voice is not None:
                ctx.script = stages.sync_script_durations(ctx.script, ctx.voice)
            await stages.run_drive_stage(ctx, container)
            print(f"Drive link: {ctx.drive_link}")

        elif stage == "prepareupload":
            from content_farm.assembly.ffmpeg import FFmpegComposer
            from content_farm.youtube.meta import (
                generate_meta_template, save_meta_template,
            )

            assembly = _rebuild_assembly_artifact(run_dir)
            if assembly is None or not Path(assembly.file_path).exists():
                print(
                    "Error: assembly video not found. Run assembly first.",
                    file=sys.stderr,
                )
                sys.exit(1)

            source_path = Path(assembly.file_path)
            upload_dir = run_dir / "upload"
            upload_dir.mkdir(parents=True, exist_ok=True)

            composer = FFmpegComposer(ffmpeg_path=settings.ffmpeg_path)

            # Respect the script's declared orientation: long-form landscape
            # videos must stay landscape, short-form stays/becomes portrait.
            from content_farm.types import Orientation as _Orientation

            declared_orientation = (
                getattr(ctx.script, "orientation", None) or _Orientation.PORTRAIT
            )
            src_w, src_h = await composer.probe_dimensions(source_path)
            src_is_portrait = src_h > src_w

            if declared_orientation == _Orientation.LANDSCAPE:
                # Keep the landscape output as-is (no portrait conversion)
                final_path = upload_dir / f"{source_path.stem}_final.mp4"
                import shutil
                shutil.copy2(source_path, final_path)
            elif src_is_portrait:
                # Portrait source, portrait target — copy as-is
                final_path = upload_dir / f"{source_path.stem}_final.mp4"
                import shutil
                shutil.copy2(source_path, final_path)
            else:
                # Portrait target but source is landscape — convert
                final_path = upload_dir / f"{source_path.stem}_portrait.mp4"
                await composer.convert_to_portrait(
                    input_path=source_path,
                    output_path=final_path,
                    title="",
                    title_fontsize=87,
                )
            logger.info("Final video: %s", final_path)

            # Generate thumbnail
            from content_farm.thumbnail.schemas import ThumbnailInput

            thumb_gen = container.create_thumbnail_generator(
                run_dir / "thumbnails",
            )
            video_for_thumb = str(source_path)
            ctx.thumbnail = await thumb_gen.generate(
                ThumbnailInput(
                    script=ctx.script,
                    video_path=video_for_thumb,
                ),
            )
            logger.info("Thumbnail: %s", ctx.thumbnail.file_path)

            meta = generate_meta_template(ctx.script, run_dir, final_path)
            meta_path = save_meta_template(meta, run_dir)
            logger.info("Meta template: %s", meta_path)
            print(f"Final video: {final_path}")
            print(f"Thumbnail: {ctx.thumbnail.file_path}")
            print(f"Meta template: {meta_path}")
            print("Edit youtube_meta.json, then run /project:upload")

        elif stage == "youtube":
            from content_farm.youtube.meta import load_meta_template
            from content_farm.youtube.schemas import UploadInput, UploadSettings

            meta = load_meta_template(run_dir)

            video_path = run_dir / meta["video_path"]
            if not video_path.exists():
                print(f"Error: video not found: {video_path}", file=sys.stderr)
                sys.exit(1)

            thumbnail_path = None
            if meta.get("thumbnail_path"):
                tp = run_dir / meta["thumbnail_path"]
                if tp.exists():
                    thumbnail_path = str(tp)

            subtitle_path = None
            if meta.get("subtitle_path"):
                sp = run_dir / meta["subtitle_path"]
                if sp.exists():
                    subtitle_path = str(sp)

            upload_settings = UploadSettings(
                privacy_status=meta.get("privacy_status", "private"),
                category_id=meta.get("category_id", "22"),
                made_for_kids=meta.get("made_for_kids", False),
                default_language=meta.get("default_language", "zh-TW"),
                publish_at=meta.get("publish_at"),
                contains_synthetic_media=meta.get("contains_synthetic_media"),
            )

            # Multi-channel runs (scripts/produce.py) name the env var holding
            # that channel's refresh token; the OAuth client stays shared.
            token_env = (meta.get("credentials_env") or {}).get("refresh_token")
            if token_env:
                from dotenv import dotenv_values
                from pydantic import SecretStr

                token = os.environ.get(token_env) or dotenv_values(".env").get(token_env) or ""
                if not token:
                    print(f"Error: env var {token_env} (channel refresh token) is not set",
                          file=sys.stderr)
                    sys.exit(1)
                container = ServiceContainer(settings.model_copy(
                    update={"youtube_refresh_token": SecretStr(token)}))

            upload_script = ctx.script.model_copy(update={
                "video_title": meta["title"],
                "description": meta["description"],
            })

            gen = container.create_upload_generator(
                upload_settings=upload_settings,
            )
            upload_input = UploadInput(
                script=upload_script,
                video_path=str(video_path),
                thumbnail_path=thumbnail_path,
                subtitle_path=subtitle_path,
                tags=tuple(meta.get("tags", [])),
            )

            artifact = await gen.generate(upload_input)
            _save_artifact(run_dir, "upload", artifact)
            print(f"Uploaded: {artifact.url}")
            print(f"Video ID: {artifact.video_id}")
            print(f"Privacy: {artifact.privacy_status}")

        else:
            print(f"Unknown stage: {stage}", file=sys.stderr)
            sys.exit(1)

        print(f"Stage '{stage}' completed successfully.")

    finally:
        await container.close()


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a single pipeline stage given a run directory.",
    )
    parser.add_argument(
        "--stage", required=True, choices=STAGES,
        help="Stage to run",
    )
    parser.add_argument(
        "--run-dir", required=False, default=None, type=str,
        help="Path to run directory. Accepts: full path, bare name "
             "(prefixed with output/), 'latest', or omit entirely (uses "
             "newest run under output/ with a script.json).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    try:
        run_dir = resolve_run_dir(args.run_dir)
    except FileNotFoundError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        sys.exit(1)

    asyncio.run(run_stage(args.stage, run_dir))


if __name__ == "__main__":
    main()
