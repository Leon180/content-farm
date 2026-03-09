"""Video assembly pipeline stage."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from content_farm.assembly.protocol import VideoComposer
from content_farm.assembly.schemas import (
    AssemblyArtifact,
    AssemblyInput,
    AssemblySettings,
    ComposedScene,
)
from content_farm.config import Settings
from content_farm.visual.schemas import VisualAsset
from content_farm.voice.schemas import AudioSegment

logger = logging.getLogger(__name__)


class VideoAssembler:
    """Assembles final video from voice + visual artifacts.

    Accepts any VideoComposer implementation (FFmpeg, etc.).
    """

    def __init__(
        self,
        composer: VideoComposer,
        settings: Settings,
        render_settings: AssemblySettings | None = None,
        output_dir: Path | None = None,
    ) -> None:
        self._composer = composer
        self._settings = settings
        self._render = render_settings or AssemblySettings()
        self._output_dir = output_dir or Path("output/assembly")
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_scenes)

    async def generate(self, assembly_input: AssemblyInput) -> AssemblyArtifact:
        """Assemble the final video from voice + visual artifacts."""
        self._output_dir.mkdir(parents=True, exist_ok=True)

        # Phase 1: Compose each scene concurrently
        tasks = []
        for scene in assembly_input.script.scenes:
            audio_seg = _find_segment(assembly_input, scene.scene_number)
            visual_asset = _find_asset(assembly_input, scene.scene_number)

            tasks.append(
                self._compose_single_scene(
                    scene_number=scene.scene_number,
                    video_path=Path(visual_asset.file_path) if visual_asset.file_path else None,
                    audio_path=Path(audio_seg.file_path),
                    target_duration=audio_seg.duration_seconds,
                )
            )

        composed = await asyncio.gather(*tasks)

        # Phase 2: Concatenate all scenes
        transitions = tuple(
            s.transition for s in assembly_input.script.scenes[:-1]
        )
        concat_path = self._output_dir / "concatenated.mp4"
        await self._composer.concatenate(
            scene_paths=tuple(Path(cs.file_path) for cs in composed),
            output_path=concat_path,
            transitions=transitions,
        )

        # Phase 3: Final render
        title = _safe_filename(assembly_input.script.video_title)
        final_path = self._output_dir / f"{title}.mp4"
        await self._composer.final_render(
            video_path=concat_path,
            output_path=final_path,
            background_music_path=(
                Path(assembly_input.background_music_path)
                if assembly_input.background_music_path
                else None
            ),
            music_volume=self._render.background_music_volume,
            subtitle_path=(
                Path(assembly_input.subtitle_path)
                if assembly_input.subtitle_path
                else None
            ),
        )

        total_duration = sum(cs.duration_seconds for cs in composed)
        file_size = final_path.stat().st_size if final_path.exists() else 0

        return AssemblyArtifact(
            file_path=str(final_path),
            scenes=tuple(composed),
            total_duration_seconds=total_duration,
            file_size_bytes=file_size,
            output_dir=str(self._output_dir),
            resolution=f"{self._render.width}x{self._render.height}",
            fps=self._render.fps,
        )

    async def _compose_single_scene(
        self,
        *,
        scene_number: int,
        video_path: Path | None,
        audio_path: Path,
        target_duration: float,
    ) -> ComposedScene:
        """Compose a single scene with concurrency control."""
        async with self._semaphore:
            output_path = self._output_dir / f"scene_{scene_number:03d}_composed.mp4"

            # Use placeholder black video if no visual asset
            effective_video = video_path or output_path.with_suffix(".placeholder.mp4")
            if video_path is None:
                logger.warning("Scene %d: no visual asset, using black placeholder", scene_number)

            await self._composer.compose_scene(
                video_path=effective_video,
                audio_path=audio_path,
                output_path=output_path,
                target_duration=target_duration,
            )

            return ComposedScene(
                scene_number=scene_number,
                file_path=str(output_path),
                duration_seconds=target_duration,
                video_source=str(video_path or ""),
                audio_source=str(audio_path),
            )


class AssemblyStage:
    """PipelineStage adapter for VideoAssembler."""

    def __init__(self, assembler: VideoAssembler) -> None:
        self._assembler = assembler

    @property
    def name(self) -> str:
        return "video_assembly"

    async def validate_input(self, input_data: AssemblyInput) -> None:
        if not isinstance(input_data, AssemblyInput):
            raise TypeError(f"Expected AssemblyInput, got {type(input_data)}")
        if not input_data.voice.segments:
            raise ValueError("VoiceArtifact has no segments")
        if not input_data.visual.assets:
            raise ValueError("VisualArtifact has no assets")

        voice_scenes = {s.scene_number for s in input_data.voice.segments}
        visual_scenes = {a.scene_number for a in input_data.visual.assets}
        script_scenes = {s.scene_number for s in input_data.script.scenes}

        if voice_scenes != script_scenes:
            raise ValueError(
                f"Voice/script scene mismatch: {voice_scenes} vs {script_scenes}"
            )
        if visual_scenes != script_scenes:
            raise ValueError(
                f"Visual/script scene mismatch: {visual_scenes} vs {script_scenes}"
            )

    async def execute(self, input_data: AssemblyInput) -> AssemblyArtifact:
        return await self._assembler.generate(input_data)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _find_segment(inp: AssemblyInput, scene_number: int) -> AudioSegment:
    """Find the audio segment matching a scene number."""
    for seg in inp.voice.segments:
        if seg.scene_number == scene_number:
            return seg
    raise ValueError(f"No audio segment for scene {scene_number}")


def _find_asset(inp: AssemblyInput, scene_number: int) -> VisualAsset:
    """Find the visual asset matching a scene number."""
    for asset in inp.visual.assets:
        if asset.scene_number == scene_number:
            return asset
    raise ValueError(f"No visual asset for scene {scene_number}")


def _safe_filename(title: str) -> str:
    """Convert a title to a filesystem-safe filename."""
    safe = re.sub(r"[^\w\s-]", "", title)
    return re.sub(r"\s+", "_", safe).strip("_")[:100] or "untitled"
