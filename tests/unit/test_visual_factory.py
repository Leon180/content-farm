"""Tests for visual provider factory."""

from __future__ import annotations

import pytest

from content_farm.config import Settings
from content_farm.visual.factory import create_stock_provider


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

    def test_unknown_provider_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_STOCK_PROVIDER", "unknown")
        settings = Settings()  # type: ignore[call-arg]
        with pytest.raises(ValueError, match="Unknown stock provider"):
            create_stock_provider(settings)

    def test_pexels_missing_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CF_PEXELS_API_KEY", "")
        settings = Settings()  # type: ignore[call-arg]
        with pytest.raises(ValueError, match="CF_PEXELS_API_KEY"):
            create_stock_provider(settings)

    def test_default_provider_is_pexels(self) -> None:
        settings = Settings()  # type: ignore[call-arg]
        assert settings.stock_provider == "pexels"
