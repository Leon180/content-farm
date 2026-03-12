"""Tests for visual provider factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from content_farm.config import Settings
from content_farm.visual.factory import create_image_provider, create_stock_provider


@pytest.fixture
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CF_PEXELS_API_KEY", "test-pexels-key")


@pytest.mark.usefixtures("_env")
class TestCreateStockProvider:
    def test_creates_pexels(self) -> None:
        settings = Settings()  # type: ignore[call-arg]
        provider = create_stock_provider(settings)
        assert type(provider).__name__ == "PexelsProvider"

    def test_no_keys_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_PEXELS_API_KEY", "")
        settings = Settings()  # type: ignore[call-arg]
        with pytest.raises(ValueError, match="(?i)at least one stock video API key"):
            create_stock_provider(settings)

    def test_both_keys_returns_multi(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_PIXABAY_API_KEY", "test-pixabay-key")
        settings = Settings()  # type: ignore[call-arg]
        provider = create_stock_provider(settings)
        assert type(provider).__name__ == "MultiStockProvider"

    def test_pixabay_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_PEXELS_API_KEY", "")
        monkeypatch.setenv("CF_PIXABAY_API_KEY", "test-pixabay-key")
        settings = Settings()  # type: ignore[call-arg]
        provider = create_stock_provider(settings)
        assert type(provider).__name__ == "PixabayProvider"

    def test_default_provider_is_pexels(self) -> None:
        settings = Settings()  # type: ignore[call-arg]
        assert settings.stock_provider == "pexels"


@pytest.mark.usefixtures("_env")
class TestCreateImageProvider:
    def test_returns_none_without_api_key(self) -> None:
        settings = Settings()  # type: ignore[call-arg]
        provider = create_image_provider(settings)
        assert provider is None

    def test_creates_gemini_with_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_GEMINI_API_KEY", "test-gemini-key")
        settings = Settings()  # type: ignore[call-arg]
        mock_cls = MagicMock()
        with patch("content_farm.visual.gemini.GeminiImageProvider", mock_cls):
            provider = create_image_provider(settings)
        assert provider is not None

    def test_unknown_provider_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_IMAGE_PROVIDER", "unknown")
        monkeypatch.setenv("CF_GEMINI_API_KEY", "test-key")
        settings = Settings()  # type: ignore[call-arg]
        provider = create_image_provider(settings)
        assert provider is None

    def test_default_image_provider_is_gemini(self) -> None:
        settings = Settings()  # type: ignore[call-arg]
        assert settings.image_provider == "gemini"
