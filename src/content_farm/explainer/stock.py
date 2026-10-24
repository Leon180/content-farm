"""Stock B-roll for explainer slides: Pexels first, Pixabay second, cached per query.

Terms this module is written to respect (checked 2026-10):
- Pexels API: 200 requests/hour, 20,000/month by default; credit the creator
  and show a link to Pexels; never work around the rate limit. The key goes in
  the ``Authorization`` header (search only — file downloads go without it).
  We space calls >= 1 s apart, cap a run at ``MAX_CALLS_PER_RUN`` per provider,
  and stop as soon as ``X-Ratelimit-Remaining`` reaches 0 or a 429 comes back.
- Pixabay API: 100 requests/60 s; results must be cached (24 h) and files
  downloaded rather than hot-linked. Our per-query cache never expires on its
  own, so the same query is never searched twice.

Every chosen clip carries author, page URL and licence so ``credits.json``
can be pasted into the video description.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

PEXELS_SEARCH = "https://api.pexels.com/videos/search"
PIXABAY_SEARCH = "https://pixabay.com/api/videos/"
PEXELS_LICENSE = ("Pexels License", "https://www.pexels.com/license/")
PIXABAY_LICENSE = ("Pixabay Content License", "https://pixabay.com/service/license-summary/")
USER_AGENT = "content-farm-explainer/2 (+stock b-roll; cached per query)"
MIN_WIDTH = 1280            # below this the 1920 upscale looks soft — not "suitable"
TARGET_WIDTH = 1920
MIN_ASPECT = 1.6            # landscape only (16:9 = 1.78)
MAX_DOWNLOAD_BYTES = 300 * 1024 * 1024
CACHE_VERSION = 1
MAX_CALLS_PER_RUN = 60  # well under Pexels' 200/hour even if two runs overlap


class StockUnavailable(RuntimeError):
    """No suitable footage; ``str(exc)`` is the reason recorded in the media report."""


@dataclass(frozen=True)
class StockCandidate:
    provider: str          # "pexels" | "pixabay"
    provider_id: str
    page_url: str
    download_url: str
    width: int
    height: int
    duration: float
    author: str
    author_url: str
    license_name: str
    license_url: str
    tags: str = ""         # provider tags, comma separated (Pixabay always, Pexels rarely)


@dataclass(frozen=True)
class StockAsset:
    query: str
    candidate: StockCandidate
    path: Path
    from_cache: bool
    matched: tuple[str, ...] = ()  # relevance terms found in the clip's slug / tags


class RateLimiter:
    """Spaces calls per provider and remembers when a provider said 'no more'."""

    def __init__(
        self, min_interval: float = 1.0, max_calls: int = MAX_CALLS_PER_RUN,
        clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._min_interval = min_interval
        self._max_calls = max_calls
        self._calls: dict[str, int] = {}
        self._clock = clock
        self._sleep = sleep
        self._last: dict[str, float] = {}
        self._exhausted: dict[str, str] = {}

    def wait(self, provider: str) -> None:
        if provider in self._exhausted:
            raise StockUnavailable(self._exhausted[provider])
        if self._calls.get(provider, 0) >= self._max_calls:
            raise StockUnavailable(f"{provider}: per-run budget of {self._max_calls} calls used")
        self._calls[provider] = self._calls.get(provider, 0) + 1
        last = self._last.get(provider)
        if last is not None:
            delay = self._min_interval - (self._clock() - last)
            if delay > 0:
                self._sleep(delay)
        self._last[provider] = self._clock()

    def observe(self, provider: str, response: httpx.Response) -> None:
        remaining = response.headers.get("x-ratelimit-remaining")
        if response.status_code == 429 or (remaining is not None and remaining.strip() == "0"):
            reset = response.headers.get("x-ratelimit-reset", "?")
            self._exhausted[provider] = f"{provider} rate limit reached (reset {reset})"
            logger.warning("%s rate limit reached; no more calls this run", provider)


def _int(value: object) -> int:
    try:
        return int(value or 0)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return 0


def _suitable(width: int, height: int) -> bool:
    return width >= MIN_WIDTH and height > 0 and width / height >= MIN_ASPECT


def _pexels_file(files: list[dict]) -> dict | None:
    """Smallest landscape file that is >= 1920 wide, else the widest suitable one."""
    usable = [f for f in files if f.get("link") and _suitable(_int(f.get("width")), _int(f.get("height")))]
    full_hd = [f for f in usable if _int(f.get("width")) >= TARGET_WIDTH]
    if full_hd:
        return min(full_hd, key=lambda f: _int(f.get("width")))
    return max(usable, key=lambda f: _int(f.get("width")), default=None)


def parse_pexels(data: dict) -> list[StockCandidate]:
    out: list[StockCandidate] = []
    for video in data.get("videos") or []:
        chosen = _pexels_file(video.get("video_files") or [])
        if chosen is None:
            continue
        user = video.get("user") or {}
        tags = [t if isinstance(t, str) else str((t or {}).get("name", "")) for t in video.get("tags") or []]
        out.append(StockCandidate(
            provider="pexels",
            provider_id=str(video.get("id", "")),
            page_url=str(video.get("url", "")),
            download_url=str(chosen["link"]),
            width=_int(chosen.get("width")),
            height=_int(chosen.get("height")),
            duration=float(video.get("duration") or 0),
            author=str(user.get("name", "")),
            author_url=str(user.get("url", "")),
            license_name=PEXELS_LICENSE[0],
            license_url=PEXELS_LICENSE[1],
            tags=", ".join(t for t in tags if t),
        ))
    return out


def _pixabay_file(files: list[dict]) -> dict | None:
    """Pixabay ``large`` is usually 4K; take the smallest rendition that is still >= 1920."""
    usable = [f for f in files if f.get("url") and _suitable(_int(f.get("width")), _int(f.get("height")))]
    full_hd = [f for f in usable if _int(f.get("width")) >= TARGET_WIDTH]
    if full_hd:
        return min(full_hd, key=lambda f: _int(f.get("width")))
    return max(usable, key=lambda f: _int(f.get("width")), default=None)


def parse_pixabay(data: dict) -> list[StockCandidate]:
    out: list[StockCandidate] = []
    for hit in data.get("hits") or []:
        files = hit.get("videos") or {}
        chosen = _pixabay_file([files.get(q) or {} for q in ("large", "medium", "small")])
        if chosen is None:
            continue
        user, user_id = str(hit.get("user", "")), hit.get("user_id", "")
        out.append(StockCandidate(
            provider="pixabay",
            provider_id=str(hit.get("id", "")),
            page_url=str(hit.get("pageURL", "")),
            download_url=str(chosen["url"]),
            width=_int(chosen.get("width")),
            height=_int(chosen.get("height")),
            duration=float(hit.get("duration") or 0),
            author=user,
            author_url=f"https://pixabay.com/users/{user}-{user_id}/" if user else "",
            license_name=PIXABAY_LICENSE[0],
            license_url=PIXABAY_LICENSE[1],
            tags=str(hit.get("tags", "")),
        ))
    return out


# Words that say nothing about *what* is on screen. "factory production line"
# is all generic and came back as a motorbike assembly line, so these never
# count as evidence that a clip is on topic.
GENERIC_WORDS = frozenset({
    "a", "an", "and", "the", "of", "in", "on", "at", "with", "for", "to", "by", "from",
    "close", "closeup", "up", "view", "shot", "footage", "video", "background", "slow", "motion",
    "aerial", "drone", "timelapse", "time", "lapse", "4k", "hd",
    "factory", "production", "line", "manufacturing", "industry", "industrial", "business",
    "technology", "tech", "modern", "process", "work", "working", "worker", "workers",
    "people", "person", "man", "woman", "engineer", "engineers", "team", "office",
    "inspection", "equipment", "machine", "machinery", "assembly", "building", "construction",
})


def _words(text: str) -> set[str]:
    seq = re.findall(r"[a-z0-9]+", text.lower())
    words = set(seq) | {a + b for a, b in zip(seq, seq[1:])}  # "clean room" → cleanroom
    return words | {w[:-1] for w in words if len(w) > 3 and w.endswith("s")}  # wafers → wafer


def relevance_terms(query: str, keywords: tuple[str, ...] = ()) -> tuple[str, ...]:
    """Words a clip must mention to count as on topic: ``keywords``, else the query's specific words."""
    if keywords:
        return tuple(dict.fromkeys(k.lower() for k in keywords))
    words = re.findall(r"[a-z0-9]+", query.lower())
    return tuple(dict.fromkeys(w for w in words if w not in GENERIC_WORDS and len(w) > 1))


