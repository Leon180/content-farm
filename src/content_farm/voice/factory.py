"""Factory for creating TTS providers from configuration."""

from __future__ import annotations

from content_farm.config import Settings
from content_farm.voice.protocol import TTSProvider


_DEFAULT_VOICE = {
    "fish_audio": lambda s: s.fish_audio_reference_id,
    "elevenlabs": lambda s: s.elevenlabs_voice_id,
    "macos_say": lambda s: s.macos_say_voice,
}


def effective_voice_id(settings: Settings) -> str:
    """The voice the provider will actually use: the per-run override, else its default."""
    default = _DEFAULT_VOICE.get(settings.tts_provider)
    return settings.tts_voice_id or (default(settings) if default else "")


# Model each provider used before its model became a setting: audio recorded without a
# ``model`` in voice_identity.json was made with this one.
LEGACY_MODEL = {"fish_audio": "speech-1.5"}


def effective_tts_model(settings: Settings) -> str:
    """The model that is part of a voice's identity ("" = not tracked for this provider)."""
    return settings.fish_audio_model if settings.tts_provider == "fish_audio" else ""


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
            model=settings.fish_audio_model,
        )

    if provider == "macos_say":
        # Free local TTS for development/testing only — never publish with it.
        from content_farm.voice.macos_say import MacSayProvider

        return MacSayProvider(
            voice=settings.macos_say_voice,
            rate=settings.macos_say_rate,
            ffmpeg_path=settings.ffmpeg_path,
        )

    raise ValueError(
        f"Unknown TTS provider: {provider!r}. Use 'elevenlabs', 'fish_audio' or 'macos_say'."
    )
