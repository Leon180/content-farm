"""ElevenLabs TTS provider."""

from __future__ import annotations

import logging
from pathlib import Path

from elevenlabs.client import AsyncElevenLabs

logger = logging.getLogger(__name__)


async def _collect_audio_stream(stream: object) -> bytes:
    """Collect an AsyncIterator[bytes] into a single bytes object."""
    chunks: list[bytes] = []
    async for chunk in stream:  # type: ignore[union-attr]
        chunks.append(chunk)
    return b"".join(chunks)


class ElevenLabsProvider:
    """Async wrapper around ElevenLabs text-to-speech API.

    Supports previous_text/next_text for smooth scene transitions.
    """

    def __init__(
        self,
        api_key: str,
        voice_id: str = "JBFqnCBsd6RMkjVDRZzb",
        model_id: str = "eleven_v3",
    ) -> None:
        self._client = AsyncElevenLabs(api_key=api_key)
        self._voice_id = voice_id
        self._model_id = model_id

    async def generate_speech(
        self,
        text: str,
        *,
        output_path: Path,
        voice_id: str | None = None,
    ) -> int:
        """Generate speech and save to file. Returns bytes written."""
        stream = self._client.text_to_speech.convert(
            text=text,
            voice_id=voice_id or self._voice_id,
            model_id=self._model_id,
            output_format="mp3_44100_128",
        )
        audio = await _collect_audio_stream(stream)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio)

        byte_count = len(audio)
        logger.info("ElevenLabs TTS: %d bytes, %d chars -> %s", byte_count, len(text), output_path)
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
        """Generate speech with continuity context for natural transitions."""
        kwargs: dict[str, object] = {
            "text": text,
            "voice_id": voice_id or self._voice_id,
            "model_id": self._model_id,
            "output_format": "mp3_44100_128",
        }
        # previous_text/next_text only supported by older models, not eleven_v3
        supports_context = self._model_id not in ("eleven_v3",)
        if supports_context and previous_text is not None:
            kwargs["previous_text"] = previous_text[-1000:]
        if supports_context and next_text is not None:
            kwargs["next_text"] = next_text[:1000]

        stream = self._client.text_to_speech.convert(**kwargs)
        audio = await _collect_audio_stream(stream)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio)

        byte_count = len(audio)
        logger.info("ElevenLabs TTS (ctx): %d bytes -> %s", byte_count, output_path)
        return byte_count
