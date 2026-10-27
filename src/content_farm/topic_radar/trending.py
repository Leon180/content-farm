"""Fast-moving public signals: Hacker News (Algolia search API), Reddit public JSON, Bilibili public ranking.

Terms followed:
- HN Search API (hn.algolia.com/api): public, no key, rate limit 10,000 requests/hour per IP; we send a handful.
- Reddit: read-only public subreddits, descriptive User-Agent, <= 10 requests/minute (spaced 6.5 s).
  Reddit may answer 403/429 to an unauthenticated client; that is reported, never worked around.
- Bilibili: only the public, no-login list endpoints (``ranking/v2`` per zone, ``popular``); no signed or login APIs.
- V2EX: the public JSON API (``/api/topics/hot.json``, ``/api/topics/show.json?node_name=``), no key. Only title, link,
  reply count, time and a short excerpt are kept — never member names or replies.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from urllib.parse import quote

from content_farm.topic_radar import scoring
from content_farm.topic_radar.config import Subreddit
from content_farm.topic_radar.http import RadarHttp, SourceError
from content_farm.topic_radar.models import Signal

FEED_TTL = 3 * 3600
HN_WINDOW_DAYS = 7
HN_MIN_POINTS = 30
BILI_MIN_VIEWS = 100_000
BILI_MAX_AGE_DAYS = 14
EXCERPT_CHARS = 120
# Bilibili answers its API with -352 to a non-browser User-Agent. We keep our honest radar User-Agent and do not
# disguise it: when Bilibili answers -352 that is reported and the source is skipped (Leon decision 2026-10-27).


def matches(text: str, keywords: tuple[str, ...]) -> bool:
    """No keywords = everything passes (a channel that wants the whole feed, e.g. technews)."""
    lowered = text.lower()
    return not keywords or any(word in lowered for word in keywords)


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).replace(microsecond=0).isoformat()


def fetch_hackernews(http: RadarHttp, query: str, now: float | None = None) -> list[Signal]:
    day_start = int((now or time.time()) // 86400 * 86400)     # a stable URL within a day, so the cache can serve re-runs
    since = day_start - HN_WINDOW_DAYS * 86400
    url = (f"https://hn.algolia.com/api/v1/search?query={quote(query)}&tags=story"
           f"&numericFilters=created_at_i%3E{since},points%3E{HN_MIN_POINTS}&hitsPerPage=8")
    reply = http.get_json(url, ttl=FEED_TTL)
    if reply.status != 200 or not isinstance(reply.data, dict):
        raise SourceError(f"hackernews search '{query}': http {reply.status}")
    signals = []
    for hit in reply.data.get("hits", []):
        title = str(hit.get("title") or "").strip()
        if not title:
            continue
        signals.append(Signal(
            source="hackernews", subject=title, lang="en",
            url=f"https://news.ycombinator.com/item?id={hit['objectID']}",
            metrics={"points": float(hit.get("points") or 0), "comments": float(hit.get("num_comments") or 0)},
            published=str(hit.get("created_at") or "")))
    return signals


def fetch_reddit(http: RadarHttp, sub: Subreddit) -> list[Signal]:
    url = f"https://www.reddit.com/r/{quote(sub.name)}/{sub.sort}.json?t=week&limit=15&raw_json=1"
    reply = http.get_json(url, ttl=FEED_TTL)
    if reply.status != 200 or not isinstance(reply.data, dict):
        raise SourceError(f"reddit r/{sub.name}: http {reply.status}")
    signals = []
    for child in reply.data.get("data", {}).get("children", []):
        post = child.get("data", {})
        if post.get("over_18") or not post.get("title"):
            continue
        signals.append(Signal(
            source="reddit", subject=str(post["title"]).strip(), lang="en",
            url=f"https://www.reddit.com{post.get('permalink', '')}",
            metrics={"score": float(post.get("score") or 0), "comments": float(post.get("num_comments") or 0)},
            published=_iso(float(post.get("created_utc") or 0))))
    return signals


def _excerpt(text: object) -> str:
    """A short public summary: whitespace collapsed, cut at EXCERPT_CHARS. Never a full body."""
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= EXCERPT_CHARS else flat[:EXCERPT_CHARS].rstrip() + "…"


def _bilibili_items(http: RadarHttp, url: str, label: str) -> list[dict]:
    """Public, no-login Bilibili list endpoint. ``-352`` is Bilibili's risk control: reported, never worked around."""
    reply = http.get_json(url, ttl=FEED_TTL)
    if reply.status != 200 or not isinstance(reply.data, dict) or reply.data.get("code") != 0:
        code = reply.data.get("code") if isinstance(reply.data, dict) else None
        raise SourceError(f"bilibili {label}: http {reply.status} code {code}")
    data = reply.data.get("data")
    items = data.get("list") if isinstance(data, dict) else None
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _bilibili_signal(item: dict, fetched_at: str) -> Signal | None:
    stat = item.get("stat") or {}
    views = float(stat.get("view") or 0)
    if views < BILI_MIN_VIEWS or not item.get("title"):
        return None
    return Signal(
        source="bilibili", subject=str(item["title"]).strip(), lang="zh-Hans",
        url=f"https://www.bilibili.com/video/{item.get('bvid', '')}",
        metrics={"views": views, "likes": float(stat.get("like") or 0), "comments": float(stat.get("reply") or 0)},
        published=_iso(float(item.get("pubdate") or 0)), excerpt=_excerpt(item.get("desc")), fetched_at=fetched_at)


