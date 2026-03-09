"""Tests for LLM cache backends."""

from __future__ import annotations

import pytest

from content_farm.llm.cache import FileCache, NullCache, ResponseCache


@pytest.fixture
def file_cache(tmp_path) -> FileCache:
    return FileCache(tmp_path / "cache")


class TestResponseCache:
    def test_make_key_deterministic(self) -> None:
        key1 = ResponseCache.make_key("test", "content")
        key2 = ResponseCache.make_key("test", "content")
        assert key1 == key2

    def test_make_key_different_content(self) -> None:
        key1 = ResponseCache.make_key("test", "content_a")
        key2 = ResponseCache.make_key("test", "content_b")
        assert key1 != key2

    def test_make_key_includes_prefix(self) -> None:
        key = ResponseCache.make_key("outline", "some content")
        assert key.startswith("outline_")


class TestFileCache:
    @pytest.mark.asyncio
    async def test_get_miss(self, file_cache: FileCache) -> None:
        result = await file_cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get(self, file_cache: FileCache) -> None:
        data = {"key": "value", "number": 42}
        await file_cache.set("test_key", data)
        result = await file_cache.get("test_key")
        assert result == data

    @pytest.mark.asyncio
    async def test_set_creates_directory(self, tmp_path) -> None:
        cache = FileCache(tmp_path / "nested" / "dir")
        await cache.set("key", {"data": True})
        result = await cache.get("key")
        assert result == {"data": True}

    @pytest.mark.asyncio
    async def test_corrupted_cache_returns_none(self, file_cache: FileCache, tmp_path) -> None:
        # Write invalid JSON
        cache_file = tmp_path / "cache" / "bad_key.json"
        cache_file.write_text("not valid json{{{")
        result = await file_cache.get("bad_key")
        assert result is None


class TestNullCache:
    @pytest.mark.asyncio
    async def test_always_misses(self) -> None:
        cache = NullCache()
        await cache.set("key", "value")
        assert await cache.get("key") is None
