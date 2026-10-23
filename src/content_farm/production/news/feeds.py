"""Whitelisted RSS / Atom feeds (entertainment news): the only door a story can come through.

Every feed is declared in the channel yaml (``series.news.feeds``) with the hosts its articles live on.
An entry whose link points anywhere else is dropped here — not later, not by a prompt — and counted in the
fetch report, so a feed that starts redirecting to an aggregator shows up as ``off_list`` instead of leaking
unvetted stories in. One request per feed per run, spaced by the host's own gap (``PoliteHttp``).
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape

from content_farm.production.news import fetch, guard
from content_farm.production.news.models import Candidate, Discussion
from content_farm.production.news.series import Feed

_ATOM = "{http://www.w3.org/2005/Atom}"
_ORIG_LINK = "{http://rssnamespace.org/feedburner/ext/1.0}origLink"
_DC_DATE = "{http://purl.org/dc/elements/1.1/}date"
_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class FeedResult:
    feed: Feed
    candidates: tuple[Candidate, ...]
    off_list: int           # entries dropped because their link is not on the feed's declared hosts


def plain(text: str | None, limit: int = 400) -> str:
    return " ".join(unescape(_TAG.sub(" ", text or "")).split())[:limit]


def _when(entry: ET.Element) -> str | None:
    for tag in ("pubDate", _DC_DATE, f"{_ATOM}published", f"{_ATOM}updated", "published", "updated"):
        raw = (entry.findtext(tag) or "").strip()
        if not raw:
            continue
        try:
            stamp = parsedate_to_datetime(raw) if not raw[:4].isdigit() else datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        return fetch._iso(stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc))
    return None


def _link(entry: ET.Element) -> str:
    orig = (entry.findtext(_ORIG_LINK) or "").strip()
    if orig:
        return orig
    link = entry.find("link")
    if link is None:
        link = entry.find(f"{_ATOM}link")
    if link is None:
        return ""
    return (link.get("href") or link.text or "").strip()


def candidate_id(feed: Feed, link: str) -> str:
    return f"{feed.id}-{hashlib.sha1(link.encode()).hexdigest()[:10]}"[:40]


def parse_feed(body: bytes, feed: Feed) -> FeedResult:
    root = ET.fromstring(body)
    entries = list(root.iter("item")) or list(root.iter(f"{_ATOM}entry"))
    out, off_list = [], 0
    for rank, entry in enumerate(entries, start=1):
        link = _link(entry)
        title = plain(entry.findtext("title") or entry.findtext(f"{_ATOM}title"), 300)
        posted = _when(entry)
        if not link or not title or not posted or fetch.is_blocked(link):
            continue
        if not guard.host_matches(link, feed.domains):
            off_list += 1
            continue
        summary = plain(entry.findtext("description") or entry.findtext(f"{_ATOM}summary")
                        or entry.findtext(f"{_ATOM}content"))
        out.append(Candidate(
            id=candidate_id(feed, link), title=title, url=link, domain=guard.host_of(link), posted_at=posted,
            discussions=(Discussion(site="rss", url=feed.url, rank=rank),),
            tags=tuple(c.text.strip() for c in entry.findall("category") if c.text), summary=summary,
            publisher=feed.name))
    return FeedResult(feed, tuple(out), off_list)


def fetch_feed(get: fetch.Getter, feed: Feed) -> FeedResult:
    resp = get(feed.url)
    if resp.status != 200:
        raise fetch.FetchError(f"{feed.id}: GET {feed.url}: http {resp.status}")
    try:
        return parse_feed(resp.body, feed)
    except ET.ParseError as exc:
        raise fetch.FetchError(f"{feed.id}: not a feed ({exc})") from exc


def fetch_feeds(get: fetch.Getter, feeds: Sequence[Feed]) -> tuple[list[Candidate], list[str], dict[str, int]]:
    """(candidates, one error line per failed feed, {feed id: kept entries}); one dead feed never stops the others."""
    found: list[Candidate] = []
    errors: list[str] = []
    counts: dict[str, int] = {}
    for feed in feeds:
        try:
            result = fetch_feed(get, feed)
        except fetch.FetchError as exc:
            errors.append(str(exc))
            counts[feed.id] = 0
            continue
        counts[feed.id] = len(result.candidates)
        if result.off_list:
            errors.append(f"{feed.id}: {result.off_list} entries linked outside {', '.join(feed.domains)}; dropped")
        found.extend(result.candidates)
    return found, errors, counts
