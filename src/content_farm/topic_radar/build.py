"""Turn one channel's radar config + live signals into ranked candidates with evidence."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from content_farm.topic_radar import scoring, trending, wikipedia
from content_farm.topic_radar.config import RadarConfig, Topic, Watch
from content_farm.topic_radar.http import RadarHttp, SourceError
from content_farm.topic_radar.models import (
    Candidate, ChannelRadar, Competitor, Evidence, Signal, SourceName, SourceStatus, ViewerQuestion, VideoFormat,
)
from content_farm.topic_radar.youtube import YouTubeClient, median_views

logger = logging.getLogger(__name__)

YT_TOPICS_PER_CHANNEL = 10      # every seed topic: search results are cached 7 days, so a steady day costs ~1/7 of a first run
TRENDING_PER_CHANNEL = 4
YOUTUBE_RETENTION_DAYS = 30
HOST_SOURCE: dict[str, SourceName] = {
    "wikimedia.org": "wikipedia", "zh.wikipedia.org": "wikipedia", "en.wikipedia.org": "wikipedia",
    "ja.wikipedia.org": "wikipedia", "www.googleapis.com": "youtube", "oauth2.googleapis.com": "youtube",
    "hn.algolia.com": "hackernews", "www.reddit.com": "reddit", "api.bilibili.com": "bilibili", "www.v2ex.com": "v2ex",
}
SOURCE_ORDER: tuple[SourceName, ...] = ("youtube", "wikipedia", "hackernews", "reddit", "bilibili", "v2ex")
REFUSALS = ("http 403", "http 429", "code -352")      # a source that refuses us is not asked again this run
CN_SOURCES = ("bilibili", "v2ex")
CN_SIGNAL_NOTE = "中文網路熱度只是選題信號，不是題目本身；題目與切角要另行確立並查證"
LANG_NAME = {"zh": "中文維基", "en": "英文維基", "ja": "日文維基"}


@dataclass
class Notes:
    """Failures per source, collected instead of raised: one dead source must not blank a channel's file."""

    errors: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    def add(self, source: SourceName, message: str) -> None:
        if message not in self.errors[source]:
            self.errors[source].append(message)


def _title_for(config: RadarConfig, topic: Topic) -> str:
    return topic.title or config.title_template.format(subject=topic.subject)


def _wiki_evidence(views: list[wikipedia.WikiViews]) -> list[Evidence]:
    return [Evidence(source="wikipedia", metric=f"{LANG_NAME[item.lang]}「{item.title}」近 30 日瀏覽量", value=item.total_30d,
                     url=item.url, note=f"近 7 日日均 {item.recent_daily:g}，前 23 日日均 {item.earlier_daily:g}，升溫 ×{item.growth:g}")
            for item in views]


def _youtube_evidence(query: str, videos: list[Competitor], median: float) -> list[Evidence]:
    if not videos:
        return []
    top = videos[0]
    return [Evidence(source="youtube", metric=f"YouTube 搜尋「{query}」前 {len(videos)} 名影片觀看數中位數", value=median,
                     url=top.url, note=f"最高：{top.views:,} 次（{top.channel}，{top.published}）")]


def _pick_format(config: RadarConfig, kind: str, growth: float) -> tuple[VideoFormat, str]:
    if not config.shorts_supported:
        return "long", "此頻道只做長片"
    if kind == "trending":
        return "shorts", "時效題：熱度通常一週內消退，用 Shorts 趕時效"
    if growth >= 1.5:
        return "shorts", f"近 7 日瀏覽量是前 23 日的 {growth} 倍，先用 Shorts 試水再決定是否做長片"
    return "long", "長青題材，資料量撐得起 7–10 分鐘長片"


def _best_wiki(views: list[wikipedia.WikiViews]) -> wikipedia.WikiViews | None:
    return max(views, key=lambda item: item.total_30d, default=None)


def _topic_views(http: RadarHttp, topic: Topic, today: date, notes: Notes) -> list[wikipedia.WikiViews]:
    found = []
    for entry in topic.wiki:
        try:
            item = wikipedia.fetch_views(http, entry, today)
        except SourceError as exc:
            notes.add("wikipedia", str(exc))
            continue
        if item is None:
            notes.add("wikipedia", f"{entry.lang}:{entry.title} 不存在或沒有瀏覽資料")
        else:
            found.append(item)
    return found


