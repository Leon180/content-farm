"""TTS provider protocol — abstraction for multiple TTS backends."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class TTSProvider(Protocol):
    """Interface that all TTS providers must implement."""

    async def generate_speech(
        self,
        text: str,
        *,
        output_path: Path,
        voice_id: str | None = None,
    ) -> int:
        """Generate speech from text and save to file.

        Returns the number of bytes written.
        """
        ...

    async def generate_speech_with_context(
        self,
        text: str,
        *,
        output_path: Path,
        previous_text: str | None = None,
        next_text: str | None = None,
        voice_id: str | None = None,
    ) -> int:
        """Generate speech with optional continuity context.

        Providers that don't support context should ignore
        previous_text/next_text and fall back to generate_speech.
        Returns the number of bytes written.
        """
        ...
