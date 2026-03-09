"""Response cache with file-based and Redis backends."""

from __future__ import annotations

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ResponseCache(ABC):
    """Abstract cache interface for LLM responses."""

    @abstractmethod
    async def get(self, key: str) -> Any | None: ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl_seconds: int = 86400) -> None: ...

    @staticmethod
    def make_key(prefix: str, content: str) -> str:
        """Create a cache key from a prefix and content hash."""
        h = hashlib.sha256(content.encode()).hexdigest()[:16]
        return f"{prefix}_{h}"


class FileCache(ResponseCache):
    """JSON file-based cache. Good for development."""

    def __init__(self, cache_dir: Path) -> None:
        self._dir = cache_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    async def get(self, key: str) -> Any | None:
        path = self._dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Cache read failed for key=%s: %s", key, exc)
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int = 86400) -> None:
        path = self._dir / f"{key}.json"
        try:
            path.write_text(json.dumps(value, default=str))
        except OSError as exc:
            logger.warning("Cache write failed for key=%s: %s", key, exc)


class RedisCache(ResponseCache):
    """Redis-backed cache. For production use."""

    def __init__(self, redis_url: str) -> None:
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(redis_url)

    async def get(self, key: str) -> Any | None:
        raw = await self._redis.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("Redis cache decode failed for key=%s: %s", key, exc)
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int = 86400) -> None:
        await self._redis.set(key, json.dumps(value, default=str), ex=ttl_seconds)


class NullCache(ResponseCache):
    """No-op cache for testing."""

    async def get(self, key: str) -> Any | None:
        return None

    async def set(self, key: str, value: Any, ttl_seconds: int = 86400) -> None:
        pass
