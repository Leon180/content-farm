"""Tests for video composer factory."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from content_farm.assembly.factory import create_video_composer
from content_farm.config import Settings


@pytest.fixture
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")


@pytest.mark.usefixtures("_env")
class TestCreateVideoComposer:
    def test_creates_ffmpeg_composer(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            settings = Settings()  # type: ignore[call-arg]
            composer = create_video_composer(settings)
            assert type(composer).__name__ == "FFmpegComposer"

    def test_ffmpeg_not_found_raises(self) -> None:
        with patch("shutil.which", return_value=None):
            settings = Settings()  # type: ignore[call-arg]
            with pytest.raises(RuntimeError, match="FFmpeg binary not found"):
                create_video_composer(settings)

    def test_default_ffmpeg_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_FFMPEG_PATH", "ffmpeg")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.ffmpeg_path == "ffmpeg"

    def test_custom_ffmpeg_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_FFMPEG_PATH", "/opt/ffmpeg/bin/ffmpeg")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.ffmpeg_path == "/opt/ffmpeg/bin/ffmpeg"
