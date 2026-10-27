"""Polite JSON GETs for the radar: per-host spacing, an on-disk cache with a TTL, request counting.

Why not ``production.news.fetch.PoliteHttp``: the radar needs a per-request ``Authorization`` header
(YouTube OAuth), a TTL per call (Wikipedia titles are stable for a week, YouTube search for a day) and
its cache must never store a URL that carries an API key.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import httpx

USER_AGENT = "content-farm-topic-radar/0.1 (+https://github.com/Leon180/content-farm; editorial topic research)"
TIMEOUT = 20.0
DEFAULT_SPACING = 1.0
HOST_SPACING = {
    "www.googleapis.com": 0.2,
    "wikimedia.org": 0.2,          # Wikimedia asks for <= 200 req/s; we are far below
    "zh.wikipedia.org": 0.2, "en.wikipedia.org": 0.2, "ja.wikipedia.org": 0.2,
    "hn.algolia.com": 0.5,
    "www.reddit.com": 6.5,         # unauthenticated clients are limited to ~10 requests/minute
    "api.bilibili.com": 2.0,
    "www.v2ex.com": 1.5,           # V2EX documents 120 requests/hour for the public API; a run sends ~10
}
_SECRET_PARAM = re.compile(r"([?&](?:key|access_token)=)[^&\s]+")


class SourceError(RuntimeError):
    """A source did not answer usefully. The message never contains a key or token."""


def scrub(text: str) -> str:
    return _SECRET_PARAM.sub(r"\1***", text)


@dataclass
class Reply:
    status: int
    data: object


@dataclass
class RadarHttp:
    cache_dir: Path | None = None
    default_ttl: float = 6 * 3600
    spacing: dict[str, float] = field(default_factory=lambda: dict(HOST_SPACING))
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    wall: Callable[[], float] = time.time
    network: Counter = field(default_factory=Counter)      # host -> requests sent
    cached: Counter = field(default_factory=Counter)       # host -> answers served from disk
    _last: dict[str, float] = field(default_factory=dict)
    _client: httpx.Client | None = None

    def _path(self, url: str) -> Path | None:
        if self.cache_dir is None:
            return None
        host = urlsplit(url).hostname or "unknown"
        return self.cache_dir / host / f"{hashlib.sha1(url.encode()).hexdigest()}.json"

    def _cache_get(self, url: str, ttl: float) -> Reply | None:
        path = self._path(url)
        if path is None or ttl <= 0 or not path.is_file():
            return None
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
            if self.wall() - float(row["at"]) > ttl:
                return None
            return Reply(int(row["status"]), row["data"])
        except (OSError, ValueError, KeyError):
            return None        # a damaged cache entry is just a miss

    def is_cached(self, url: str, ttl: float | None = None) -> bool:
        return self._cache_get(url, self.default_ttl if ttl is None else ttl) is not None

    def _cache_put(self, url: str, reply: Reply) -> None:
        path = self._path(url)
        if path is None or reply.status != 200:
            return
        if isinstance(reply.data, dict) and reply.data.get("code") not in (None, 0):
            return      # Bilibili reports risk control (-352) as http 200 with a body code: a refusal must not be replayed from cache
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"at": self.wall(), "status": reply.status, "data": reply.data}), encoding="utf-8")

    def _wait(self, host: str) -> None:
        gap = self.spacing.get(host, DEFAULT_SPACING)
        last = self._last.get(host)
        if last is not None:
            remaining = gap - (self.clock() - last)
            if remaining > 0:
                self.sleep(remaining)
        self._last[host] = self.clock()

    def _client_(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, follow_redirects=True)
        return self._client

    def get_json(self, url: str, *, headers: Mapping[str, str] | None = None, ttl: float | None = None) -> Reply:
        """GET ``url`` as JSON. Non-200 answers are returned (not cached); network and JSON errors raise SourceError."""
        host = urlsplit(url).hostname or ""
        hit = self._cache_get(url, self.default_ttl if ttl is None else ttl)
        if hit is not None:
            self.cached[host] += 1
            return hit
        self._wait(host)
        self.network[host] += 1
        try:
            resp = self._client_().get(url, headers=dict(headers or {}))
        except httpx.HTTPError as exc:
            raise SourceError(scrub(f"GET {url}: {type(exc).__name__}")) from exc
        try:
            data = resp.json()
        except ValueError:
            data = None
        reply = Reply(resp.status_code, data)
        self._cache_put(url, reply)
        return reply

    def post_form(self, url: str, form: Mapping[str, str]) -> Reply:
        """POST a form (OAuth token refresh). Never cached."""
        host = urlsplit(url).hostname or ""
        self._wait(host)
        self.network[host] += 1
        try:
            resp = self._client_().post(url, data=dict(form))
        except httpx.HTTPError as exc:
            raise SourceError(scrub(f"POST {host}: {type(exc).__name__}")) from exc
        try:
            data = resp.json()
        except ValueError:
            data = None
        return Reply(resp.status_code, data)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
