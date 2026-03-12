"""Timestamp parsing, timeline construction, and FFmpeg composition.

Handles user-provided clips named like ``00:00to00:03.mp4`` — parses
timestamps, fills gaps with black frames, and composes the final video.
"""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
from pathlib import Path

from content_farm.compose.schemas import ComposeResult, StagedClip, TimelineSegment

logger = logging.getLogger(__name__)

# Matches ``MM:SStoMM:SS.ext`` or ``H:MM:SStoH:MM:SS.ext``
_TIMESTAMP_RE = re.compile(
    r"(\d{1,2}:\d{2}(?::\d{2})?)to(\d{1,2}:\d{2}(?::\d{2})?)\.([a-zA-Z][a-zA-Z0-9]*)$"
)

_IMAGE_EXTS = frozenset({"jpg", "jpeg", "png", "webp"})
_VIDEO_EXTS = frozenset({"mp4", "mov", "avi", "mkv", "webm"})


# ------------------------------------------------------------------
# Parsing helpers
# ------------------------------------------------------------------


def parse_timestamp(ts: str) -> float:
    """Parse ``MM:SS`` or ``H:MM:SS`` into seconds."""
    parts = ts.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    raise ValueError(f"Invalid timestamp format: {ts}")


def parse_clip_filename(filename: str) -> tuple[float, float, str] | None:
    """Extract (start_secs, end_secs, extension) from a timestamped filename.

    Returns ``None`` if the filename doesn't match the expected pattern.
    """
    m = _TIMESTAMP_RE.search(filename)
    if not m:
        return None
    start = parse_timestamp(m.group(1))
    end = parse_timestamp(m.group(2))
    ext = m.group(3).lower()
    if end <= start:
        return None
    return start, end, ext


def classify_media(ext: str) -> str:
    """Classify a file extension as ``'video'`` or ``'image'``."""
    ext = ext.lower().lstrip(".")
    if ext in _VIDEO_EXTS:
        return "video"
    if ext in _IMAGE_EXTS:
        return "image"
    raise ValueError(f"Unsupported media extension: .{ext}")


# ------------------------------------------------------------------
# Timeline builder
# ------------------------------------------------------------------


def _check_overlaps(clips: tuple[StagedClip, ...]) -> str | None:
    """Return an error message if any clips overlap, else ``None``."""
    sorted_clips = sorted(clips, key=lambda c: c.start_seconds)
    for i in range(len(sorted_clips) - 1):
        a, b = sorted_clips[i], sorted_clips[i + 1]
        if a.end_seconds > b.start_seconds:
            return (
                f"時間重疊: {a.original_filename} "
                f"({a.start_seconds:.0f}-{a.end_seconds:.0f}s) 與 "
                f"{b.original_filename} "
                f"({b.start_seconds:.0f}-{b.end_seconds:.0f}s)"
            )
    return None


async def build_timeline(
    clips: tuple[StagedClip, ...],
    total_duration: float,
    work_dir: Path,
    *,
    ffmpeg_path: str = "ffmpeg",
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
) -> tuple[TimelineSegment, ...]:
    """Sort clips, validate no overlaps, preprocess, fill gaps.

    Returns an ordered tuple of ``TimelineSegment`` covering 0 → total_duration.
    """
    if not clips:
        raise ValueError("No clips to build timeline from")

    # Clean stale intermediate files from previous runs
    for stale in work_dir.glob("_clip_*"):
        stale.unlink(missing_ok=True)
    for stale in work_dir.glob("_gap_*"):
        stale.unlink(missing_ok=True)

    overlap_err = _check_overlaps(clips)
    if overlap_err:
        raise ValueError(overlap_err)

    sorted_clips = sorted(clips, key=lambda c: c.start_seconds)

    # Clamp clips that extend beyond total_duration
    clamped: list[StagedClip] = []
    for clip in sorted_clips:
        if clip.start_seconds >= total_duration:
            logger.warning(
                "Clip %s starts beyond total duration (%.1fs), skipping",
                clip.original_filename, total_duration,
            )
            continue
        if clip.end_seconds > total_duration:
            clip = StagedClip(
                file_path=clip.file_path,
                original_filename=clip.original_filename,
                start_seconds=clip.start_seconds,
                end_seconds=total_duration,
                media_type=clip.media_type,
            )
        clamped.append(clip)

    segments: list[TimelineSegment] = []
    cursor = 0.0

    for clip in clamped:
        # Fill gap before this clip
        if clip.start_seconds > cursor + 0.01:
            gap_path = await _make_placeholder(
                work_dir, cursor, clip.start_seconds,
                ffmpeg_path=ffmpeg_path, width=width, height=height, fps=fps,
            )
            segments.append(TimelineSegment(
                file_path=str(gap_path),
                start_seconds=cursor,
                end_seconds=clip.start_seconds,
                is_gap=True,
            ))

        # Preprocess the clip (normalize resolution, strip audio)
        clip_duration = clip.end_seconds - clip.start_seconds
        processed = await _preprocess_clip(
            clip, clip_duration, work_dir,
            ffmpeg_path=ffmpeg_path, width=width, height=height, fps=fps,
        )
        segments.append(TimelineSegment(
            file_path=str(processed),
            start_seconds=clip.start_seconds,
            end_seconds=clip.end_seconds,
        ))
        cursor = clip.end_seconds

    # Fill trailing gap
    if cursor < total_duration - 0.01:
        gap_path = await _make_placeholder(
            work_dir, cursor, total_duration,
            ffmpeg_path=ffmpeg_path, width=width, height=height, fps=fps,
        )
        segments.append(TimelineSegment(
            file_path=str(gap_path),
            start_seconds=cursor,
            end_seconds=total_duration,
            is_gap=True,
        ))

    return tuple(segments)


