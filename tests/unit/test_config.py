"""Tests for configuration module."""

from __future__ import annotations

import pytest

from content_farm.config import Settings


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "sk-test-123")
    monkeypatch.setenv("CF_LOG_LEVEL", "DEBUG")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.anthropic_api_key.get_secret_value() == "sk-test-123"
    assert settings.log_level == "DEBUG"


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "sk-test")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.llm_cheap_model == "claude-haiku-4-5"
    assert settings.llm_expensive_model == "claude-sonnet-4-6"
    assert settings.cache_backend == "file"
    assert settings.max_concurrent_scenes == 5


def test_settings_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CF_ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(Exception):
        Settings()  # type: ignore[call-arg]


def test_settings_secret_masking(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "sk-secret-key")
    settings = Settings()  # type: ignore[call-arg]

    # SecretStr should not expose the value in repr/str
    assert "sk-secret-key" not in repr(settings)
