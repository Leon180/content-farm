"""Shared test fixtures."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from content_farm.config import Settings
from content_farm.llm.cache import NullCache, ResponseCache
from content_farm.llm.client import LLMClient


@pytest.fixture(autouse=True)
def _no_real_claude(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Tests never launch a real `claude -p` reviewer: point the binary at a stub that fails."""
    stub = tmp_path_factory.getbasetemp() / "claude-stub"
    if not stub.exists():
        stub.write_text("#!/bin/sh\necho 'no real claude in tests' >&2\nexit 97\n", encoding="utf-8")
        stub.chmod(0o755)
    monkeypatch.setenv("CF_CLAUDE_BIN", str(stub))
    # Unit tests do not wait in the machine-wide heavy queue (tests of the queue clear this).
    monkeypatch.setenv("CF_HEAVY_SLOT", "unit-test")
    monkeypatch.setenv("CF_ADMISSION_UNIT_TEST", "1")      # only honoured inside pytest (lanes.queue)


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
