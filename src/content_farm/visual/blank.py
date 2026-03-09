"""Blank visual generator — black-screen video clips for template assembly."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from content_farm.script_gen.schemas import Script
from content_farm.visual.schemas import VisualArtifact, VisualAsset

logger = logging.getLogger(__name__)


async def generate_blank_visuals(
    script: Script,
    output_dir: Path,
    *,
    width: int = 1080,
    height: int = 1920,
    ffmpeg_path: str = "ffmpeg",
) -> VisualArtifact:
    """Generate black-screen video clips for each scene.

    Used in materials-only mode: produces blank background clips
    that get combined with voice + subtitles into a template video.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    assets = []
    for scene in script.scenes:
        output_path = output_dir / f"scene_{scene.scene_number:03d}.mp4"
        duration = scene.duration_seconds

        if output_path.exists() and output_path.stat().st_size > 0:
            logger.info("Reusing existing blank: %s", output_path.name)
        else:
            await _create_black_clip(
                output_path, duration, width, height, ffmpeg_path,
            )

        assets.append(VisualAsset(
            scene_number=scene.scene_number,
            file_path=str(output_path),
            source="blank",
            duration_seconds=float(duration),
            query_used="",
            format="mp4",
        ))

    total_duration = sum(a.duration_seconds for a in assets)
    return VisualArtifact(
        assets=tuple(assets),
        total_duration_seconds=total_duration,
        output_dir=str(output_dir),
    )


async def _create_black_clip(
    output_path: Path,
    duration: int,
    width: int,
    height: int,
    ffmpeg_path: str,
) -> None:
    """Create a black-screen video clip with ffmpeg."""
    cmd = [
        ffmpeg_path,
        "-y",
        "-f", "lavfi",
        "-i", f"color=c=black:s={width}x{height}:d={duration}:r=30",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "stillimage",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed creating blank clip: {stderr.decode()[:500]}"
        )

    logger.info("Blank clip created: %s (%ds)", output_path.name, duration)