def candidate_text(c: StockCandidate) -> str:
    """What the provider says the clip shows: the Pexels page slug + any tags."""
    slug = c.page_url.rstrip("/").rsplit("/", 1)[-1]
    return f"{slug} {c.tags}"


def relevance(c: StockCandidate, terms: tuple[str, ...]) -> tuple[str, ...]:
    words = _words(candidate_text(c))
    hits = []
    for term in terms:
        parts = term.split("-")  # "clean-room" matches the slug "clean-room" too
        if all(p in words for p in parts) or term.replace("-", "") in words:
            hits.append(term)
    return tuple(hits)


def rank(candidates: list[StockCandidate], min_seconds: float,
         terms: tuple[str, ...] = ()) -> list[StockCandidate]:
    """Most relevance terms first, then Full-HD, then long enough to trim/slow (not loop), then longest."""
    def key(c: StockCandidate) -> tuple:
        return (len(relevance(c, terms)), c.width >= TARGET_WIDTH, c.duration * 1.5 >= min_seconds,
                c.duration)
    return sorted((c for c in candidates if c.duration > 0), key=key, reverse=True)


def cache_key(query: str) -> str:
    norm = " ".join(query.lower().split())
    slug = re.sub(r"[^a-z0-9]+", "-", norm).strip("-")[:40] or "q"
    return f"{slug}-{hashlib.sha1(norm.encode()).hexdigest()[:10]}"


