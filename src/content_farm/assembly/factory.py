"""Factory for creating video composers from configuration."""

from __future__ import annotations

import shutil

from content_farm.assembly.protocol import VideoComposer
from content_farm.assembly.schemas import AssemblySettings
from content_farm.config import Settings


def create_video_composer(
    settings: Settings,
    render_settings: AssemblySettings | None = None,
) -> VideoComposer:
    """Create the appropriate video composer based on settings."""
    from content_farm.assembly.ffmpeg import FFmpegComposer

    ffmpeg = settings.ffmpeg_path
    if not shutil.which(ffmpeg):
        raise RuntimeError(
            f"FFmpeg binary not found: {ffmpeg!r}. "
            "Install FFmpeg or set CF_FFMPEG_PATH."
        )

    return FFmpegComposer(
        render_settings=render_settings,
        ffmpeg_path=ffmpeg,
    )
