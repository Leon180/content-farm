"""Subtitle generation pipeline stage."""

from __future__ import annotations

import logging
from pathlib import Path

from content_farm.config import Settings
from content_farm.subtitle.protocol import SubtitleProvider
from content_farm.subtitle.schemas import (
    SubtitleArtifact,
    SubtitleInput,
    SubtitleSegment,
)
from content_farm.subtitle.srt import render_srt
from content_farm.voice.schemas import AudioSegment

logger = logging.getLogger(__name__)


class SubtitleGenerator:
    """Generates an SRT subtitle file for all scenes in a script."""

    def __init__(
        self,
        provider: SubtitleProvider,
        settings: Settings,
        output_dir: Path | None = None,
    ) -> None:
        self._provider = provider
        self._settings = settings
        self._output_dir = output_dir or Path("output/subtitles")

    async def generate(self, subtitle_input: SubtitleInput) -> SubtitleArtifact:
        """Generate a single SRT file covering the entire video."""
        self._output_dir.mkdir(parents=True, exist_ok=True)

        all_segments: list[SubtitleSegment] = []
        cumulative_offset = 0.0
        global_index = 1

        sorted_scenes = sorted(
            subtitle_input.script.scenes,
            key=lambda s: s.scene_number,
        )

        for scene in sorted_scenes:
            audio_seg = _find_audio_segment(subtitle_input, scene.scene_number)

            scene_segments = await self._provider.generate_segments(
                text=scene.narration,
                duration_seconds=audio_seg.duration_seconds,
                offset_seconds=cumulative_offset,
            )

            for seg in scene_segments:
                renumbered = SubtitleSegment(
                    index=global_index,
                    start_seconds=seg.start_seconds,
                    end_seconds=seg.end_seconds,
                    text=seg.text,
                    scene_number=scene.scene_number,
                )
                all_segments.append(renumbered)
                global_index += 1

            cumulative_offset += audio_seg.duration_seconds

        segments_tuple = tuple(all_segments)

        srt_content = render_srt(segments_tuple)
        srt_path = self._output_dir / "subtitles.srt"
        srt_path.write_text(srt_content, encoding="utf-8")

        logger.info(
            "Generated %d subtitle segments, total %.1fs",
            len(segments_tuple),
            cumulative_offset,
        )

        return SubtitleArtifact(
            file_path=str(srt_path),
            segments=segments_tuple,
            total_segments=len(segments_tuple),
            total_duration_seconds=cumulative_offset,
            language=subtitle_input.script.language,
            output_dir=str(self._output_dir),
        )


class SubtitleStage:
    """PipelineStage adapter for SubtitleGenerator."""

    def __init__(self, generator: SubtitleGenerator) -> None:
        self._generator = generator

    @property
    def name(self) -> str:
        return "subtitle_generation"

    async def validate_input(self, input_data: SubtitleInput) -> None:
        if not isinstance(input_data, SubtitleInput):
            msg = f"Expected SubtitleInput, got {type(input_data)}"
            raise TypeError(msg)
        if not input_data.voice.segments:
            raise ValueError("VoiceArtifact has no segments")
        if not input_data.script.scenes:
            raise ValueError("Script has no scenes")

        voice_scenes = {s.scene_number for s in input_data.voice.segments}
        script_scenes = {s.scene_number for s in input_data.script.scenes}
        if voice_scenes != script_scenes:
            raise ValueError(
                f"Voice/script scene mismatch: {voice_scenes} vs {script_scenes}"
            )

    async def execute(self, input_data: SubtitleInput) -> SubtitleArtifact:
        return await self._generator.generate(input_data)


def _find_audio_segment(inp: SubtitleInput, scene_number: int) -> AudioSegment:
    """Find the audio segment matching a scene number."""
    for seg in inp.voice.segments:
        if seg.scene_number == scene_number:
            return seg
    raise ValueError(f"No audio segment for scene {scene_number}")
