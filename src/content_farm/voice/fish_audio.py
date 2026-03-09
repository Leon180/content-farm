"""Fish Audio TTS provider."""

from __future__ import annotations

import logging
from pathlib import Path

from fish_audio_sdk import Session, TTSRequest

logger = logging.getLogger(__name__)


class FishAudioProvider:
    """Async wrapper around Fish Audio text-to-speech API.

    Fish Audio excels at Chinese narration with natural prosody.
    """

    def __init__(
        self,
        api_key: str,
        reference_id: str = "",
    ) -> None:
        self._session = Session(apikey=api_key)
        self._reference_id = reference_id or None

    async def generate_speech(
        self,
        text: str,
        *,
        output_path: Path,
        voice_id: str | None = None,
    ) -> int:
        """Generate speech and save to file. Returns bytes written."""
        ref_id = voice_id or self._reference_id
        kwargs: dict[str, object] = {"text": text}
        if ref_id:
            kwargs["reference_id"] = ref_id

        request = TTSRequest(**kwargs)
        chunks: list[bytes] = []
        for chunk in self._session.tts(request):
            chunks.append(chunk)
        audio = b"".join(chunks)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio)

        byte_count = len(audio)
        logger.info("Fish Audio TTS: %d bytes, %d chars -> %s", byte_count, len(text), output_path)
        return byte_count

    async def generate_speech_with_context(
        self,
        text: str,
        *,
        output_path: Path,
        previous_text: str | None = None,
        next_text: str | None = None,
        voice_id: str | None = None,
    ) -> int:
        """Generate speech — Fish Audio handles continuity internally."""
        return await self.generate_speech(
            text,
            output_path=output_path,
            voice_id=voice_id,
        )