def _fresh(signal: Signal | None, now: float | None) -> bool:
    if signal is None:
        return False
    if now is None:
        return True
    return scoring.age_days(signal.published, datetime.fromtimestamp(now, tz=timezone.utc)) <= BILI_MAX_AGE_DAYS


def fetch_bilibili(http: RadarHttp, rid: int, now: float | None = None) -> list[Signal]:
    """Zone ranking (``ranking/v2``). Fresh, but Bilibili answers -352 to it intermittently."""
    stamp = _iso(now or time.time())
    items = _bilibili_items(http, f"https://api.bilibili.com/x/web-interface/ranking/v2?rid={rid}&type=all",
                            f"ranking rid={rid}")
    signals = (_bilibili_signal(item, stamp) for item in items)
    return [signal for signal in signals if signal and _fresh(signal, now)]


def fetch_bilibili_popular(http: RadarHttp, zones: tuple[str, ...] = (), now: float | None = None) -> list[Signal]:
    """The public 'popular' list (``popular?ps=50``): fresh and steady, but a general, entertainment-heavy feed,
    so the channel config names the zones (``tname``, simplified Chinese) worth keeping."""
    stamp = _iso(now or time.time())
    items = _bilibili_items(http, "https://api.bilibili.com/x/web-interface/popular?ps=50&pn=1", "popular")
    kept = (item for item in items if not zones or str(item.get("tname") or "") in zones)
    signals = (_bilibili_signal(item, stamp) for item in kept)
    return [signal for signal in signals if signal and _fresh(signal, now)]


def _v2ex_signals(reply_data: object, fetched_at: str) -> list[Signal]:
    if not isinstance(reply_data, list):
        return []
    signals = []
    for topic in reply_data:
        title = str(topic.get("title") or "").strip() if isinstance(topic, dict) else ""
        if not title or not topic.get("url"):
            continue
        signals.append(Signal(
            source="v2ex", subject=title, lang="zh-Hans", url=str(topic["url"]),
            metrics={"replies": float(topic.get("replies") or 0)},
            published=_iso(float(topic.get("created") or 0)), excerpt=_excerpt(topic.get("content")),
            fetched_at=fetched_at))        # member / reply authors are never read
    return signals


def fetch_v2ex(http: RadarHttp, node: str | None = None, now: float | None = None) -> list[Signal]:
    """V2EX public JSON API: ``topics/hot.json`` (node=None) or ``topics/show.json?node_name=<node>``."""
    path = "hot.json" if node is None else f"show.json?node_name={quote(node)}"
    label = "hot" if node is None else f"node {node}"
    reply = http.get_json(f"https://www.v2ex.com/api/topics/{path}", ttl=FEED_TTL)
    if reply.status != 200 or not isinstance(reply.data, list):
        raise SourceError(f"v2ex {label}: http {reply.status}")
    return _v2ex_signals(reply.data, _iso(now or time.time()))
