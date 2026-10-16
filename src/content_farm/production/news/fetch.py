"""Free sources: HN official API, Lobsters RSS, arXiv API — with polite spacing.

Rates (REPORT-hn-daily §來源與速率):
- HN Firebase API states "no rate limit"; we still space requests 0.1 s.
- Lobsters: one RSS request per run (1 s spacing if more are added).
- arXiv: "no more than one request every three seconds … a single connection";
  titles/abstracts only — no PDF is downloaded or stored.
- Any other host (original articles, ``verify``): 1 s spacing per host.
X/Twitter is never fetched (not a source; ``BLOCKED_DOMAINS``).
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx

from content_farm.production.news.models import Candidate, Discussion

USER_AGENT = "content-farm-news/0.1 (+https://github.com/Leon180/content-farm; editorial fact-check)"
HN_API = "https://hacker-news.firebaseio.com/v0"
HN_ITEM = "https://news.ycombinator.com/item?id={id}"
LOBSTERS_RSS = "https://lobste.rs/rss"
ARXIV_API = "https://export.arxiv.org/api/query"
ARXIV_CATEGORIES = ("cs.AR", "cs.AI", "cs.CL", "cs.LG", "cs.CR", "cs.ET")
HOST_SPACING = {"hacker-news.firebaseio.com": 0.1, "export.arxiv.org": 3.0, "lobste.rs": 1.0}
DEFAULT_SPACING = 1.0
TIMEOUT = 15.0
MAX_BYTES = 3 * 1024 * 1024
BLOCKED_DOMAINS = ("x.com", "twitter.com", "t.co", "nitter.net")

_ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class Response:
    url: str            # final URL after redirects
    status: int
    content_type: str
    body: bytes


Getter = Callable[[str], Response]


@dataclass
class PoliteHttp:
    """Sequential GETs with per-host minimum spacing and a size cap."""

    spacing: dict[str, float] = field(default_factory=lambda: dict(HOST_SPACING))
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    _last: dict[str, float] = field(default_factory=dict)
    _client: httpx.Client | None = None

    def _wait(self, host: str) -> None:
        gap = self.spacing.get(host, DEFAULT_SPACING)
        last = self._last.get(host)
        if last is not None:
            remaining = gap - (self.clock() - last)
            if remaining > 0:
                self.sleep(remaining)
        self._last[host] = self.clock()

    def get(self, url: str) -> Response:
        host = urlsplit(url).hostname or ""
        if is_blocked(url):
            raise FetchError(f"{host} is not a source (X/Twitter is never fetched)")
        self._wait(host)
        if self._client is None:
            self._client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT,
                                        follow_redirects=True)
        try:
            with self._client.stream("GET", url) as resp:
                chunks, size = [], 0
                for chunk in resp.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        break
                    chunks.append(chunk)
                return Response(str(resp.url), resp.status_code,
                                resp.headers.get("content-type", ""), b"".join(chunks))
        except httpx.HTTPError as exc:
            raise FetchError(f"GET {url}: {type(exc).__name__}: {exc}") from exc

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


def is_blocked(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in BLOCKED_DOMAINS)


def domain_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.")


def _iso(ts: datetime) -> str:
    if ts.tzinfo is None:   # RFC 2822 "-0000" parses naive; it means UTC, not this machine's zone
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _json(get: Getter, url: str) -> object:
    import json

    resp = get(url)
    if resp.status != 200:
        raise FetchError(f"GET {url}: http {resp.status}")
    return json.loads(resp.body)


# ── Hacker News ──────────────────────────────────────────────────────────────

def hn_item_candidate(item: dict, rank: int) -> Candidate | None:
    """A story with an external URL; Ask/Show-text posts without a link can't be verified."""
    if item.get("type") != "story" or item.get("dead") or item.get("deleted"):
        return None
    url = item.get("url")
    if not url or is_blocked(url):
        return None
    hn_url = HN_ITEM.format(id=item["id"])
    return Candidate(
        id=f"hn-{item['id']}", title=str(item.get("title", "")).strip()[:300] or "(no title)",
        url=url, domain=domain_of(url),
        posted_at=_iso(datetime.fromtimestamp(int(item["time"]), timezone.utc)),
        discussions=(Discussion(site="hn", url=hn_url, points=int(item.get("score") or 0),
                                comments=int(item.get("descendants") or 0), rank=rank),),
    )


def fetch_hn(get: Getter, top: int = 60, best: int = 30) -> list[Candidate]:
    ids: dict[int, int] = {}
    for listing, limit in (("topstories", top), ("beststories", best)):
        for position, item_id in enumerate(_json(get, f"{HN_API}/{listing}.json")[:limit], start=1):
            ids.setdefault(int(item_id), position)
    out = []
    for item_id, position in ids.items():
        item = _json(get, f"{HN_API}/item/{item_id}.json")
        candidate = hn_item_candidate(item, position) if isinstance(item, dict) else None
        if candidate:
            out.append(candidate)
    return out


