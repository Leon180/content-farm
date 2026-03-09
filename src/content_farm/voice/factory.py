"""Factory for creating TTS providers from configuration."""

from __future__ import annotations

from content_farm.config import Settings
from content_farm.voice.protocol import TTSProvider


def create_tts_provider(settings: Settings) -> TTSProvider:
    """Create the appropriate TTS provider based on settings."""
    provider = settings.tts_provider

    if provider == "elevenlabs":
        from content_farm.voice.elevenlabs import ElevenLabsProvider

        api_key = settings.elevenlabs_api_key.get_secret_value()
        if not api_key:
            raise ValueError("CF_ELEVENLABS_API_KEY is required for ElevenLabs provider")
        return ElevenLabsProvider(
            api_key=api_key,
            voice_id=settings.elevenlabs_voice_id,
            model_id=settings.elevenlabs_model_id,
        )

    if provider == "fish_audio":
        from content_farm.voice.fish_audio import FishAudioProvider

        api_key = settings.fish_audio_api_key.get_secret_value()
        if not api_key:
            raise ValueError("CF_FISH_AUDIO_API_KEY is required for Fish Audio provider")
        return FishAudioProvider(
            api_key=api_key,
            reference_id=settings.fish_audio_reference_id,
        )

    raise ValueError(f"Unknown TTS provider: {provider!r}. Use 'elevenlabs' or 'fish_audio'.")
