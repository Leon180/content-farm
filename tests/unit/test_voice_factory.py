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

    def test_default_provider_is_fish_audio(self) -> None:
        settings = Settings()  # type: ignore[call-arg]
        assert settings.tts_provider == "fish_audio"


@pytest.mark.usefixtures("_env")
class TestFishAudioModel:
    """CF_FISH_AUDIO_MODEL picks the Fish TTS model (sent as the ``model`` header)."""

    @staticmethod
    def _sent_backend(monkeypatch: pytest.MonkeyPatch, tmp_path) -> str:
        monkeypatch.setenv("CF_TTS_PROVIDER", "fish_audio")
        provider = create_tts_provider(Settings(_env_file=None))  # type: ignore[call-arg]
        sent: dict[str, str] = {}

        def fake_tts(request, backend="speech-1.5"):
            sent["backend"] = backend
            yield b"audio"

        monkeypatch.setattr(provider._session, "tts", fake_tts)
        import asyncio

        asyncio.run(provider.generate_speech("你好", output_path=tmp_path / "a.mp3"))
        return sent["backend"]

    def test_default_model_is_s2_1_pro(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        monkeypatch.delenv("CF_FISH_AUDIO_MODEL", raising=False)
        assert self._sent_backend(monkeypatch, tmp_path) == "s2.1-pro"

    def test_env_overrides_the_model(self, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
        monkeypatch.setenv("CF_FISH_AUDIO_MODEL", "speech-1.5")
        assert self._sent_backend(monkeypatch, tmp_path) == "speech-1.5"

    def test_empty_model_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_TTS_PROVIDER", "fish_audio")
        monkeypatch.setenv("CF_FISH_AUDIO_MODEL", "")
        with pytest.raises(ValueError, match="CF_FISH_AUDIO_MODEL"):
            create_tts_provider(Settings(_env_file=None))  # type: ignore[call-arg]
