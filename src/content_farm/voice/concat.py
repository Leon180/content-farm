"""Concatenate per-scene MP3 files into a single full audio track."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


async def concat_audio_files(
    segment_paths: list[Path],
    output_path: Path,
    ffmpeg_path: str = "ffmpeg",
) -> Path:
    """Concatenate MP3 files using FFmpeg concat demuxer.

    All inputs must share the same codec (MP3 from same TTS engine).
    """
    if not segment_paths:
        msg = "No audio segments to concatenate"
        raise ValueError(msg)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False
    ) as f:
        for p in segment_paths:
            f.write(f"file '{p.resolve()}'\n")
        concat_list = f.name

    proc = await asyncio.create_subprocess_exec(
        ffmpeg_path, "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_list,
        "-c", "copy",
        str(output_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    Path(concat_list).unlink(missing_ok=True)

    if proc.returncode != 0:
        logger.error("FFmpeg concat failed: %s", stderr.decode())
        msg = f"FFmpeg concat failed with code {proc.returncode}"
        raise RuntimeError(msg)

    logger.info("Concatenated %d files -> %s", len(segment_paths), output_path)
    return output_path
