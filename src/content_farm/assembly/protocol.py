"""Video composition protocol — abstraction over FFmpeg or future backends."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class VideoComposer(Protocol):
    """Interface for composing video from audio + visual assets."""

    async def compose_scene(
        self,
        *,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
        target_duration: float,
    ) -> Path:
        """Combine one video clip + one audio clip into a single scene MP4.

        Trims or loops the video to match target_duration, overlays audio.
        Returns the output_path on success.
        """
        ...

    async def concatenate(
        self,
        *,
        scene_paths: tuple[Path, ...],
        output_path: Path,
        transitions: tuple[str, ...] = (),
    ) -> Path:
        """Concatenate composed scenes into a single video.

        Returns the output_path.
        """
        ...

    async def final_render(
        self,
        *,
        video_path: Path,
        output_path: Path,
        background_music_path: Path | None = None,
        music_volume: float = 0.15,
        subtitle_path: Path | None = None,
    ) -> Path:
        """Final render: mix background music, burn subtitles, ensure YouTube specs.

        Returns the output_path.
        """
        ...