async def compose_timeline(
    segments: tuple[TimelineSegment, ...],
    voice_paths: tuple[Path, ...],
    output_path: Path,
    *,
    subtitle_path: Path | None = None,
    ffmpeg_path: str = "ffmpeg",
) -> ComposeResult:
    """Compose timeline segments + voice + optional subtitles into final video.

    Steps:
    1. Concatenate all video segments → silent timeline video
    2. Concatenate all voice files → full audio track
    3. Overlay audio + optional subtitles → final video
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir = output_path.parent

    # 1. Concat video segments
    video_concat = work_dir / "_timeline_video.mp4"
    await _concat_files(
        [Path(s.file_path) for s in segments],
        video_concat,
        ffmpeg_path=ffmpeg_path,
    )

    # 2. Concat voice files
    voice_concat = work_dir / "_voice_full.mp3"
    await _concat_files(list(voice_paths), voice_concat, ffmpeg_path=ffmpeg_path)

    # 3. Overlay voice onto video + optional subtitles
    await _overlay_voice(
        video_path=video_concat,
        voice_path=voice_concat,
        output_path=output_path,
        subtitle_path=subtitle_path,
        ffmpeg_path=ffmpeg_path,
    )

    # Compute stats
    total_duration = sum(s.duration for s in segments)
    clip_count = sum(1 for s in segments if not s.is_gap)
    gap_count = sum(1 for s in segments if s.is_gap)

    # Cleanup temp files
    for tmp in (video_concat, voice_concat):
        tmp.unlink(missing_ok=True)

    return ComposeResult(
        file_path=str(output_path),
        duration_seconds=total_duration,
        clip_count=clip_count,
        gap_count=gap_count,
    )


# ------------------------------------------------------------------
# FFmpeg helpers
# ------------------------------------------------------------------


async def _make_placeholder(
    work_dir: Path,
    start: float,
    end: float,
    *,
    ffmpeg_path: str,
    width: int,
    height: int,
    fps: int,
) -> Path:
    """Generate a black placeholder video for a gap."""
    duration = end - start
    out = work_dir / f"_gap_{start:.1f}_{end:.1f}.mp4"
    args = [
        ffmpeg_path, "-y",
        "-f", "lavfi", "-i",
        f"color=c=black:s={width}x{height}:r={fps}:d={duration:.2f}",
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
        "-t", f"{duration:.2f}",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        str(out),
    ]
    await _run_ffmpeg(args)
    return out


async def _preprocess_clip(
    clip: StagedClip,
    duration: float,
    work_dir: Path,
    *,
    ffmpeg_path: str,
    width: int,
    height: int,
    fps: int,
) -> Path:
    """Normalize a clip: scale/pad to target resolution, strip audio."""
    out = work_dir / f"_clip_{clip.start_seconds:.1f}_{clip.end_seconds:.1f}.mp4"

    if clip.media_type == "image":
        from content_farm.visual.image_to_video import image_to_video

        return await image_to_video(
            Path(clip.file_path), out,
            duration=duration,
            width=width, height=height, fps=fps,
            ffmpeg_path=ffmpeg_path,
        )

    vf = (
        f"scale={width}:{height}"
        ":force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"setsar=1,fps={fps}"
    )
    args = [
        ffmpeg_path, "-y",
        "-i", clip.file_path,
        "-vf", vf,
        "-t", f"{duration:.2f}",
        "-c:v", "libx264", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-an",
        str(out),
    ]
    await _run_ffmpeg(args)
    return out


async def _concat_files(
    paths: list[Path],
    output_path: Path,
    *,
    ffmpeg_path: str,
) -> Path:
    """Concatenate media files using the FFmpeg concat demuxer."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    try:
        for p in paths:
            tmp.write(f"file '{p.resolve()}'\n")
        tmp.flush()
        tmp.close()

        args = [
            ffmpeg_path, "-y",
            "-f", "concat", "-safe", "0",
            "-i", tmp.name,
            "-c", "copy",
            "-movflags", "+faststart",
            str(output_path),
        ]
        await _run_ffmpeg(args)
    finally:
        Path(tmp.name).unlink(missing_ok=True)

    return output_path


async def _overlay_voice(
    *,
    video_path: Path,
    voice_path: Path,
    output_path: Path,
    subtitle_path: Path | None = None,
    ffmpeg_path: str = "ffmpeg",
) -> Path:
    """Overlay voice audio onto silent video, optionally burning subtitles."""
    args = [ffmpeg_path, "-y", "-i", str(video_path), "-i", str(voice_path)]

    vf_file: Path | None = None
    if subtitle_path:
        from content_farm.assembly.drawtext import build_drawtext_filter

        drawtext_vf = build_drawtext_filter(subtitle_path)
        if drawtext_vf:
            vf_file = output_path.parent / f".vf_{output_path.stem}.txt"
            vf_file.write_text(drawtext_vf, encoding="utf-8")
            args.extend(["-filter_script:v", str(vf_file)])
            args.extend([
                "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            ])
        else:
            args.extend(["-c:v", "copy"])
    else:
        args.extend(["-c:v", "copy"])

    args.extend([
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ])
    try:
        await _run_ffmpeg(args)
    finally:
        if vf_file is not None:
            vf_file.unlink(missing_ok=True)
    return output_path


async def _run_ffmpeg(args: list[str]) -> None:
    """Run an FFmpeg command, raising on failure."""
    logger.debug("FFmpeg command: %s", " ".join(args))
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        detail = stderr.decode(errors="replace")[-500:]
        raise RuntimeError(
            f"FFmpeg failed (exit {proc.returncode}): {detail}"
        )
