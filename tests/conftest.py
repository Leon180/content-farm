"""Shared test fixtures."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from content_farm.config import Settings
from content_farm.llm.cache import NullCache, ResponseCache
from content_farm.llm.client import LLMClient


@pytest.fixture
def mock_llm() -> AsyncMock:
    """Mock LLM client that returns no data by default."""
    return AsyncMock(spec=LLMClient)


@pytest.fixture
def null_cache() -> NullCache:
    """Cache that always misses."""
    return NullCache()


@pytest.fixture
def test_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Settings with test values."""
    monkeypatch.setenv("CF_ANTHROPIC_API_KEY", "test-key-not-real")
    return Settings()  # type: ignore[call-arg]
