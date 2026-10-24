"""Find, licence-check, download and cache outside footage (Wikimedia, NASA, NOAA, Pexels, Pixabay).

Order of work for one slide: cached clip → search providers in turn (rate-limited, one request at a time, results cached)
→ ``screen`` every candidate (licence whitelist, author, page URL, no-people) → pick the most relevant → download once →
write the sidecar next to the file. A pinned ``url`` skips the search but not the screening. Nothing is fetched for a
refused candidate, and a refusal reason is kept so the media report can say why a slide fell back.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlparse

import httpx

from content_farm.explainer.footage import nasa, noaa, wikimedia
from content_farm.explainer.footage.models import FootageCandidate, screen, sidecar
from content_farm.explainer.stock import (
    MAX_DOWNLOAD_BYTES,
    RateLimiter,
    StockCandidate,
    StockClient,
    StockUnavailable,
    relevance_terms,
)
from content_farm.explainer.stock import _words  # noqa: PLC2701  (shared tokenizer)

logger = logging.getLogger(__name__)

FOOTAGE_UA = "content-farm-footage/1 (https://github.com/Leon180/content-farm; cached, one request at a time)"
DEFAULT_ORDER = ("nasa", "wikimedia", "pexels", "pixabay")   # noaa is page-pinned (no search endpoint)
CACHE_VERSION = 1
_PREFERENCE = {"pd": 0, "cc0": 0, "pexels": 1, "pixabay": 1, "cc-by": 2, "cc-by-sa": 3}


@dataclass(frozen=True)
class FootageAsset:
    query: str
    candidate: FootageCandidate
    path: Path
    sidecar_path: Path
    from_cache: bool
    matched: tuple[str, ...] = ()
    ranking: dict | None = None        # semantic re-ranking record (model, licence, scores) when CLIP ranking ran


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "q"


def _from_stock(c: StockCandidate) -> FootageCandidate:
    return FootageCandidate(
        provider=c.provider, provider_id=c.provider_id, title=c.page_url.rstrip("/").rsplit("/", 1)[-1].replace("-", " "),
        page_url=c.page_url, download_url=c.download_url, width=c.width, height=c.height, duration=c.duration,
        author=c.author, author_url=c.author_url, license_name=c.license_name, license_url=c.license_url, tags=c.tags)


class FootageClient:
    def __init__(self, *, cache_dir: Path, stock: StockClient | None = None, order: tuple[str, ...] = DEFAULT_ORDER,
                 http: httpx.Client | None = None, limiter: RateLimiter | None = None, avoid_faces: bool = True,
                 ranker: Callable[[list[FootageCandidate], str], tuple[list[FootageCandidate], dict]] | None = None) -> None:
        self._cache = cache_dir
        self._stock = stock
        self._order = order
        self._http = http or httpx.Client(timeout=45.0, follow_redirects=True, headers={"User-Agent": FOOTAGE_UA})
        self._limiter = limiter or RateLimiter()
        self._avoid_faces = avoid_faces
        self._ranker = ranker
        self.refusals: list[str] = []

    # ---- public ---------------------------------------------------------------------------------------------
    def fetch(self, query: str, min_seconds: float, keywords: tuple[str, ...] = (), url: str = "",
              sentence: str = "") -> FootageAsset:
        """A screened, cached clip for ``query`` (or the pinned ``url``) or :class:`StockUnavailable` with the reason."""
        self.refusals = []
        if url:
            return self._fetch_pinned(url, query)
        terms = relevance_terms(query, keywords)
        if not terms:
            raise StockUnavailable(f"query {query!r} has only generic words; name what is on screen or set media.keywords")
        found: list[FootageCandidate] = []
        for provider in self._order:
            try:
                found += self._search(provider, query)
            except StockUnavailable as exc:
                self.refusals.append(str(exc))
            except (httpx.HTTPError, ValueError, OSError) as exc:
                self.refusals.append(f"{provider}: {type(exc).__name__}: {exc}")
        good = self._rank(self._screened(found), terms, min_seconds)
        if not good:
            raise StockUnavailable(f"no licensed, on-topic footage for {query!r} ({'; '.join(self.refusals[-6:])})")
        good, ranking = self._semantic(good, sentence)
        return replace(self._store(query, good[0]), matched=_matched(good[0], terms), ranking=ranking)

    def _semantic(self, good: list[FootageCandidate], sentence: str) -> tuple[list[FootageCandidate], dict | None]:
        """Re-order the best keyword matches by closeness to the spoken sentence (local CLIP); any failure keeps the order."""
        if self._ranker is None or not sentence.strip():
            return good, None
        try:
            return self._ranker(good, sentence)
        except Exception as exc:  # noqa: BLE001 - a broken local model must never lose the clip
            self.refusals.append(f"clip rank skipped: {type(exc).__name__}: {exc}")
            return good, {"changed": False, "reason": f"ranker failed: {type(exc).__name__}"}

    # ---- search ---------------------------------------------------------------------------------------------
    def _search(self, provider: str, query: str) -> list[FootageCandidate]:
        cached = self._search_cache(provider, query)
        if cached is not None:
            return cached
        if provider in {"pexels", "pixabay"}:
            if self._stock is None or not self._stock.configured:
                raise StockUnavailable(f"{provider}: no API key")
            found = [_from_stock(c) for c in self._stock.search(provider, query)]
        elif provider == "wikimedia":
            self._limiter.wait("wikimedia")
            found = wikimedia.parse(self._get_json("wikimedia", wikimedia.API, wikimedia.search_params(query)))
        elif provider == "nasa":
            self._limiter.wait("nasa")
            found = self._resolve_nasa(nasa.parse(self._get_json("nasa", nasa.SEARCH, nasa.search_params(query))))
        else:
            raise StockUnavailable(f"unknown footage provider {provider!r}")
        self._save_search(provider, query, found)
        return found

    def _resolve_nasa(self, hits: list[FootageCandidate]) -> list[FootageCandidate]:
        """Attach a file URL and size to the screened-OK hits only (one manifest request each, capped)."""
        out: list[FootageCandidate] = []
        for hit in hits[:12]:
            if not screen(hit, avoid_faces=self._avoid_faces).ok:
                out.append(hit)       # kept so the refusal is reported; never downloaded
                continue
            self._limiter.wait("nasa")
            files = self._get_json("nasa", hit.download_url, {})
            link = nasa.pick_file(files if isinstance(files, list) else [])
            if link:
                out.append(replace(hit, download_url=link))
        return out

    def _get_json(self, provider: str, url: str, params: dict):
        response = self._http.get(url, params=params)
        self._limiter.observe(provider, response)
        if response.status_code >= 400:
            raise StockUnavailable(f"{provider}: HTTP {response.status_code}")
        return response.json()

    # ---- screening and ranking -------------------------------------------------------------------------------
    def _screened(self, found: list[FootageCandidate], *, avoid_faces: bool | None = None) -> list[FootageCandidate]:
        faces = self._avoid_faces if avoid_faces is None else avoid_faces
        out = []
        for c in found:
            result = screen(c, avoid_faces=faces)
            if result.ok and c.download_url:
                out.append(c)
            else:
                self.refusals.append(f"{c.provider}:{c.provider_id} 拒收：{result.reason or '沒有影片檔'}")
        return out

    def _rank(self, found: list[FootageCandidate], terms: tuple[str, ...], min_seconds: float) -> list[FootageCandidate]:
        def key(c: FootageCandidate) -> tuple:
            code = screen(c).verdict.code
            return (len(_matched(c, terms)), -_PREFERENCE.get(code, 9), c.width >= 1280 or c.width == 0,
                    c.duration >= min_seconds or c.duration == 0, min(c.duration, 60))
        return sorted((c for c in found if _matched(c, terms)), key=key, reverse=True)

    # ---- pinned URL --------------------------------------------------------------------------------------------
    def _fetch_pinned(self, url: str, query: str) -> FootageAsset:
        host = urlparse(url).netloc.lower()
        if "commons.wikimedia.org" in host:
            title = wikimedia.file_title_from_url(url)
            if not title:
                raise StockUnavailable(f"not a Commons file page: {url}")
            self._limiter.wait("wikimedia")
            found = wikimedia.parse(self._get_json("wikimedia", wikimedia.API, wikimedia.title_params(title)))
        elif host.endswith("images.nasa.gov") and "/details/" in url:
            nasa_id = url.rstrip("/").rsplit("/", 1)[-1]
            self._limiter.wait("nasa")
            found = self._resolve_nasa(
                nasa.parse(self._get_json("nasa", nasa.SEARCH, {"nasa_id": nasa_id, "media_type": "video"})))
        elif noaa.is_noaa_host(url):
            self._limiter.wait("noaa")
            response = self._http.get(url)
            if response.status_code >= 400:
                raise StockUnavailable(f"noaa: HTTP {response.status_code} for {url}")
            try:
                found = [noaa.scan_page(response.text, url)]
            except noaa.PageRefused as exc:
                raise StockUnavailable(f"NOAA 頁面拒收：{exc}") from exc
        else:
            raise StockUnavailable(f"pinned footage url must be Commons / images.nasa.gov / noaa.gov: {url}")
        # A pinned clip was picked by a person who looked at it: the licence screen still applies, the title-word
        # people screen (which also trips on "scientists" in a caption of an empty seafloor) does not.
        good = self._screened(found, avoid_faces=False)
        if not good:
            raise StockUnavailable(f"pinned footage refused ({'; '.join(self.refusals)})")
        return self._store(query or good[0].title, good[0])

    # ---- cache -------------------------------------------------------------------------------------------------
    def _entry(self, c: FootageCandidate) -> Path:
        return self._cache / c.provider / re.sub(r"[^A-Za-z0-9_.-]+", "_", c.provider_id)[:80]

    def _store(self, query: str, c: FootageCandidate) -> FootageAsset:
        entry = self._entry(c)
        meta, video = entry / "sidecar.json", next(iter(sorted(entry.glob("video.*"))), None) if entry.is_dir() else None
        if meta.is_file() and video is not None and not video.name.endswith(".part"):
            return FootageAsset(query, c, video, meta, from_cache=True)
        entry.mkdir(parents=True, exist_ok=True)
        suffix = Path(urlparse(c.download_url).path).suffix.lower() or ".mp4"
        video, partial = entry / f"video{suffix}", entry / f"video{suffix}.part"
        self._limiter.wait(f"dl-{c.provider}")
        size = 0
        source = wikimedia.transcode_url(c.download_url) if (
            c.provider == "wikimedia" and c.size_bytes > wikimedia.MAX_ORIGINAL_BYTES) else c.download_url
        with self._http.stream("GET", source) as response:
            response.raise_for_status()
            with partial.open("wb") as fh:
                for chunk in response.iter_bytes(chunk_size=1 << 16):
                    size += len(chunk)
                    if size > MAX_DOWNLOAD_BYTES:
                        partial.unlink(missing_ok=True)
                        raise StockUnavailable(f"{c.provider}: file > {MAX_DOWNLOAD_BYTES} bytes")
                    fh.write(chunk)
        partial.replace(video)
        meta.write_text(json.dumps(sidecar(c), ensure_ascii=False, indent=2), "utf-8")
        logger.info("footage %r → %s:%s (%d bytes)", query, c.provider, c.provider_id, size)
        return FootageAsset(query, c, video, meta, from_cache=False)

    def _search_cache(self, provider: str, query: str) -> list[FootageCandidate] | None:
        path = self._search_path(provider, query)
        try:
            data = json.loads(path.read_text("utf-8"))
            return [FootageCandidate(**row) for row in data["candidates"]] if data.get("version") == CACHE_VERSION else None
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def _save_search(self, provider: str, query: str, found: list[FootageCandidate]) -> None:
        path = self._search_path(provider, query)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": CACHE_VERSION, "candidates": [c.to_json() for c in found]},
                                   ensure_ascii=False), "utf-8")

    def _search_path(self, provider: str, query: str) -> Path:
        norm = " ".join(query.lower().split())
        return self._cache / "_search" / f"{provider}-{_slug(norm)}-{hashlib.sha1(norm.encode()).hexdigest()[:10]}.json"


def _matched(c: FootageCandidate, terms: tuple[str, ...]) -> tuple[str, ...]:
    words = _words(c.text)
    return tuple(t for t in terms if all(p in words for p in t.split("-")) or t.replace("-", "") in words)


__all__ = ["FootageAsset", "FootageClient", "DEFAULT_ORDER"]