class StockClient:
    def __init__(
        self, *, pexels_key: str, pixabay_key: str, cache_dir: Path,
        http: httpx.Client | None = None, limiter: RateLimiter | None = None,
    ) -> None:
        self._keys = {"pexels": pexels_key.strip(), "pixabay": pixabay_key.strip()}
        self._cache_dir = cache_dir
        self._http = http or httpx.Client(
            timeout=30.0, follow_redirects=True, headers={"User-Agent": USER_AGENT},
        )
        self._limiter = limiter or RateLimiter()

    @property
    def configured(self) -> bool:
        return any(self._keys.values())

    def fetch(self, query: str, min_seconds: float, keywords: tuple[str, ...] = ()) -> StockAsset:
        """Cached on-topic asset for ``query`` or :class:`StockUnavailable` with the reason.

        A clip counts only if its slug / tags mention one of :func:`relevance_terms`;
        a cached clip that no longer passes (stricter keywords) is searched again.
        """
        terms = relevance_terms(query, keywords)
        if not terms:
            raise StockUnavailable(
                f"query {query!r} has only generic words; name what is on screen or set media.keywords")
        entry = self._cache_dir / cache_key(query)
        cached = self._load_cache(entry, query)
        if cached is not None:
            matched = relevance(cached.candidate, terms)
            if matched:
                return replace(cached, matched=matched)
            logger.info("cached clip for %r mentions none of %s; searching again", query, terms)
        if not self.configured:
            raise StockUnavailable("no Pexels/Pixabay API key configured")
        reasons: list[str] = []
        for provider in ("pexels", "pixabay"):
            if not self._keys[provider]:
                reasons.append(f"{provider}: no key")
                continue
            try:
                found = rank(self._search(provider, query), min_seconds, terms)
                relevant = [c for c in found if relevance(c, terms)]
                if not relevant:
                    reasons.append(f"{provider}: {len(found)} usable result(s), none mention {'/'.join(terms)}")
                    continue
                asset = self._store(entry, query, relevant[0])
                return replace(asset, matched=relevance(relevant[0], terms))
            except StockUnavailable as exc:
                reasons.append(str(exc))
            except (httpx.HTTPError, ValueError, OSError) as exc:
                reasons.append(f"{provider}: {type(exc).__name__}: {exc}")
        raise StockUnavailable(f"no on-topic footage for {query!r} ({'; '.join(reasons)})")

    def search(self, provider: str, query: str) -> list[StockCandidate]:
        """One rate-limited provider search (used by the footage client, which does its own screening)."""
        return self._search(provider, query)

    def _search(self, provider: str, query: str) -> list[StockCandidate]:
        self._limiter.wait(provider)
        if provider == "pexels":
            response = self._http.get(
                PEXELS_SEARCH,
                params={"query": query, "orientation": "landscape", "size": "medium", "per_page": 15},
                headers={"Authorization": self._keys["pexels"]},
            )
        else:
            response = self._http.get(PIXABAY_SEARCH, params={
                "key": self._keys["pixabay"], "q": query[:100], "video_type": "film",
                "per_page": 20, "safesearch": "true",
            })
        self._limiter.observe(provider, response)
        if response.status_code == 429:
            raise StockUnavailable(f"{provider}: HTTP 429 rate limited")
        if response.status_code >= 400:
            raise StockUnavailable(f"{provider}: HTTP {response.status_code}")
        data = response.json()
        return parse_pexels(data) if provider == "pexels" else parse_pixabay(data)

    def _store(self, entry: Path, query: str, candidate: StockCandidate) -> StockAsset:
        entry.mkdir(parents=True, exist_ok=True)
        video = entry / "video.mp4"
        partial = entry / "video.mp4.part"
        size = 0
        with self._http.stream("GET", candidate.download_url) as response:  # no API key here
            response.raise_for_status()
            with partial.open("wb") as fh:
                for chunk in response.iter_bytes(chunk_size=1 << 16):
                    size += len(chunk)
                    if size > MAX_DOWNLOAD_BYTES:
                        raise StockUnavailable(f"{candidate.provider}: file > {MAX_DOWNLOAD_BYTES} bytes")
                    fh.write(chunk)
        partial.replace(video)
        meta = {"version": CACHE_VERSION, "query": query, "candidate": asdict(candidate)}
        (entry / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), "utf-8")
        logger.info("stock %r → %s:%s (%d bytes)", query, candidate.provider, candidate.provider_id, size)
        return StockAsset(query=query, candidate=candidate, path=video, from_cache=False)

    @staticmethod
    def _load_cache(entry: Path, query: str) -> StockAsset | None:
        meta_path, video = entry / "meta.json", entry / "video.mp4"
        if not (meta_path.is_file() and video.is_file()):
            return None
        try:
            meta = json.loads(meta_path.read_text("utf-8"))
            if meta.get("version") != CACHE_VERSION:
                return None
            candidate = StockCandidate(**meta["candidate"])
        except (ValueError, TypeError, KeyError) as exc:
            logger.warning("ignoring corrupt stock cache %s: %s", entry, exc)
            return None
        return StockAsset(query=query, candidate=candidate, path=video, from_cache=True)


def credit_entry(asset: StockAsset, slide_id: str, index: int) -> dict:
    """One ``credits.json`` row (also what the description generator reads)."""
    c = asset.candidate
    return {
        "slide_id": slide_id,
        "slide_index": index,
        "kind": "stock",
        "query": asset.query,
        "provider": c.provider,
        "provider_id": c.provider_id,
        "source_url": c.page_url,
        "download_url": c.download_url,
        "author": c.author,
        "author_url": c.author_url,
        "license": c.license_name,
        "license_url": c.license_url,
        "resolution": f"{c.width}x{c.height}",
    }