def _enrich(youtube: YouTubeClient | None, topic: Topic, today: date, notes: Notes
            ) -> tuple[list[Competitor], list[ViewerQuestion], float]:
    if youtube is None or not topic.youtube_query:
        return [], [], 0.0
    try:
        videos = youtube.competitors(topic.youtube_query)
        questions: list[ViewerQuestion] = []
        for video in videos[:2]:
            questions.extend(youtube.viewer_questions(video))
    except SourceError as exc:
        notes.add("youtube", str(exc))
        return [], [], 0.0
    questions.sort(key=lambda item: -item.likes)
    return videos, questions[:6], median_views(videos)


def _evergreen(config: RadarConfig, http: RadarHttp, youtube: YouTubeClient | None, today: date,
               notes: Notes) -> list[dict]:
    pre = []
    for topic in config.topics:
        views = _topic_views(http, topic, today, notes)
        best = _best_wiki(views)
        pre.append((wikipedia_score(best), topic, views, best))
    pre.sort(key=lambda row: -row[0])
    rows = []
    for rank, (wiki_points, topic, views, best) in enumerate(pre):
        videos, questions, median = (_enrich(youtube, topic, today, notes) if rank < YT_TOPICS_PER_CHANNEL
                                     else ([], [], 0.0))
        score = wiki_points + (scoring.youtube_score(median, videos, today) if videos else 0.0)
        rows.append({"topic": topic, "views": views, "best": best, "videos": videos, "questions": questions,
                     "median": median, "score": score})
    return rows


def wikipedia_score(best: wikipedia.WikiViews | None) -> float:
    return scoring.wiki_score(best.total_30d, best.growth) if best else 0.0


def _evergreen_candidates(config: RadarConfig, rows: list[dict]) -> list[Candidate]:
    out = []
    for row in rows:
        topic: Topic = row["topic"]
        growth = row["best"].growth if row["best"] else 1.0
        fmt, why = _pick_format(config, "evergreen", growth)
        evidence = _wiki_evidence(row["views"]) + _youtube_evidence(topic.youtube_query, row["videos"], row["median"])
        warnings = [] if evidence else ["沒有取得任何需求數字（來源失敗或條目不存在）"]
        out.append(Candidate(id="", kind="evergreen", subject=topic.subject, title_draft=_title_for(config, topic),
                             format=fmt, format_reason=why, score=round(row["score"], 1), evidence=tuple(evidence),
                             competitors=tuple(row["videos"][:5]), viewer_questions=tuple(row["questions"]),
                             warnings=tuple(warnings)))
    return out


def _trending_jobs(watch: Watch, http: RadarHttp, now: datetime) -> list[tuple[str, str, str, Callable[[], list[Signal]]]]:
    """(source, endpoint, label, run). Bilibili's two endpoints are separate so a -352 on one does not silence the other."""
    stamp = now.timestamp()
    jobs = [("hackernews", "search", query, lambda q=query: trending.fetch_hackernews(http, q, stamp))
            for query in watch.hackernews_queries]
    jobs += [("reddit", "top", sub.name, lambda s=sub: trending.fetch_reddit(http, s)) for sub in watch.subreddits]
    jobs += [("bilibili", "ranking", str(rid), lambda r=rid: trending.fetch_bilibili(http, r, stamp))
             for rid in watch.bilibili_rids]
    if watch.bilibili_popular:
        jobs.append(("bilibili", "popular", "popular",
                     lambda: trending.fetch_bilibili_popular(http, watch.bilibili_popular_zones, stamp)))
    if watch.v2ex_hot:
        jobs.append(("v2ex", "hot", "hot", lambda: trending.fetch_v2ex(http, None, stamp)))
    jobs += [("v2ex", "node", node, lambda n=node: trending.fetch_v2ex(http, n, stamp)) for node in watch.v2ex_nodes]
    return jobs


def fetch_trending_signals(watch: Watch, http: RadarHttp, notes: Notes, now: datetime) -> list[Signal]:
    """Every source in ``watch``; a failure is recorded in ``notes`` and the rest carry on."""
    found, dead = [], set()
    for source, endpoint, label, run in _trending_jobs(watch, http, now):
        if (source, endpoint) in dead:
            continue
        try:
            found.extend(item for item in run() if trending.matches(f"{item.subject} {item.excerpt}", watch.keywords))
        except SourceError as exc:
            notes.add(source, str(exc))
            if any(mark in str(exc) for mark in REFUSALS):
                dead.add((source, endpoint))
    return list({item.url: item for item in found}.values())


