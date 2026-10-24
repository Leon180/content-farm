"""Fast-moving public signals: Hacker News (Algolia search API), Reddit public JSON, Bilibili public ranking.

Terms followed:
- HN Search API (hn.algolia.com/api): public, no key, rate limit 10,000 requests/hour per IP; we send a handful.
- Reddit: read-only public subreddits, descriptive User-Agent, <= 10 requests/minute (spaced 6.5 s).
  Reddit may answer 403/429 to an unauthenticated client; that is reported, never worked around.
- Bilibili: only the public, no-login ranking endpoint (``x/web-interface/ranking/v2``); no signed or login APIs.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from urllib.parse import quote

from content_farm.topic_radar.config import Subreddit
from content_farm.topic_radar.http import RadarHttp, SourceError
from content_farm.topic_radar.models import Signal

FEED_TTL = 3 * 3600
HN_WINDOW_DAYS = 7
HN_MIN_POINTS = 30
BILI_MIN_VIEWS = 100_000


def matches(text: str, keywords: tuple[str, ...]) -> bool:
    """No keywords = everything passes (a channel that wants the whole feed, e.g. technews)."""
    lowered = text.lower()
    return not keywords or any(word in lowered for word in keywords)


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).replace(microsecond=0).isoformat()


def fetch_hackernews(http: RadarHttp, query: str, now: float | None = None) -> list[Signal]:
    since = int((now or time.time()) - HN_WINDOW_DAYS * 86400)
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


def fetch_bilibili(http: RadarHttp, rid: int) -> list[Signal]:
    url = f"https://api.bilibili.com/x/web-interface/ranking/v2?rid={rid}&type=all"
    reply = http.get_json(url, ttl=FEED_TTL)
    if reply.status != 200 or not isinstance(reply.data, dict) or reply.data.get("code") != 0:
        code = reply.data.get("code") if isinstance(reply.data, dict) else None
        raise SourceError(f"bilibili ranking rid={rid}: http {reply.status} code {code}")
    signals = []
    for item in reply.data.get("data", {}).get("list", []):
        stat = item.get("stat", {})
        views = float(stat.get("view") or 0)
        if views < BILI_MIN_VIEWS or not item.get("title"):
            continue
        signals.append(Signal(
            source="bilibili", subject=str(item["title"]).strip(), lang="zh-Hans",
            url=f"https://www.bilibili.com/video/{item.get('bvid', '')}",
            metrics={"views": views, "likes": float(stat.get("like") or 0), "comments": float(stat.get("reply") or 0)},
            published=_iso(float(item.get("pubdate") or 0))))
    return signals
