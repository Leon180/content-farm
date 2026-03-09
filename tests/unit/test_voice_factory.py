"""Tests for TTS provider factory."""

from __future__ import annotations

import pytest

from content_farm.config import Settings
from content_farm.voice.factory import create_tts_provider


@pytest.fixture
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CF_ELEVENLABS_API_KEY", "test-elevenlabs-key")
    monkeypatch.setenv("CF_FISH_AUDIO_API_KEY", "test-fish-key")


@pytest.mark.usefixtures("_env")
class TestCreateTTSProvider:
    def test_creates_elevenlabs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_TTS_PROVIDER", "elevenlabs")
        settings = Settings()  # type: ignore[call-arg]
        provider = create_tts_provider(settings)
        assert type(provider).__name__ == "ElevenLabsProvider"

    def test_creates_fish_audio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_TTS_PROVIDER", "fish_audio")
        settings = Settings()  # type: ignore[call-arg]
        provider = create_tts_provider(settings)
        assert type(provider).__name__ == "FishAudioProvider"

    def test_unknown_provider_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_TTS_PROVIDER", "unknown")
        settings = Settings()  # type: ignore[call-arg]
        with pytest.raises(ValueError, match="Unknown TTS provider"):
            create_tts_provider(settings)

    def test_elevenlabs_missing_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_TTS_PROVIDER", "elevenlabs")
        monkeypatch.setenv("CF_ELEVENLABS_API_KEY", "")
        settings = Settings()  # type: ignore[call-arg]
        with pytest.raises(ValueError, match="CF_ELEVENLABS_API_KEY"):
            create_tts_provider(settings)

    def test_fish_audio_missing_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_TTS_PROVIDER", "fish_audio")
        monkeypatch.setenv("CF_FISH_AUDIO_API_KEY", "")
        settings = Settings()  # type: ignore[call-arg]
        with pytest.raises(ValueError, match="CF_FISH_AUDIO_API_KEY"):
            create_tts_provider(settings)

    def test_default_provider_is_elevenlabs(self) -> None:
        settings = Settings()  # type: ignore[call-arg]
        assert settings.tts_provider == "elevenlabs"