# ── Lobsters (RSS) ───────────────────────────────────────────────────────────

def parse_lobsters_rss(body: bytes) -> list[Candidate]:
    root = ET.fromstring(body)
    out = []
    for rank, item in enumerate(root.iter("item"), start=1):
        link = (item.findtext("link") or "").strip()
        comments = (item.findtext("comments") or "").strip()
        guid = (item.findtext("guid") or comments or link).rstrip("/").rsplit("/", 1)[-1]
        pub = item.findtext("pubDate")
        if not link or not pub or is_blocked(link):
            continue
        out.append(Candidate(
            id=f"lob-{guid}"[:40], title=(item.findtext("title") or "").strip()[:300] or "(no title)",
            url=link, domain=domain_of(link), posted_at=_iso(parsedate_to_datetime(pub)),
            discussions=(Discussion(site="lobsters", url=comments or link, rank=rank),),
            tags=tuple(c.text.strip() for c in item.findall("category") if c.text),
        ))
    return out


def fetch_lobsters(get: Getter) -> list[Candidate]:
    resp = get(LOBSTERS_RSS)
    if resp.status != 200:
        raise FetchError(f"GET {LOBSTERS_RSS}: http {resp.status}")
    return parse_lobsters_rss(resp.body)


# ── arXiv (API, abstracts only) ──────────────────────────────────────────────

def arxiv_query_url(categories: Iterable[str] = ARXIV_CATEGORIES, limit: int = 40) -> str:
    query = "+OR+".join(f"cat:{c}" for c in categories)
    return (f"{ARXIV_API}?search_query={query}&sortBy=submittedDate&sortOrder=descending"
            f"&start=0&max_results={limit}")


def arxiv_abs_id(url: str) -> str | None:
    """'2610.01234' from https://arxiv.org/abs/2610.01234v2 or /pdf/…; None otherwise."""
    parts = urlsplit(url)
    if domain_of(url) not in ("arxiv.org", "export.arxiv.org"):
        return None
    path = parts.path.strip("/").split("/")
    if len(path) < 2 or path[0] not in ("abs", "pdf", "html"):
        return None
    ident = path[1].removesuffix(".pdf")
    return ident.split("v")[0] if ident[:4].isdigit() else ident


def parse_arxiv_atom(body: bytes) -> list[Candidate]:
    root = ET.fromstring(body)
    out = []
    for rank, entry in enumerate(root.findall("a:entry", _ATOM), start=1):
        abs_url = (entry.findtext("a:id", default="", namespaces=_ATOM) or "").strip()
        ident = arxiv_abs_id(abs_url)
        published = entry.findtext("a:published", default="", namespaces=_ATOM)
        if not ident or not published:
            continue
        title = " ".join((entry.findtext("a:title", default="", namespaces=_ATOM) or "").split())
        summary = " ".join((entry.findtext("a:summary", default="", namespaces=_ATOM) or "").split())
        cats = tuple(c.get("term", "") for c in entry.findall("a:category", _ATOM) if c.get("term"))
        url = f"https://arxiv.org/abs/{ident}"
        out.append(Candidate(
            id=f"arxiv-{ident}"[:40], title=title[:300] or "(no title)", url=url, domain="arxiv.org",
            posted_at=_iso(datetime.fromisoformat(published.replace("Z", "+00:00"))),
            discussions=(Discussion(site="arxiv", url=url, rank=rank),), tags=cats, summary=summary,
        ))
    return out


def fetch_arxiv(get: Getter, limit: int = 40) -> list[Candidate]:
    resp = get(arxiv_query_url(limit=limit))
    if resp.status != 200:
        raise FetchError(f"arXiv API: http {resp.status}")
    return parse_arxiv_atom(resp.body)


def fetch_arxiv_abstract(get: Getter, ident: str) -> Candidate | None:
    resp = get(f"{ARXIV_API}?id_list={ident}")
    if resp.status != 200:
        raise FetchError(f"arXiv API id_list={ident}: http {resp.status}")
    found = parse_arxiv_atom(resp.body)
    return found[0] if found else None


@dataclass(frozen=True)
class FetchReport:
    candidates: tuple[Candidate, ...]
    errors: tuple[str, ...]            # one line per failed source; the others still count
    counts: dict[str, int]


def fetch_all(get: Getter) -> FetchReport:
    """Every source; one failing source is reported, not fatal."""
    found: list[Candidate] = []
    errors: list[str] = []
    counts: dict[str, int] = {}
    for name, fn in (("hn", fetch_hn), ("lobsters", fetch_lobsters), ("arxiv", fetch_arxiv)):
        try:
            items = fn(get)
        except (FetchError, ET.ParseError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"{name}: {exc}")
            items = []
        counts[name] = len(items)
        found.extend(items)
    return FetchReport(tuple(found), tuple(errors), counts)
