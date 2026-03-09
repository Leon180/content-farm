"""Append source credits as subtitle-only end card to a template video."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from content_farm.subtitle.srt import format_timestamp

logger = logging.getLogger(__name__)

# How long each source line is displayed
_SECONDS_PER_SOURCE = 3.0
# Header display time
_HEADER_SECONDS = 2.0
# Trailing padding
_TAIL_SECONDS = 1.0


def build_source_srt(sources: tuple[str, ...]) -> str:
    """Build SRT content for source credits."""
    blocks: list[str] = []
    t = 0.0
    idx = 1

    # Header
    blocks.append(
        f"{idx}\n"
        f"{format_timestamp(t)} --> {format_timestamp(t + _HEADER_SECONDS)}\n"
        f"【參考來源】\n"
    )
    t += _HEADER_SECONDS
    idx += 1

    for src in sources:
        end = t + _SECONDS_PER_SOURCE
        blocks.append(
            f"{idx}\n"
            f"{format_timestamp(t)} --> {format_timestamp(end)}\n"
            f"{src}\n"
        )
        t = end
        idx += 1

    return "\n".join(blocks)


def sources_duration(sources: tuple[str, ...]) -> float:
    """Calculate total duration needed for source display."""
    if not sources:
        return 0.0
    return _HEADER_SECONDS + len(sources) * _SECONDS_PER_SOURCE + _TAIL_SECONDS


async def append_sources_to_video(
    video_path: Path,
    sources: tuple[str, ...],
    output_dir: Path,
    *,
    width: int = 1080,
    height: int = 1920,
    ffmpeg_path: str = "ffmpeg",
) -> Path:
    """Append source credits as subtitle-only segment at the end of a video.

    1. Creates a source SRT file
    2. Creates a black+silent extension clip with sources burned in
    3. Concatenates original video + extension
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    srt_content = build_source_srt(sources)
    srt_path = output_dir / "sources.srt"
    srt_path.write_text(srt_content, encoding="utf-8")

    duration = sources_duration(sources)

    # Step 1: Create extension clip (black + silence + source subtitles)
    ext_path = output_dir / "sources_extension.mp4"
    srt_escaped = (
        str(srt_path)
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
    )
    await _run_ffmpeg(
        ffmpeg_path,
        "-y",
        "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:d={duration}:r=30",
        "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", str(duration),
        "-vf", f"subtitles={srt_escaped}:force_style='FontSize=20,Alignment=2,MarginV=80'",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        str(ext_path),
    )

    # Step 2: Concatenate original + extension
    concat_list = output_dir / "concat_list.txt"
    concat_list.write_text(
        f"file '{video_path}'\nfile '{ext_path}'\n",
        encoding="utf-8",
    )

    final_path = video_path.with_name(video_path.stem + "_with_sources.mp4")
    await _run_ffmpeg(
        ffmpeg_path,
        "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c", "copy",
        str(final_path),
    )

    logger.info("Sources appended: %s (%.1fs extra)", final_path.name, duration)
    return final_path


async def _run_ffmpeg(*cmd: str) -> None:
    """Run an ffmpeg command and raise on failure."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed: {stderr.decode()[:500]}"
        )
