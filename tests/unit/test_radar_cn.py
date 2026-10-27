"""Chinese-web sources (V2EX, Bilibili) and the cross-channel pool. Fake replies mirror the real field shapes
(checked against live public responses 2026-10-27) with invented titles; no author names, no network."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from content_farm.topic_radar import pool, trending
from content_farm.topic_radar.build import Notes, build_channel, fetch_trending_signals
from content_farm.topic_radar.config import RadarConfig, Watch
from content_farm.topic_radar.fit import FitRule, PoolConfig, assign_fits, load_pool_config
from content_farm.topic_radar.http import RadarHttp, Reply, SourceError

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
STAMP = NOW.timestamp()
FRESH = int(STAMP) - 3600


class FakeHttp(RadarHttp):
    def __init__(self, routes: dict[str, tuple[int, object]]):
        super().__init__(cache_dir=None)
        self.routes, self.asked, self.headers_seen = routes, [], []

    def get_json(self, url, *, headers=None, ttl=None):
        self.asked.append(url)
        self.headers_seen.append(dict(headers or {}))
        self.network[url.split("/")[2]] += 1
        for fragment in sorted(self.routes, key=len, reverse=True):
            if fragment in url:
                return Reply(*self.routes[fragment])
        return Reply(404, None)


def v2ex_topic(n: int, title: str, replies: int, content: str = "正文") -> dict:
    return {"id": n, "title": title, "url": f"https://www.v2ex.com/t/{n}", "replies": replies, "created": FRESH,
            "content": content, "member": {"username": "SECRET_NAME"}, "last_reply_by": "SECRET_NAME",
            "node": {"name": "programmer"}}


def bili_item(bvid: str, title: str, views: int, tname: str = "数码", pubdate: int = FRESH, desc: str = "简介") -> dict:
    return {"bvid": bvid, "title": title, "tname": tname, "pubdate": pubdate, "desc": desc,
            "owner": {"name": "SECRET_NAME"}, "stat": {"view": views, "like": 10, "reply": 5}}


# ── V2EX ────────────────────────────────────────────────────────────────────────

def test_v2ex_hot_keeps_title_link_replies_and_never_member_names():
    body = [v2ex_topic(1, "大模型又出新版本", 120, "x" * 500)]
    got = trending.fetch_v2ex(FakeHttp({"topics/hot.json": (200, body)}), None, STAMP)
    assert [s.subject for s in got] == ["大模型又出新版本"] and got[0].url == "https://www.v2ex.com/t/1"
    assert got[0].metrics == {"replies": 120.0} and got[0].source == "v2ex"
    assert len(got[0].excerpt) <= trending.EXCERPT_CHARS + 1 and got[0].fetched_at.startswith("2026-10-27")
    assert "SECRET_NAME" not in got[0].model_dump_json()


def test_v2ex_node_uses_show_endpoint_and_bad_status_raises():
    http = FakeHttp({"show.json?node_name=programmer": (200, [v2ex_topic(2, "t", 3)])})
    assert trending.fetch_v2ex(http, "programmer", STAMP)[0].url.endswith("/2")
    with pytest.raises(SourceError, match="http 403"):
        trending.fetch_v2ex(FakeHttp({"hot.json": (403, None)}), None, STAMP)


# ── Bilibili ────────────────────────────────────────────────────────────────────

def test_bilibili_popular_filters_zone_views_and_stale_and_sends_no_disguise_headers():
    body = {"code": 0, "data": {"list": [
        bili_item("BV1", "芯片横评", 500_000), bili_item("BV2", "搞笑合集", 900_000, tname="搞笑"),
        bili_item("BV3", "冷门", 10), bili_item("BV4", "旧闻", 500_000, pubdate=FRESH - 40 * 86400)]}}
    http = FakeHttp({"web-interface/popular": (200, body)})
    got = trending.fetch_bilibili_popular(http, ("数码",), STAMP)
    assert [s.subject for s in got] == ["芯片横评"] and "SECRET_NAME" not in got[0].model_dump_json()
    assert not http.headers_seen[0]        # honest radar User-Agent only: no browser disguise, no cookies, no signature


def test_bilibili_risk_control_352_is_a_source_error():
    with pytest.raises(SourceError, match="code -352"):
        trending.fetch_bilibili_popular(FakeHttp({"popular": (200, {"code": -352, "message": "-352"})}), (), STAMP)


def test_cache_does_not_replay_a_body_level_refusal(tmp_path):
    http = RadarHttp(cache_dir=tmp_path, spacing={}, sleep=lambda _: None)
    url = "https://api.bilibili.com/x/web-interface/popular?ps=1"
    http._cache_put(url, Reply(200, {"code": -352}))
    assert not http.is_cached(url, 60)
    http._cache_put(url, Reply(200, {"code": 0, "data": {}}))
    assert http.is_cached(url, 60)


# ── degrade, don't block ────────────────────────────────────────────────────────

def test_ranking_352_does_not_silence_popular_and_v2ex_still_runs():
    watch = Watch(bilibili_rids=(188, 36), bilibili_popular=True, v2ex_hot=True)
    http = FakeHttp({"ranking/v2": (200, {"code": -352}),
                     "web-interface/popular": (200, {"code": 0, "data": {"list": [bili_item("BV1", "显卡评测", 300_000)]}}),
                     "hot.json": (200, [v2ex_topic(1, "话题", 50)])})
    notes = Notes()
    signals = fetch_trending_signals(watch, http, notes, NOW)
    assert {s.source for s in signals} == {"bilibili", "v2ex"}
    assert sum("ranking/v2" in url for url in http.asked) == 1           # asked once, then left alone
    assert "code -352" in notes.errors["bilibili"][0]


def test_dead_v2ex_leaves_channel_candidates_and_marks_status():
    config = RadarConfig.model_validate({"channel": "technews", "topics": [], "watch": {"v2ex_hot": True, "hackernews_queries": ["ai"]}})
    hn = {"hits": [{"objectID": "9", "title": "AI thing", "points": 500, "num_comments": 1, "created_at": "2026-10-27T08:00:00Z"}]}
    http = FakeHttp({"hot.json": (500, None), "hn.algolia.com": (200, hn)})
    radar = build_channel(config, http, None, NOW, Notes())
    assert [c.subject for c in radar.candidates] == ["AI thing"]
    assert not next(s for s in radar.sources if s.source == "v2ex").ok


def test_cn_candidate_carries_link_fetch_time_excerpt_and_signal_warning():
    config = RadarConfig.model_validate({"channel": "technews", "topics": [], "watch": {"v2ex_hot": True}})
    http = FakeHttp({"hot.json": (200, [v2ex_topic(7, "开源项目改许可证", 80, "摘要内容")])})
    cand = build_channel(config, http, None, NOW, Notes()).candidates[0]
    assert cand.evidence[0].url == "https://www.v2ex.com/t/7" and cand.evidence[0].fetched_at.startswith("2026-10-27")
    assert cand.excerpt == "摘要内容" and any("信號" in w for w in cand.warnings) and any("簡體" in w for w in cand.warnings)


# ── fit rules ───────────────────────────────────────────────────────────────────

def rules() -> tuple[FitRule, ...]:
    return (
        FitRule(target="technews", kind="existing", label="科技", reason="r1", keywords=("ai", "开源")),
        FitRule(target="yokai", kind="existing", label="妖怪", reason="r2", keywords=("妖怪", "山海经")),
        FitRule(target="new-history", kind="new", label="歷史", reason="r3", keywords=("历史", "山海经")),
    )


def test_fit_ascii_keywords_match_whole_words_only():
    assert assign_fits("mail server", rules()) == ()
    assert assign_fits("AI 开源", rules())[0].target == "technews"


def test_fit_orders_by_hits_and_separates_existing_from_new():
    fits = assign_fits("山海经里的妖怪与历史", rules())
    assert [(f.target, f.kind, f.hits) for f in fits] == [("yokai", "existing", 2), ("new-history", "new", 2)]


def test_fit_origin_channel_comes_first_without_duplicates():
    fits = assign_fits("开源 ai 妖怪", rules(), origin="technews")
    assert fits[0].target == "technews" and fits[0].hits == 0
    assert [f.target for f in fits].count("technews") == 1 and "yokai" in [f.target for f in fits]


def test_shipped_pool_config_loads_and_routes_known_titles():
    config = load_pool_config()
    assert assign_fits("台积电 3nm 产能", config.rules)[0].target == "chipcat"
    assert assign_fits("山海经里的九尾狐", config.rules)[0].target == "yokai"
    assert assign_fits("囚徒困境 与 博弈论", config.rules)[0].target == "fable"
    assert any(f.kind == "new" for f in assign_fits("裁员 加班 薪资", config.rules))


def test_pool_config_rejects_new_kind_without_new_prefix(tmp_path):
    (tmp_path / "pool.yaml").write_text(
        "watch: {}\nrules:\n  - {target: oops, kind: new, label: l, reason: r, keywords: [x]}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="new-"):
        load_pool_config(tmp_path)


# ── pool ────────────────────────────────────────────────────────────────────────

def test_pool_merges_channels_dedupes_by_url_and_renders_top_per_group():
    config = PoolConfig(pool_size=10, per_target=1, watch=Watch(v2ex_hot=True), rules=rules())
    http = FakeHttp({"hot.json": (200, [v2ex_topic(1, "开源 AI 山海经", 150), v2ex_topic(2, "无关话题", 30)])})
    tech = RadarConfig.model_validate({"channel": "technews", "topics": [], "watch": {"v2ex_hot": True}})
    radar = build_channel(tech, http, None, NOW, Notes())
    result = pool.collect([radar], http, config, NOW)
    urls = [e.evidence[0].url for e in result.entries]
    assert len(urls) == len(set(urls)) == 2                               # same V2EX story from two sides = one entry
    top = result.entries[0]
    assert {f.target for f in top.fits} >= {"technews", "yokai"} and top.id == "pool-20261027-01"
    text = pool.render_pool(result, config)
    assert "## 科技" in text and "https://www.v2ex.com/t/1" in text and "抓取 2026-10-27" in text
    assert "SECRET_NAME" not in text and "SECRET_NAME" not in result.model_dump_json()
    assert text.count("**1.") >= 2 and "**2." not in text                  # per_target=1


def test_pool_written_files_roundtrip(tmp_path):
    config = PoolConfig(watch=Watch(v2ex_hot=True), rules=rules())
    result = pool.collect([], FakeHttp({"hot.json": (200, [v2ex_topic(1, "ai", 10)])}), config, NOW)
    json_path, md_path = pool.write_pool(tmp_path, result, pool.render_pool(result, config))
    assert json_path.parent.name == "2026-10-27" and md_path.read_text(encoding="utf-8").startswith("# 跨頻道選題池")
