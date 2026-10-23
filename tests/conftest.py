"""Shared test fixtures."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from content_farm.config import Settings
from content_farm.llm.cache import NullCache, ResponseCache
from content_farm.llm.client import LLMClient
from tests._shared_path_guard import install

os.environ["CF_REVIEW_POLICY"] = "legacy"   # before test modules call load_review() at import (see _no_real_claude)

REPO = Path(__file__).resolve().parents[1]
SHARED_PATH_GUARD = install(REPO)   # inactive until pytest_configure


def pytest_configure(config: pytest.Config) -> None:
    SHARED_PATH_GUARD.active = True


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session: pytest.Session) -> None:
    SHARED_PATH_GUARD.active = False   # pytest's own reports (--junitxml …) may go anywhere


@pytest.fixture(autouse=True)
def _shared_paths_to_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Every machine-wide path (content_farm.paths) points at tmp; a write to a real one fails the test."""
    shared = tmp_path_factory.getbasetemp() / "shared"
    monkeypatch.setenv("CF_CACHE_ROOT", str(shared / "cache"))
    monkeypatch.setenv("CF_HEAVY_QUEUE_DIR", str(shared / "cache" / "heavy-queue"))
    monkeypatch.setenv("CF_LOCAL_TTS_LOCK_PATH", str(shared / "cache" / "local_tts.lock"))
    monkeypatch.setenv("CF_ORCH_MAIL", str(shared / "orchestrator" / "orch_mail.py"))   # absent: no mail
    monkeypatch.setenv("CF_ORCH_MAIL_DIR", str(shared / "orch-mail"))
    monkeypatch.setenv("ORCH_MAIL_DIR", str(shared / "orch-mail"))
    before = len(SHARED_PATH_GUARD.violations)
    yield
    hits = SHARED_PATH_GUARD.violations[before:]
    if hits:
        pytest.fail("\n".join(hits), pytrace=False)


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
    # The round machinery is tested with the yaml's rounds / thresholds / waivers; policy tests clear this.
    monkeypatch.setenv("CF_REVIEW_POLICY", "legacy")


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
