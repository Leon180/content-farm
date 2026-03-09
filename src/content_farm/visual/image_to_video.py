"""Convert a still image to a video clip with Ken Burns zoom effect."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Slow zoom from 100% to 110% over the clip duration — subtle but alive.
_ZOOMPAN_FILTER = (
    "zoompan=z='min(zoom+0.0005,1.1)':x='iw/2-(iw/zoom/2)'"
    ":y='ih/2-(ih/zoom/2)':d={fps}*{duration}:s={width}x{height}:fps={fps}"
)


async def image_to_video(
    image_path: Path,
    output_path: Path,
    *,
    duration: float,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    ffmpeg_path: str = "ffmpeg",
) -> Path:
    """Convert a still image to a video clip with a slow zoom (Ken Burns) effect.

    Returns the output video path.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    zoompan = _ZOOMPAN_FILTER.format(
        fps=fps, duration=duration, width=width, height=height,
    )

    args = [
        ffmpeg_path, "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-vf", zoompan,
        "-t", f"{duration:.2f}",
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-an",
        str(output_path),
    ]

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(
            f"image_to_video failed (rc={proc.returncode}): {stderr.decode()[-500:]}"
        )

    logger.info(
        "Image→video: %s → %s (%.1fs)",
        image_path.name, output_path.name, duration,
    )
    return output_path
