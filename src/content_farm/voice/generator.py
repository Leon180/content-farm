"""Voice generation pipeline stage."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path

from content_farm.config import Settings
from content_farm.script_gen.schemas import Script
from content_farm.voice.checked_synthesis import CheckedSynthesizer, record_check
from content_farm.voice.factory import LEGACY_MODEL, effective_tts_model, effective_voice_id
from content_farm.voice.pronunciation import load_table, merged_map
from content_farm.voice.protocol import TTSProvider
from content_farm.voice.schemas import AudioSegment, VoiceArtifact
from content_farm.voice.text_normalize import normalize_for_tts

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


IDENTITY_FILE = "voice_identity.json"


def _identity(provider: str, voice_id: str, tts_text: str, model: str = "") -> dict[str, str]:
    text_sha = hashlib.sha256(tts_text.encode("utf-8")).hexdigest()[:16]
    identity = {"provider": provider, "voice_id": voice_id, "text_sha": text_sha}
    return {**identity, "model": model} if model else identity


def _with_legacy_model(record: object) -> object:
    """Records written before the model was tracked name no model: they used the old default."""
    if not isinstance(record, dict) or "model" in record:
        return record
    legacy = LEGACY_MODEL.get(str(record.get("provider")), "")
    return {**record, "model": legacy} if legacy else record


class VoiceGenerator:
    """Generates audio narration for each scene in a script.

    Accepts any TTSProvider implementation (ElevenLabs, Fish Audio, etc.).

    Existing scene audio is reused only when ``audio/voice_identity.json`` says it
    was made by the same provider, voice and TTS text; otherwise (voice changed,
    pronunciation fixed, or audio from before this record existed) it is redone.
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
        # A local model is one process doing one thing at a time: voice scenes in order, each
        # synthesized, read back and re-generated before the next (cleaner logs, same speed).
        local = getattr(tts, "worker", None) is not None
        self._semaphore = asyncio.Semaphore(1 if local else settings.max_concurrent_scenes)
        self._voice_id = effective_voice_id(settings)
        self._model = effective_tts_model(settings)
        self._table = (load_table(Path(settings.pronunciation_file), provider=settings.tts_provider,
                                  channel=settings.channel_code)
                       if settings.pronunciation_file else None)
        self._checker = (CheckedSynthesizer(tts, settings, self._table.key_terms if self._table else (),
                                            mapping=self._table.mapping if self._table else None)
                         if settings.speech_check else None)

    def _load_identities(self) -> dict[str, dict[str, str]]:
        path = self._output_dir / IDENTITY_FILE
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Ignoring unreadable %s; all scenes will be re-synthesized", path)
            return {}
        return data if isinstance(data, dict) else {}

    def _record_identity(self, filename: str, identity: dict[str, str]) -> None:
        # Written after every scene, so a run that dies midway keeps what it paid for.
        path = self._output_dir / IDENTITY_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        updated = {**self._load_identities(), filename: identity}
        path.write_text(json.dumps(updated, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    async def generate(self, script: Script) -> VoiceArtifact:
        """Generate audio for all scenes in the script; local models are unloaded at the end."""
        try:
            return await self._generate(script)
        finally:
            await self._close()

    async def _close(self) -> None:
        if self._checker is not None:
            await self._checker.aclose()
        close = getattr(self._tts, "aclose", None)
        if close is not None:
            await close()

    async def _generate(self, script: Script) -> VoiceArtifact:
        logger.info("TTS voice: provider=%s model=%s voice_id=%s (%s)", self._settings.tts_provider,
                    self._model or "-", self._voice_id or "(provider default)",
                    "CF_TTS_VOICE_ID" if self._settings.tts_voice_id else "provider default setting")
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
                    pronunciation_map=script.pronunciation_map,
                )
            )

        segments = await asyncio.gather(*tasks)
        sorted_segments = sorted(segments, key=lambda s: s.scene_number)

        total_duration = sum(s.duration_seconds for s in sorted_segments)
        total_chars = sum(s.character_count for s in sorted_segments)

        full_path = await self._concat_full_audio(sorted_segments)
        await self._generate_subtitles(script, sorted_segments)

        return VoiceArtifact(
            segments=tuple(sorted_segments),
            total_duration_seconds=total_duration,
            total_characters=total_chars,
            output_dir=str(self._output_dir),
            full_audio_path=str(full_path),
        )

    async def _concat_full_audio(
        self, segments: list[AudioSegment],
    ) -> Path:
        """Concat scene MP3s into audio/full.mp3."""
        from content_farm.voice.concat import concat_audio_files

        paths = [Path(s.file_path) for s in segments]
        output = self._output_dir / "full.mp3"
        return await concat_audio_files(paths, output)

    async def _generate_subtitles(
        self, script: Script, segments: list[AudioSegment],
    ) -> Path:
        """Run subtitle generation and write SRT alongside audio."""
        from content_farm.subtitle.factory import create_subtitle_provider
        from content_farm.subtitle.generator import SubtitleGenerator
        from content_farm.subtitle.schemas import SubtitleInput

        sub_dir = self._output_dir.parent / "subtitles"
        sub_dir.mkdir(parents=True, exist_ok=True)

        voice_artifact = VoiceArtifact(
            segments=tuple(segments),
            total_duration_seconds=sum(s.duration_seconds for s in segments),
            output_dir=str(self._output_dir),
        )
        provider = create_subtitle_provider(
            self._settings, getattr(script, "orientation", None),
        )
        gen = SubtitleGenerator(provider, self._settings, output_dir=sub_dir)
        sub_input = SubtitleInput(script=script, voice=voice_artifact)
        await gen.generate(sub_input)
        logger.info("Generated subtitles at %s", sub_dir / "subtitles.srt")
        return sub_dir / "subtitles.srt"

    async def _generate_scene_audio(
        self,
        *,
        scene_number: int,
        narration: str,
        previous_text: str | None,
        next_text: str | None,
        pronunciation_map: dict[str, str] | None = None,
    ) -> AudioSegment:
        """Generate audio for a single scene with continuity context."""
        async with self._semaphore:
            output_path = self._output_dir / f"scene_{scene_number:03d}.mp3"

            tts_text = normalize_for_tts(narration, merged_map(self._table, pronunciation_map))
            identity = _identity(self._settings.tts_provider, self._voice_id, tts_text, self._model)
            exists = output_path.exists() and output_path.stat().st_size > 0

            # Skip the API call only for audio made by this voice from this text (I-1)
            if exists and _with_legacy_model(self._load_identities().get(output_path.name)) == identity:
                logger.info("Reusing existing audio: %s", output_path)
                duration = await _get_audio_duration(output_path)
                return AudioSegment(
                    scene_number=scene_number,
                    file_path=str(output_path),
                    duration_seconds=round(duration, 2),
                    character_count=len(narration),
                    tts_text=tts_text,
                )

            if exists:
                logger.info("Re-synthesizing %s: voice or text differs from the recorded audio",
                            output_path)
            voice_id = self._settings.tts_voice_id or None
            if self._checker is None:
                await self._tts.generate_speech_with_context(
                    text=tts_text, output_path=output_path, previous_text=previous_text,
                    next_text=next_text, voice_id=voice_id)
            else:
                check = await self._checker.synthesize(
                    narration=narration, tts_text=tts_text, output_path=output_path,
                    previous_text=previous_text, next_text=next_text, voice_id=voice_id)
                record_check(self._output_dir, output_path.name, {**check.to_json(), "tts_text": tts_text})
            self._record_identity(output_path.name, identity)

            # Use ffprobe for accurate duration (C-2)
            duration = await _get_audio_duration(output_path)

            return AudioSegment(
                scene_number=scene_number,
                file_path=str(output_path),
                duration_seconds=round(duration, 2),
                character_count=len(narration),
                tts_text=tts_text,
            )
