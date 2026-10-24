"""Topic radar: config, sources (against canned answers), auth fallback, scoring, build, store, summary, brief."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from content_farm.topic_radar import brief, scoring, store, trending, wikipedia
from content_farm.topic_radar.build import Notes, build_channel
from content_farm.topic_radar.config import CHANNEL_CODES, RadarConfig, Subreddit, WikiEntry, load_radar_config
from content_farm.topic_radar.http import RadarHttp, Reply, SourceError, scrub
from content_farm.topic_radar.models import Competitor
from content_farm.topic_radar.summary import render_summary
from content_farm.topic_radar.youtube import (
    QuotaBudgetExceeded, YouTubeAuth, YouTubeClient, build_auth, extract_questions,
)

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
TODAY = NOW.date()


class FakeHttp(RadarHttp):
    """Answers by longest matching URL fragment; records every URL asked."""

    def __init__(self, routes: dict[str, tuple[int, object]] | None = None, post: tuple[int, object] = (200, {})):
        super().__init__(cache_dir=None)
        self.routes, self.post, self.asked, self.warm = routes or {}, post, [], set()

    def is_cached(self, url: str, ttl: float | None = None) -> bool:
        return url in self.warm

    def get_json(self, url, *, headers=None, ttl=None):
        self.asked.append(url)
        host = url.split("/")[2]
        self.network[host] += 1
        for fragment in sorted(self.routes, key=len, reverse=True):
            if fragment in url:
                return Reply(*self.routes[fragment])
        return Reply(404, None)

    def post_form(self, url, form):
        self.network["oauth2.googleapis.com"] += 1
        return Reply(*self.post)


def days(values: list[int]) -> dict:
    return {"items": [{"views": v} for v in values]}


def wiki_routes() -> dict:
    return {
        "api.php?action=query": (200, {"query": {"pages": [{"title": "台積電"}]}}),
        "pageviews/per-article": (200, days([100] * 23 + [300] * 7)),
    }


# ── config ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", CHANNEL_CODES)
def test_every_shipped_radar_config_loads(code):
    config = load_radar_config(code)
    assert config.channel == code and len(config.topics) >= 6
    assert all(t.youtube_query for t in config.topics)


def test_config_rejects_template_without_subject():
    with pytest.raises(ValueError):
        RadarConfig(channel="x", title_template="no placeholder", topics=())


def test_config_rejects_unknown_key(tmp_path):
    (tmp_path / "x.yaml").write_text("channel: x\ntopics: []\nbogus: 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_radar_config("x", tmp_path)


def test_config_channel_must_match_filename(tmp_path):
    (tmp_path / "x.yaml").write_text("channel: y\ntopics: []\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_radar_config("x", tmp_path)


# ── wikipedia ───────────────────────────────────────────────────────────────────

def test_wiki_views_growth_and_totals():
    got = wikipedia.fetch_views(FakeHttp(wiki_routes()), WikiEntry(lang="zh", title="台積電"), TODAY)
    assert got.total_30d == 100 * 23 + 300 * 7
    assert got.recent_daily == 300 and got.earlier_daily == 100 and got.growth == 3.0
    assert got.url == "https://zh.wikipedia.org/wiki/%E5%8F%B0%E7%A9%8D%E9%9B%BB"


def test_wiki_missing_page_is_none_not_error():
    routes = {"api.php?action=query": (200, {"query": {"pages": [{"title": "x", "missing": True}]}})}
    assert wikipedia.fetch_views(FakeHttp(routes), WikiEntry(lang="en", title="x"), TODAY) is None


def test_wiki_http_error_raises_source_error():
    with pytest.raises(SourceError):
        wikipedia.fetch_views(FakeHttp({"api.php": (500, None)}), WikiEntry(lang="en", title="x"), TODAY)


def test_wiki_too_few_days_is_none():
    routes = {**wiki_routes(), "pageviews/per-article": (200, days([5, 5, 5]))}
    assert wikipedia.fetch_views(FakeHttp(routes), WikiEntry(lang="zh", title="台積電"), TODAY) is None


# ── trending sources ────────────────────────────────────────────────────────────

def test_hackernews_hits_become_signals_with_item_url():
    hits = {"hits": [{"objectID": "42", "title": "Deep sea find", "points": 300, "num_comments": 90,
                      "created_at": "2026-10-23T10:00:00Z"}, {"objectID": "43", "title": ""}]}
    got = trending.fetch_hackernews(FakeHttp({"hn.algolia.com": (200, hits)}), "deep sea", NOW.timestamp())
    assert [s.subject for s in got] == ["Deep sea find"]
    assert got[0].url == "https://news.ycombinator.com/item?id=42" and got[0].metrics["points"] == 300


def test_reddit_skips_nsfw_and_reports_block():
    body = {"data": {"children": [{"data": {"title": "ok", "score": 5, "num_comments": 1, "permalink": "/r/a/1",
                                            "created_utc": 1_760_000_000}},
                                  {"data": {"title": "no", "over_18": True}}]}}
    assert [s.subject for s in trending.fetch_reddit(FakeHttp({"reddit.com": (200, body)}), Subreddit(name="a"))] == ["ok"]
    with pytest.raises(SourceError, match="http 403"):
        trending.fetch_reddit(FakeHttp({"reddit.com": (403, None)}), Subreddit(name="a"))


def test_bilibili_filters_low_views_and_checks_code():
    body = {"code": 0, "data": {"list": [
        {"title": "big", "bvid": "BV1", "pubdate": 1_760_000_000, "stat": {"view": 500_000, "like": 1, "reply": 2}},
        {"title": "small", "bvid": "BV2", "pubdate": 1_760_000_000, "stat": {"view": 10}}]}}
    got = trending.fetch_bilibili(FakeHttp({"bilibili.com": (200, body)}), 36)
    assert [s.subject for s in got] == ["big"] and got[0].url.endswith("BV1")
    with pytest.raises(SourceError):
        trending.fetch_bilibili(FakeHttp({"bilibili.com": (200, {"code": -412})}), 36)


def test_keyword_filter_empty_means_everything():
    assert trending.matches("anything", ()) and trending.matches("Deep Sea", ("sea",)) and not trending.matches("x", ("sea",))


# ── youtube ─────────────────────────────────────────────────────────────────────

def test_extract_questions_keeps_questions_by_likes_and_dedupes():
    comments = [("為什麼牠會發光？", 3), ("好看", 99), ("為什麼牠會發光？", 50), ("想看馬里亞納海溝的影片", 7), ("?", 100),
                ("氣質好!講話又親切.面帶笑容有親和力?讚👍👍", 600), ("希望這個頻道越來越好", 400),
                ("Who is here because of the missing submarine?", 900), ("本当にいたのかな？ 怖いです", 800)]
    got = extract_questions(comments, "https://youtu.be/x")
    assert [q.text for q in got] == ["為什麼牠會發光？", "想看馬里亞納海溝的影片"]
    assert got[0].likes == 50


def test_trending_bonus_lifts_news_channel_items():
    plain = build_channel(small_config(), FakeHttp(full_routes()), None, NOW, Notes())
    boosted_config = small_config().model_copy(update={"trending_bonus": 15})
    boosted = build_channel(boosted_config, FakeHttp(full_routes()), None, NOW, Notes())
    pick = lambda radar: next(c for c in radar.candidates if c.kind == "trending").score
    assert pick(boosted) == pytest.approx(pick(plain) + 15, abs=0.11)


def test_auth_prefers_oauth_when_it_can_read():
    http = FakeHttp({"videos?part=id": (200, {})}, post=(200, {"access_token": "tok"}))
    auth, status = build_auth(http, client_id="a", client_secret="b", refresh_token="c", api_key="k")
    assert auth.mode == "oauth" and status.ok and "tok" not in repr(auth) and "tok" not in status.detail


def test_auth_falls_back_to_api_key_when_token_lacks_scope():
    seq = {"videos?part=id&id=dQw4w9WgXcQ&key=": (200, {}), "videos?part=id&id=dQw4w9WgXcQ": (403, {
        "error": {"errors": [{"reason": "insufficientPermissions"}]}})}
    http = FakeHttp(seq, post=(200, {"access_token": "tok"}))
    auth, status = build_auth(http, client_id="a", client_secret="b", refresh_token="c", api_key="k")
    assert auth.mode == "api_key" and "insufficientPermissions" in status.detail


def test_auth_none_when_nothing_works_and_never_leaks():
    http = FakeHttp(post=(400, {"error": "invalid_grant"}))
    auth, status = build_auth(http, client_id="a", client_secret="SECRET", refresh_token="RT", api_key="")
    assert auth is None and not status.ok
    assert "invalid_grant" in status.detail and "SECRET" not in status.detail and "RT" not in status.detail


def test_scrub_hides_keys_and_tokens():
    assert scrub("GET https://x/y?a=1&key=AIzaSECRET&b=2") == "GET https://x/y?a=1&key=***&b=2"


def yt_routes() -> dict:
    return {
        "youtube/v3/search": (200, {"items": [{"id": {"videoId": "v1"}}, {"id": {"videoId": "v2"}}]}),
        "youtube/v3/videos?part=snippet": (200, {"items": [
            {"id": "v1", "snippet": {"title": "A", "channelTitle": "C1", "publishedAt": "2020-01-01T00:00:00Z"},
             "statistics": {"viewCount": "900000"}},
            {"id": "v2", "snippet": {"title": "B", "channelTitle": "C2", "publishedAt": "2026-05-01T00:00:00Z"},
             "statistics": {"viewCount": "50000"}}]}),
        "youtube/v3/commentThreads": (200, {"items": [{"snippet": {"topLevelComment": {"snippet": {
            "textDisplay": "這個要怎麼做到？", "likeCount": 12}}}}]}),
    }


def test_youtube_competitors_sorted_and_units_counted():
    client = YouTubeClient(FakeHttp(yt_routes()), YouTubeAuth("api_key", api_key="k"))
    rivals = client.competitors("深海")
    assert [r.views for r in rivals] == [900000, 50000] and rivals[0].url.endswith("watch?v=v1")
    assert client.units == 101
    assert client.viewer_questions(rivals[0])[0].likes == 12 and client.units == 102


def test_youtube_budget_stops_before_spending():
    client = YouTubeClient(FakeHttp(yt_routes()), YouTubeAuth("api_key", api_key="k"), budget_units=50)
    with pytest.raises(QuotaBudgetExceeded):
        client.competitors("深海")
    assert client.units == 0 and client.http.asked == []


def test_youtube_cached_answer_costs_no_units():
    http = FakeHttp(yt_routes())
    client = YouTubeClient(http, YouTubeAuth("oauth", token="t"))
    http.warm = {f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&maxResults=15&order=viewCount"
                 f"&regionCode=TW&relevanceLanguage=zh-Hant&q=%E6%B7%B1%E6%B5%B7"}
    client.competitors("深海")
    assert client.units == 1       # only videos.list was paid for


def test_comments_disabled_is_an_empty_list():
    routes = {**yt_routes(), "youtube/v3/commentThreads": (403, {"error": {"errors": [{"reason": "commentsDisabled"}]}})}
    client = YouTubeClient(FakeHttp(routes), YouTubeAuth("api_key", api_key="k"))
    video = Competitor(title="t", channel="c", views=1, published="2026-01-01", url="https://www.youtube.com/watch?v=v1")
    assert client.viewer_questions(video) == []


def test_youtube_error_message_has_no_key():
    routes = {"youtube/v3/search": (403, {"error": {"errors": [{"reason": "quotaExceeded"}]}})}
    client = YouTubeClient(FakeHttp(routes), YouTubeAuth("api_key", api_key="SECRETKEY"))
    with pytest.raises(SourceError) as info:
        client.competitors("x")
    assert "quotaExceeded" in str(info.value) and "SECRETKEY" not in str(info.value)


# ── scoring ─────────────────────────────────────────────────────────────────────

def test_scores_are_monotonic_and_bounded():
    assert scoring.wiki_score(1000, 1.0) < scoring.wiki_score(100_000, 1.0) <= 35
    assert scoring.wiki_score(1000, 1.0) < scoring.wiki_score(1000, 2.5) <= scoring.wiki_score(1000, 1.0) + 15
    assert scoring.wiki_score(0, 0.3) == 0


def test_youtube_gap_bonus_needs_proven_demand_and_stale_rivals():
    old = [Competitor(title="t", channel="c", views=1, published="2020-01-01", url="u")] * 5
    fresh = [Competitor(title="t", channel="c", views=1, published="2026-09-01", url="u")] * 5
    assert scoring.youtube_score(500_000, old, TODAY) > scoring.youtube_score(500_000, fresh, TODAY)
    assert scoring.youtube_score(1000, old, TODAY) == pytest.approx(30 * 3 / 6.5)


# ── build / store / summary / brief ─────────────────────────────────────────────

def small_config() -> RadarConfig:
    return RadarConfig.model_validate({
        "channel": "deepsea", "title_template": "{subject}：深海裡的真相",
        "topics": [{"subject": "生物發光", "wiki": [{"lang": "zh", "title": "生物發光"}], "youtube_query": "深海 發光"},
                   {"subject": "沒有資料", "wiki": [{"lang": "en", "title": "Nope"}]}],
        "watch": {"hackernews_queries": ["deep sea"], "keywords": ["deep"]}})


def full_routes() -> dict:
    hn = {"hits": [{"objectID": "9", "title": "Deep sea robot", "points": 800, "num_comments": 120,
                    "created_at": "2026-10-24T08:00:00Z"}, {"objectID": "8", "title": "Unrelated", "points": 900}]}
    missing = {"query": {"pages": [{"title": "Nope", "missing": True}]}}
    return {**wiki_routes(), **yt_routes(), "hn.algolia.com": (200, hn),
            "api.php?action=query&titles=Nope": (200, missing)}


def test_build_channel_ranks_and_attaches_evidence():
    http = FakeHttp(full_routes())
    youtube = YouTubeClient(http, YouTubeAuth("api_key", api_key="k"))
    radar = build_channel(small_config(), http, youtube, NOW, Notes())
    assert radar.date == "2026-10-24" and radar.youtube_data_expires.startswith("2026-11-23")
    assert [c.id for c in radar.candidates][0] == "deepsea-20261024-01"
    scores = [c.score for c in radar.candidates]
    assert scores == sorted(scores, reverse=True)
    first = next(c for c in radar.candidates if c.subject == "生物發光")
    assert first.title_draft == "生物發光：深海裡的真相" and first.format == "shorts"   # growth 3x
    assert {e.source for e in first.evidence} == {"wikipedia", "youtube"}
    assert len(first.competitors) == 2 and first.viewer_questions[0].text == "這個要怎麼做到？"
    assert all(e.url.startswith("https://") for c in radar.candidates for e in c.evidence)
    trend = next(c for c in radar.candidates if c.kind == "trending")
    assert trend.subject == "Deep sea robot" and trend.format == "shorts" and trend.warnings   # foreign title
    assert "Unrelated" not in [c.subject for c in radar.candidates]
    empty = next(c for c in radar.candidates if c.subject == "沒有資料")
    assert empty.warnings and empty.score == 0


def test_refusing_source_is_asked_once_per_run():
    config = RadarConfig.model_validate({"channel": "x", "topics": [], "watch": {
        "subreddits": [{"name": "a"}, {"name": "b"}, {"name": "c"}]}})
    http = FakeHttp({"reddit.com": (403, None)})
    radar = build_channel(config, http, None, NOW, Notes())
    assert sum("reddit.com" in url for url in http.asked) == 1
    assert not next(s for s in radar.sources if s.source == "reddit").ok


def test_one_dead_source_does_not_blank_the_channel():
    routes = {**full_routes(), "hn.algolia.com": (500, None)}
    http = FakeHttp(routes)
    radar = build_channel(small_config(), http, None, NOW, Notes())
    assert any(c.kind == "evergreen" and c.evidence for c in radar.candidates)
    hn = next(s for s in radar.sources if s.source == "hackernews")
    assert not hn.ok and "http 500" in hn.note
    assert next(s for s in radar.sources if s.source == "wikipedia").requests >= 2


def test_store_roundtrip_and_latest(tmp_path):
    radar = build_channel(small_config(), FakeHttp(full_routes()), None, NOW, Notes())
    path = store.write_channel(tmp_path, radar)
    assert path == tmp_path / "2026-10-24" / "deepsea.json"
    assert json.loads(path.read_text(encoding="utf-8"))["candidates"][0]["id"].startswith("deepsea-")
    assert store.latest_for(tmp_path, "deepsea", TODAY + timedelta(days=3)) == path
    assert store.latest_for(tmp_path, "deepsea", TODAY + timedelta(days=9)) is None
    assert store.latest_for(tmp_path, "cel", TODAY) is None


def test_purge_deletes_youtube_data_after_30_days(tmp_path):
    for offset in (0, 29, 31, 45):
        (tmp_path / (TODAY - timedelta(days=offset)).isoformat()).mkdir()
        (tmp_path / (TODAY - timedelta(days=offset)).isoformat() / "a.json").write_text("{}")
    (tmp_path / "notes").mkdir()
    cache = tmp_path / "cache"
    (cache / "www.googleapis.com").mkdir(parents=True)
    old, new = cache / "www.googleapis.com" / "old.json", cache / "www.googleapis.com" / "new.json"
    old.write_text("{}")
    new.write_text("{}")
    removed = store.purge_expired(tmp_path, TODAY, cache, now=old.stat().st_mtime + 9 * 86400)
    kept = sorted(p.name for p in tmp_path.iterdir() if p.is_dir() and p.name != "cache")
    assert kept == sorted([TODAY.isoformat(), (TODAY - timedelta(days=29)).isoformat(), "notes"])
    assert old in removed and not old.exists()


def test_summary_lists_top_n_with_links_and_source_failures():
    http = FakeHttp({**full_routes(), "hn.algolia.com": (500, None)})
    youtube = YouTubeClient(http, YouTubeAuth("api_key", api_key="k"))
    radar = build_channel(small_config(), http, youtube, NOW, Notes())
    text = render_summary([radar], "2026-10-24", "api_key（可用）", top=1)
    assert text.count("**1.") == 1 and "**2." not in text
    assert "https://zh.wikipedia.org/wiki/" in text and "競爭影片前 2 名觀看數：900,000、50,000" in text
    assert "觀眾在問（12 讚）" in text and "hackernews（hackernews search" in text and "2026-11-23" in text


def test_brief_copies_radar_into_run_dir_and_is_empty_without_one(tmp_path):
    radar = build_channel(small_config(), FakeHttp(full_routes()), None, NOW, Notes())
    root, run_dir = tmp_path / "radar", tmp_path / "run"
    assert brief.radar_brief(run_dir, "deepsea", TODAY, root) == ""
    store.write_channel(root, radar)
    text = brief.radar_brief(run_dir, "deepsea", TODAY, root)
    assert "deepsea-20261024-" in text and "生物發光：深海裡的真相" in text and "不可自編" in text
    assert json.loads((run_dir / "topics" / "radar.json").read_text(encoding="utf-8"))["channel"] == "deepsea"


def test_default_root_follows_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CF_RADAR_DIR", str(tmp_path))
    assert store.default_root() == tmp_path


def test_http_cache_serves_second_call_and_never_stores_url(tmp_path):
    http = RadarHttp(cache_dir=tmp_path, spacing={}, sleep=lambda _: None)
    url = "https://hn.algolia.com/api/v1/search?q=1&key=SECRETKEY"
    http._cache_put(url, Reply(200, {"ok": 1}))
    assert http.get_json(url, ttl=60).data == {"ok": 1} and http.cached["hn.algolia.com"] == 1
    assert all("SECRETKEY" not in f.read_text() for f in tmp_path.rglob("*.json"))
    assert Counter(http.network) == Counter()


def _producer_prompts(tmp_path, monkeypatch, with_radar: bool, fixes: bool = False) -> tuple[list[str], Path]:
    from content_farm.review import producers
    from content_farm.review.client import CallResult
    from content_farm.review.config import load_review

    root = tmp_path / "radar"
    monkeypatch.setenv("CF_RADAR_DIR", str(root))
    if with_radar:
        store.write_channel(root, build_channel(small_config(), FakeHttp(full_routes()), None,
                                                datetime.now(timezone.utc), Notes()))
    run_dir = tmp_path / "run"
    (run_dir / "review").mkdir(parents=True)
    if fixes:
        (run_dir / "review" / "topic.fixes.json").write_text(json.dumps({"fixes": [{"who": "viewer", "problem": "x"}]}))
    prompts: list[str] = []

    def client(call):
        prompts.append(call.prompt)
        return CallResult(call.rid, True, {}, (), "sonnet", "medium", seconds=1.0, cost_usd=0.0, tokens={})

    producers.produce("topic", run_dir, channel="deepsea", config=load_review(), python="python", client=client)
    return prompts, run_dir


def test_topic_producer_prompt_includes_radar(tmp_path, monkeypatch):
    prompts, run_dir = _producer_prompts(tmp_path, monkeypatch, with_radar=True)
    assert "選題雷達" in prompts[0] and "生物發光：深海裡的真相" in prompts[0]
    assert (run_dir / "topics" / "radar.json").is_file()


def test_topic_producer_prompt_unchanged_without_radar(tmp_path, monkeypatch):
    prompts, run_dir = _producer_prompts(tmp_path, monkeypatch, with_radar=False)
    assert "選題雷達" not in prompts[0] and not (run_dir / "topics" / "radar.json").exists()
