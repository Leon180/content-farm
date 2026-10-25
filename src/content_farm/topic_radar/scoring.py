"""Transparent 0–100 hint score. It orders the list; it is not a threshold (the topic panel decides).

evergreen (seed topics)
  wiki demand   0–35   35 * log10(best 30-day views) / 5          (100k views in 30 days = full marks)
  wiki growth   0–15   15 * (recent/earlier daily mean - 1)        (2x faster than the month before = full marks)
  yt demand     0–30   30 * log10(median views of top-5 videos) / 6.5   (~3M = full marks)
  yt gap        0–10   +10 when demand is proven (median >= 100k) but <= 1 of the top 5 is under a year old
trending (HN / Reddit / Bilibili items)
  strength      0–50   50 * log10(metric) / log10(reference)       (HN 1000 points, Reddit 20000, Bilibili 2M views)
  freshness     0–10   +10 when younger than 2 days
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone

from content_farm.topic_radar.models import Competitor, Signal

TREND_REFERENCE = {"hackernews": ("points", 1_000), "reddit": ("score", 20_000), "bilibili": ("views", 2_000_000)}


def _log_ratio(value: float, full: float) -> float:
    return min(1.0, math.log10(value) / full) if value > 1 else 0.0


def wiki_score(best_total_30d: int, growth: float) -> float:
    return 35 * _log_ratio(best_total_30d, 5) + 15 * min(1.0, max(0.0, growth - 1.0))


def youtube_score(median_views: float, competitors: list[Competitor], today: date) -> float:
    demand = 30 * _log_ratio(median_views, 6.5)
    recent = sum(1 for c in competitors if (today - date.fromisoformat(c.published)).days <= 365)
    gap = 10.0 if median_views >= 100_000 and recent <= 1 else 0.0
    return demand + gap


def trending_score(signal: Signal, now: datetime) -> float:
    metric, reference = TREND_REFERENCE[signal.source]
    strength = 50 * _log_ratio(signal.metrics.get(metric, 0.0), math.log10(reference))
    return strength + (10.0 if _age_days(signal.published, now) <= 2 else 0.0)


def _age_days(published: str, now: datetime) -> float:
    try:
        stamp = datetime.fromisoformat(published.replace("Z", "+00:00"))
    except ValueError:
        return 999.0
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (now - stamp).total_seconds() / 86400