def _trending_signals(config: RadarConfig, http: RadarHttp, notes: Notes, now: datetime) -> list[Signal]:
    return fetch_trending_signals(config.watch, http, notes, now)


def _signal_candidate(config: RadarConfig, item: Signal, points: float) -> Candidate:
    fmt, why = _pick_format(config, "trending", 1.0)
    metric, _ = scoring.TREND_REFERENCE[item.source]
    evidence = Evidence(source=item.source, metric=f"{item.source} {metric}", value=item.metrics.get(metric, 0.0),
                        url=item.url, note="；".join(f"{k} {v:,.0f}" for k, v in item.metrics.items()),
                        fetched_at=item.fetched_at)
    draft = item.subject if item.lang.startswith("zh") else f"{item.subject}（原題，待譯）"
    warnings = []
    if item.lang == "zh-Hans":
        warnings.append("簡體中文原題，選題階段需改寫成繁中標題與台灣語境")
    elif not item.lang.startswith("zh"):
        warnings.append("原題為外文，選題階段需改寫成繁中標題")
    if item.source in CN_SOURCES:
        warnings.append(CN_SIGNAL_NOTE)
    return Candidate(id="", kind="trending", subject=item.subject, title_draft=draft, format=fmt, format_reason=why,
                     score=round(points + config.trending_bonus, 1), evidence=(evidence,), warnings=tuple(warnings),
                     excerpt=item.excerpt)


def signal_candidates(config: RadarConfig, signals: list[Signal], now: datetime, limit: int) -> list[Candidate]:
    scored = sorted(((scoring.trending_score(item, now), item) for item in signals), key=lambda row: -row[0])
    return [_signal_candidate(config, item, points) for points, item in scored[:limit]]


def _trending_candidates(config: RadarConfig, signals: list[Signal], now: datetime) -> list[Candidate]:
    return signal_candidates(config, signals, now, TRENDING_PER_CHANNEL)


def _status(http: RadarHttp, before: dict, youtube: YouTubeClient | None, units_before: int,
            notes: Notes) -> tuple[SourceStatus, ...]:
    net, hit = defaultdict(int), defaultdict(int)
    for host, count in http.network.items():
        net[HOST_SOURCE.get(host, "wikipedia")] += count - before["net"].get(host, 0)
    for host, count in http.cached.items():
        hit[HOST_SOURCE.get(host, "wikipedia")] += count - before["hit"].get(host, 0)
    rows = []
    for source in SOURCE_ORDER:
        errors = notes.errors.get(source, [])
        units = (youtube.units - units_before) if (source == "youtube" and youtube) else 0
        rows.append(SourceStatus(source=source, ok=not errors, requests=net[source], cache_hits=hit[source],
                                 units=units, note=" | ".join(errors[:3])))
    return tuple(rows)


def status_rows(http: RadarHttp, before: dict, notes: Notes) -> tuple[SourceStatus, ...]:
    return _status(http, before, None, 0, notes)


def build_channel(config: RadarConfig, http: RadarHttp, youtube: YouTubeClient | None, now: datetime,
                  notes: Notes | None = None) -> ChannelRadar:
    notes = notes or Notes()
    today = now.date()
    before = {"net": dict(http.network), "hit": dict(http.cached)}
    units_before = youtube.units if youtube else 0
    candidates = _evergreen_candidates(config, _evergreen(config, http, youtube, today, notes))
    candidates += _trending_candidates(config, _trending_signals(config, http, notes, now), now)
    ranked = sorted(candidates, key=lambda item: -item.score)
    numbered = tuple(item.model_copy(update={"id": f"{config.channel}-{today:%Y%m%d}-{n:02d}"})
                     for n, item in enumerate(ranked, 1))
    expires = (now + timedelta(days=YOUTUBE_RETENTION_DAYS)).astimezone(timezone.utc)
    return ChannelRadar(channel=config.channel, date=today.isoformat(),
                        generated_at=now.astimezone(timezone.utc).replace(microsecond=0).isoformat(),
                        youtube_data_expires=expires.replace(microsecond=0).isoformat(), candidates=numbered,
                        sources=_status(http, before, youtube, units_before, notes))
