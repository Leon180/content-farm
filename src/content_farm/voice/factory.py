"""Factory for creating TTS providers from configuration."""

from __future__ import annotations

from pathlib import Path

from content_farm.config import Settings
from content_farm.voice.local_clone import CloneReference
from content_farm.voice.local_worker import GateConfig
from content_farm.voice.protocol import TTSProvider

# Local voice-cloning providers: the voice is the reference clip, not an id.
LOCAL_PROVIDERS = ("voxcpm2", "qwen3_tts")

_DEFAULT_VOICE = {
    "fish_audio": lambda s: s.fish_audio_reference_id,
    "elevenlabs": lambda s: s.elevenlabs_voice_id,
    "macos_say": lambda s: s.macos_say_voice,
}


def clone_reference(settings: Settings) -> CloneReference:
    if not settings.tts_ref_audio:
        raise ValueError(f"{settings.tts_provider} needs a reference clip: set voice.reference in the channel "
                         "yaml (CF_TTS_REF_AUDIO / CF_TTS_REF_TEXT)")
    return CloneReference(Path(settings.tts_ref_audio).expanduser(), settings.tts_ref_text)


def effective_voice_id(settings: Settings) -> str:
    """The voice the provider will actually use: the per-run override, else its default.
    Local cloning providers are identified by a hash of their reference clip + transcript."""
    if settings.tts_provider in LOCAL_PROVIDERS:
        return f"ref:{clone_reference(settings).fingerprint()}"
    default = _DEFAULT_VOICE.get(settings.tts_provider)
    return settings.tts_voice_id or (default(settings) if default else "")


# Model each provider used before its model became a setting: audio recorded without a
# ``model`` in voice_identity.json was made with this one.
LEGACY_MODEL = {"fish_audio": "speech-1.5"}

_MODEL = {
    "fish_audio": lambda s: s.fish_audio_model,
    "voxcpm2": lambda s: s.voxcpm2_model,
    "qwen3_tts": lambda s: s.qwen3_tts_model,
}


def effective_tts_model(settings: Settings) -> str:
    """The model that is part of a voice's identity ("" = not tracked for this provider)."""
    model = _MODEL.get(settings.tts_provider)
    return model(settings) if model else ""


def gate_config(settings: Settings) -> GateConfig:
    return GateConfig(settings.local_tts_busy_pattern, settings.local_tts_min_free_pct,
                      settings.local_tts_max_wait_s, settings.local_tts_lock_path)


def _local_provider(settings: Settings) -> TTSProvider:
    from content_farm.voice.qwen3_tts import Qwen3TTSProvider
    from content_farm.voice.voxcpm2 import VoxCPM2Provider

    if settings.tts_provider == "voxcpm2":
        cls, hub = VoxCPM2Provider, settings.voxcpm2_hub_dir
    else:
        cls, hub = Qwen3TTSProvider, settings.qwen3_tts_hub_dir
    return cls(python=settings.local_tts_python, hub_dir=hub, model=effective_tts_model(settings),
               reference=clone_reference(settings), gate=gate_config(settings),
               ffmpeg_path=settings.ffmpeg_path, seed=settings.tts_seed)


def create_tts_provider(settings: Settings) -> TTSProvider:
    """Create the appropriate TTS provider based on settings."""
    provider = settings.tts_provider

    if provider in LOCAL_PROVIDERS:
        return _local_provider(settings)

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
        f"Unknown TTS provider: {provider!r}. Use 'elevenlabs', 'fish_audio', 'voxcpm2', 'qwen3_tts' "
        "or 'macos_say'."
    )
