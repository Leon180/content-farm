"""Wikimedia Pageviews API (https://wikimedia.org/api/rest_v1) + MediaWiki title resolution.

Terms: Wikimedia asks for a descriptive User-Agent with contact and well under 200 req/s; data is CC0.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from urllib.parse import quote

from content_farm.topic_radar.config import WikiEntry
from content_farm.topic_radar.http import RadarHttp, SourceError

TITLE_TTL = 7 * 86400
VIEWS_TTL = 12 * 3600
WINDOW_DAYS = 30
RECENT_DAYS = 7


@dataclass(frozen=True)
class WikiViews:
    lang: str
    title: str
    url: str
    total_30d: int
    recent_daily: float      # mean of the last 7 days
    earlier_daily: float     # mean of the 23 days before that
    growth: float            # recent_daily / earlier_daily (1.0 = flat)


def resolve_title(http: RadarHttp, entry: WikiEntry) -> str | None:
    """Canonical article title after redirects and zh variant conversion; None when the page does not exist."""
    url = (f"https://{entry.lang}.wikipedia.org/w/api.php?action=query&titles={quote(entry.title)}"
           "&redirects=1&converttitles=1&format=json&formatversion=2")
    reply = http.get_json(url, ttl=TITLE_TTL)
    if reply.status != 200 or not isinstance(reply.data, dict):
        raise SourceError(f"{entry.lang}.wikipedia title lookup: http {reply.status}")
    pages = reply.data.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing") or pages[0].get("invalid"):
        return None
    return str(pages[0]["title"])


def _views_url(lang: str, title: str, start: date, end: date) -> str:
    article = quote(title.replace(" ", "_"), safe="")
    return ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
            f"{lang}.wikipedia/all-access/user/{article}/daily/{start:%Y%m%d}/{end:%Y%m%d}")


def fetch_views(http: RadarHttp, entry: WikiEntry, today: date) -> WikiViews | None:
    """30-day views and recent growth for one article; None when the article is missing or has no data."""
    title = resolve_title(http, entry)
    if title is None:
        return None
    end = today - timedelta(days=1)                       # the API lags about a day
    start = end - timedelta(days=WINDOW_DAYS - 1)
    reply = http.get_json(_views_url(entry.lang, title, start, end), ttl=VIEWS_TTL)
    if reply.status == 404:
        return None                                       # no views recorded in the window
    if reply.status != 200 or not isinstance(reply.data, dict):
        raise SourceError(f"{entry.lang}.wikipedia pageviews '{title}': http {reply.status}")
    days = [int(item["views"]) for item in reply.data.get("items", [])]
    if len(days) < RECENT_DAYS + 7:
        return None
    recent, earlier = days[-RECENT_DAYS:], days[:-RECENT_DAYS]
    recent_daily, earlier_daily = sum(recent) / len(recent), sum(earlier) / len(earlier)
    growth = recent_daily / earlier_daily if earlier_daily > 0 else 1.0
    page = f"https://{entry.lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
    return WikiViews(entry.lang, title, page, sum(days), round(recent_daily, 1), round(earlier_daily, 1),
                     round(growth, 2))
