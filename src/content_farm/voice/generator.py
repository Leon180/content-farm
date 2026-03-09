"""Voice generation pipeline stage."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from content_farm.config import Settings
from content_farm.script_gen.schemas import Script
from content_farm.voice.protocol import TTSProvider
from content_farm.voice.schemas import AudioSegment, VoiceArtifact

logger = logging.getLogger(__name__)


async def _get_audio_duration(file_path: Path) -> float:
    """Get actual audio duration using ffprobe. Falls back to byte estimation."""
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

    # Fallback: estimate from file size (MP3 ~128kbps)
    try:
        byte_count = file_path.stat().st_size
    except FileNotFoundError:
        return 0.0
    return round((byte_count * 8) / 128000, 2)


class VoiceGenerator:
    """Generates audio narration for each scene in a script.

    Accepts any TTSProvider implementation (ElevenLabs, Fish Audio, etc.).
    """

    def __init__(
        self,
        tts: TTSProvider,
        settings: Settings,
        output_dir: Path | None = None,
    ) -> None:
        self._tts = tts
        self._settings = settings
        self._output_dir = output_dir or Path("output/audio")
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_scenes)

    async def generate(self, script: Script) -> VoiceArtifact:
        """Generate audio for all scenes in the script."""
        narrations = [scene.narration for scene in script.scenes]
        tasks = []

        for i, scene in enumerate(script.scenes):
            previous_text = narrations[i - 1] if i > 0 else None
            next_text = narrations[i + 1] if i < len(narrations) - 1 else None

            tasks.append(
                self._generate_scene_audio(
                    scene_number=scene.scene_number,
                    narration=scene.narration,
                    previous_text=previous_text,
                    next_text=next_text,
                )
            )

        segments = await asyncio.gather(*tasks)

        total_duration = sum(s.duration_seconds for s in segments)
        total_chars = sum(s.character_count for s in segments)

        return VoiceArtifact(
            segments=tuple(segments),
            total_duration_seconds=total_duration,
            total_characters=total_chars,
            output_dir=str(self._output_dir),
        )

    async def _generate_scene_audio(
        self,
        *,
        scene_number: int,
        narration: str,
        previous_text: str | None,
        next_text: str | None,
    ) -> AudioSegment:
        """Generate audio for a single scene with continuity context."""
        async with self._semaphore:
            output_path = self._output_dir / f"scene_{scene_number:03d}.mp3"

            # Skip API call if file already exists (I-1: file-exists guard)
            if output_path.exists() and output_path.stat().st_size > 0:
                logger.info("Reusing existing audio: %s", output_path)
                duration = await _get_audio_duration(output_path)
                return AudioSegment(
                    scene_number=scene_number,
                    file_path=str(output_path),
                    duration_seconds=round(duration, 2),
                    character_count=len(narration),
                )

            await self._tts.generate_speech_with_context(
                text=narration,
                output_path=output_path,
                previous_text=previous_text,
                next_text=next_text,
            )

            # Use ffprobe for accurate duration (C-2)
            duration = await _get_audio_duration(output_path)

            return AudioSegment(
                scene_number=scene_number,
                file_path=str(output_path),
                duration_seconds=round(duration, 2),
                character_count=len(narration),
            )
